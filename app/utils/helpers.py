import uuid
import secrets
import hashlib
import re
from datetime import datetime, timedelta
from functools import wraps
from flask import abort, flash, redirect, url_for, request
from flask_login import current_user
import pytz

KATHMANDU_TZ = pytz.timezone("Asia/Kathmandu")


def generate_uuid() -> str:
    return str(uuid.uuid4())


def generate_order_id() -> str:
    return f"MC-ORD-{secrets.token_hex(4).upper()}-{datetime.now().strftime('%y%m%d')}"


def generate_ticket_id() -> str:
    return f"MC-REP-{secrets.token_hex(4).upper()}-{datetime.now().strftime('%y%m%d')}"


def generate_otp(length: int = 6) -> str:
    return "".join([str(secrets.randbelow(10)) for _ in range(length)])


def hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()


def generate_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


def now_kathmandu() -> datetime:
    return datetime.now(KATHMANDU_TZ)


def now_naive() -> datetime:
    """UTC-naive local wall time for comparing with DB timestamps stored without tz."""
    return datetime.now(KATHMANDU_TZ).replace(tzinfo=None)


def parse_dt(value) -> datetime:
    """Parse DB/ISO datetime to naive local (no tz) for safe comparisons."""
    if value is None:
        return now_naive()
    if isinstance(value, datetime):
        dt = value
    else:
        s = str(value).strip().replace("Z", "+00:00")
        # Turso sometimes returns "YYYY-MM-DD HH:MM:SS"
        if "T" not in s and " " in s and "+" not in s:
            try:
                return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            try:
                return datetime.strptime(str(value)[:19], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return now_naive()
    if dt.tzinfo is not None:
        dt = dt.astimezone(KATHMANDU_TZ).replace(tzinfo=None)
    return dt



def to_kathmandu(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return KATHMANDU_TZ.localize(dt)
    return dt.astimezone(KATHMANDU_TZ)


def format_npr(amount: float) -> str:
    return f"NPR {amount:,.0f}"


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")


def normalize_name_for_username(name: str) -> str:
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9]", "", name)
    return name[:20] or "user"


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login", next=request.url))
            if current_user.role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return wrapped
    return decorator


def admin_required(f):
    return role_required("admin")(f)


def seller_required(f):
    return role_required("seller", "admin")(f)


def staff_required(f):
    return role_required("staff", "admin")(f)


def sanitize_html(text: str) -> str:
    import bleach
    allowed_tags = ["p", "br", "strong", "em", "ul", "ol", "li", "a"]
    allowed_attrs = {"a": ["href", "title", "rel"]}
    return bleach.clean(text or "", tags=allowed_tags, attributes=allowed_attrs, strip=True)


def is_safe_url(target: str) -> bool:
    from urllib.parse import urlparse, urljoin
    from flask import request
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ("http", "https") and ref_url.netloc == test_url.netloc
