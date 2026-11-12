"""
Background worker for:
- Seller credential issuance (after 2 min delay)
- Commission deadline checks and hourly reminders
- Email retries

Run with: python scripts/worker.py
On Vercel, use a external cron / worker service (e.g. cron-job.org calling an API endpoint,
or a separate always-on process). Vercel serverless does not support long-running processes.
"""
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app import create_app, db
from app.utils.security import hash_password
from app.services.email_service import send_seller_credentials, send_commission_reminder
from app.utils.helpers import now_kathmandu

app = create_app()


def process_seller_credentials():
    with app.app_context():
        jobs = db.fetch_all(
            """SELECT * FROM seller_credential_jobs
               WHERE status = 'pending' AND scheduled_at <= datetime('now')"""
        )
        for job in jobs:
            try:
                pw_hash = hash_password(job["password_plain_temp"])
                db.execute(
                    """UPDATE users SET role = 'seller', seller_username = ?, password_hash = ?,
                       must_change_password = 1, is_active = 1, is_verified = 1, updated_at = datetime('now')
                       WHERE id = ?""",
                    (job["username"], pw_hash, job["user_id"]),
                )
                db.execute(
                    "UPDATE seller_applications SET status = 'approved', processed_at = datetime('now') WHERE id = ?",
                    (job["application_id"],),
                )
                user = db.fetch_one("SELECT full_name, email FROM users WHERE id = ?", (job["user_id"],))
                if user:
                    send_seller_credentials(user["email"], job["username"], job["password_plain_temp"], user["full_name"])
                db.execute(
                    "UPDATE seller_credential_jobs SET status = 'sent', processed_at = datetime('now'), password_plain_temp = '' WHERE id = ?",
                    (job["id"],),
                )
                print(f"Credentials sent for user {job['user_id']}")
            except Exception as e:
                db.execute(
                    "UPDATE seller_credential_jobs SET status = 'failed', error_message = ? WHERE id = ?",
                    (str(e), job["id"]),
                )
                print(f"Failed job {job['id']}: {e}")


def process_commission_deadlines():
    with app.app_context():
        overdue = db.fetch_all(
            """SELECT * FROM seller_commissions
               WHERE status IN ('pending','partial') AND deadline_at < datetime('now')"""
        )
        for c in overdue:
            db.execute(
                "UPDATE seller_commissions SET status = 'overdue', updated_at = datetime('now') WHERE id = ?",
                (c["id"],),
            )
            print(f"Commission {c['id']} marked overdue")


def main():
    print("Mobile Clinic worker started")
    while True:
        try:
            process_seller_credentials()
            process_commission_deadlines()
        except Exception as e:
            print(f"Worker error: {e}")
        time.sleep(30)


if __name__ == "__main__":
    main()
