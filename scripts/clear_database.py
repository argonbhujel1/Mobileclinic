"""
Wipe all application data and re-seed default admin.
Usage (from project root):
  python scripts/clear_database.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

from app import create_app, db
from app.db import ensure_admin_user, init_schema

TABLES = [
    "trip_location_updates",
    "trips",
    "staff_assignments",
    "repair_status_history",
    "repair_tickets",
    "order_items",
    "payments",
    "orders",
    "commission_payments",
    "seller_commissions",
    "product_images",
    "products",
    "categories",
    "seller_credential_jobs",
    "seller_applications",
    "email_verifications",
    "password_reset_tokens",
    "email_delivery_logs",
    "audit_logs",
    "admin_qr_codes",
    "site_settings",
    "users",
]


def main():
    app = create_app()
    with app.app_context():
        print("Connecting…")
        init_schema()
        for table in TABLES:
            try:
                db.execute(f"DELETE FROM {table}")
                print(f"  cleared {table}")
            except Exception as e:
                print(f"  skip {table}: {e}")
        ensure_admin_user()
        print("Done. Database is fresh. Default admin re-seeded from env (ADMIN_EMAIL / ADMIN_PASSWORD) or defaults.")
        print("Login with your configured admin credentials.")


if __name__ == "__main__":
    confirm = os.getenv("CONFIRM_WIPE", "")
    if confirm != "YES":
        print("This DELETES all data. Re-run with: set CONFIRM_WIPE=YES")
        print('  PowerShell: $env:CONFIRM_WIPE="YES"; python scripts/clear_database.py')
        sys.exit(1)
    main()
