import os
from datetime import timedelta
from pathlib import Path
from dotenv import load_dotenv

# Always load .env from project root (folder that contains app/), not only CWD
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _PROJECT_ROOT / ".env"
# override=True so .env wins over empty shell vars
load_dotenv(_ENV_PATH, override=True)
# also try CWD as fallback
load_dotenv(override=False)


def _env(name: str, default: str = "") -> str:
    """Read env var, strip whitespace and optional surrounding quotes."""
    val = os.getenv(name)
    if val is None:
        return default
    val = val.strip()
    if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
        val = val[1:-1].strip()
    return val


def _env_bool(name: str, default: bool = False) -> bool:
    val = _env(name, "")
    if not val:
        return default
    return val.lower() in ("true", "1", "yes", "on")


def _env_int(name: str, default: int) -> int:
    val = _env(name, "")
    if not val:
        return default
    try:
        return int(val)
    except ValueError:
        return default


class Config:
    SECRET_KEY = _env("FLASK_SECRET_KEY", "dev-secret-change-in-production")
    APP_BASE_URL = _env("APP_BASE_URL", "http://localhost:5000")

    # Turso
    TURSO_DATABASE_URL = _env("TURSO_DATABASE_URL", "")
    TURSO_AUTH_TOKEN = _env("TURSO_AUTH_TOKEN", "")

    # Cloudinary
    CLOUDINARY_CLOUD_NAME = _env("CLOUDINARY_CLOUD_NAME", "")
    CLOUDINARY_API_KEY = _env("CLOUDINARY_API_KEY", "")
    CLOUDINARY_API_SECRET = _env("CLOUDINARY_API_SECRET", "")

    # ImgBB
    IMGBB_API_KEY = _env("IMGBB_API_KEY", "")

    # Mail — support common alternate key names
    MAIL_SERVER = _env("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = _env_int("MAIL_PORT", 587)
    MAIL_USE_TLS = _env_bool("MAIL_USE_TLS", True)
    MAIL_USE_SSL = _env_bool("MAIL_USE_SSL", False)
    MAIL_USERNAME = (
        _env("MAIL_USERNAME")
        or _env("EMAIL_USER")
        or _env("SMTP_USERNAME")
        or _env("SMTP_USER")
        or ""
    )
    MAIL_PASSWORD = (
        _env("MAIL_PASSWORD")
        or _env("EMAIL_PASSWORD")
        or _env("SMTP_PASSWORD")
        or _env("MAIL_APP_PASSWORD")
        or ""
    )
    # Gmail app passwords are often stored with spaces — keep spaces (Google accepts them)
    # but also accept without spaces
    MAIL_DEFAULT_SENDER = _env(
        "MAIL_DEFAULT_SENDER",
        "",
    )
    if not MAIL_DEFAULT_SENDER and MAIL_USERNAME:
        MAIL_DEFAULT_SENDER = f"Mobile Clinic <{MAIL_USERNAME}>"
    if not MAIL_DEFAULT_SENDER:
        MAIL_DEFAULT_SENDER = "Mobile Clinic <noreply@localhost>"

    # Maps
    MAP_TILE_PROVIDER_URL = _env(
        "MAP_TILE_PROVIDER_URL",
        "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    )
    GEOCODING_PROVIDER_URL = _env(
        "GEOCODING_PROVIDER_URL", "https://nominatim.openstreetmap.org"
    )
    ROUTING_PROVIDER_URL = _env("ROUTING_PROVIDER_URL", "")

    # Business
    BUSINESS_NAME = _env("BUSINESS_NAME", "Mobile Clinic Urlabari")
    BUSINESS_OWNER = _env("BUSINESS_OWNER", "Bishal Niraula")
    BUSINESS_EMAIL = _env("BUSINESS_EMAIL", "bishal2014nir@gmail.com")
    BUSINESS_PHONE = _env("BUSINESS_PHONE", "9819378583")
    CURRENCY = _env("CURRENCY", "NPR")
    TIMEZONE = _env("TIMEZONE", "Asia/Kathmandu")
    COMMISSION_RATE = float(_env("COMMISSION_RATE", "0.08") or "0.08")
    COMMISSION_DEADLINE_HOURS = _env_int("COMMISSION_DEADLINE_HOURS", 2)

    # Security
    OTP_EXPIRY_MINUTES = _env_int("OTP_EXPIRY_MINUTES", 10)
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    _app_url = APP_BASE_URL.lower()
    _is_https = _app_url.startswith("https://")
    SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", default=_is_https)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None
    WTF_CSRF_CHECK_DEFAULT = True

    # Upload limits
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
    MAX_PRODUCT_IMAGES = _env_int("MAX_PRODUCT_IMAGES", 12)
    MIN_SELLER_PRODUCT_IMAGES = 4
    MIN_ADMIN_PRODUCT_IMAGES = 1

    RATELIMIT_DEFAULT = "200 per day;50 per hour"
    RATELIMIT_STORAGE_URI = "memory://"

    WHATSAPP_NUMBER = _env("WHATSAPP_NUMBER", "9819378583")


class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = Config.SESSION_COOKIE_SECURE


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
