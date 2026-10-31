from flask_login import UserMixin
from app import db
from app.utils.security import verify_password


class User(UserMixin):
    def __init__(self, row: dict):
        self.id = row["id"]
        self.uuid = row.get("uuid")
        self.email = row["email"]
        self.mobile = row.get("mobile")
        self.password_hash = row["password_hash"]
        self.full_name = row["full_name"]
        self.role = row["role"]
        self._is_active = bool(row.get("is_active", 0))
        self.is_verified = bool(row.get("is_verified", 0))
        self.must_change_password = bool(row.get("must_change_password", 0))
        self.profile_photo_url = row.get("profile_photo_url")
        self.seller_username = row.get("seller_username")
        self.restricted = bool(row.get("restricted", 0))
        self.restriction_reason = row.get("restriction_reason")
        self.created_at = row.get("created_at")

    def get_id(self):
        return str(self.id)

    @property
    def is_active(self):
        """Flask-Login uses this; must be a property (no setter conflict)."""
        return self._is_active

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def check_password(self, password: str) -> bool:
        return verify_password(self.password_hash, password)

    def is_admin(self) -> bool:
        return self.role == "admin"

    def is_seller(self) -> bool:
        return self.role == "seller"

    def is_staff(self) -> bool:
        return self.role == "staff"

    def is_customer(self) -> bool:
        return self.role == "customer"

    @staticmethod
    def get_by_id(user_id: int):
        row = db.fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))
        return User(row) if row else None

    @staticmethod
    def get_by_email(email: str):
        row = db.fetch_one("SELECT * FROM users WHERE email = ?", (email.lower().strip(),))
        return User(row) if row else None

    @staticmethod
    def get_by_username(username: str):
        row = db.fetch_one("SELECT * FROM users WHERE seller_username = ?", (username,))
        return User(row) if row else None
