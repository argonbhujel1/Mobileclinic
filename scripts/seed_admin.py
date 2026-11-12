"""Create or update initial admin user. Run once after schema init."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()
from app import create_app, db
from app.utils.security import hash_password
from app.utils.helpers import generate_uuid

app = create_app()
with app.app_context():
    db.init_schema()
    email = os.getenv("ADMIN_EMAIL", "bishal2014nir@gmail.com")
    password = os.getenv("ADMIN_PASSWORD", "mcl_admin123")
    existing = db.fetch_one("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
    if existing:
        db.execute(
            "UPDATE users SET password_hash = ?, is_active = 1, is_verified = 1, must_change_password = 0, updated_at = datetime('now') WHERE id = ?",
            (hash_password(password), existing["id"]),
        )
        print(f"Admin password updated: {email} / {password}")
    else:
        db.execute(
            """INSERT INTO users (uuid, email, mobile, password_hash, full_name, role, is_active, is_verified)
               VALUES (?, ?, ?, ?, ?, 'admin', 1, 1)""",
            (generate_uuid(), email, "9819378583", hash_password(password), "Bishal Niraula"),
        )
        print(f"Admin created: {email} / {password}")
