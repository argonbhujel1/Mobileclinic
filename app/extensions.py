from flask_login import LoginManager
from flask_mail import Mail
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect

login_manager = LoginManager()
mail = Mail()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, default_limits=["200 per day", "50 per hour"])


def init_extensions(app):
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"
    # "strong" can drop sessions on IP/header changes (mobile/LAN) → CSRF token missing
    login_manager.session_protection = "basic"

    mail.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    # Ensure local HTTP never requires Secure session cookie
    if app.debug or not str(app.config.get("APP_BASE_URL", "")).lower().startswith("https://"):
        app.config["SESSION_COOKIE_SECURE"] = False
