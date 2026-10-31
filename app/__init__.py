import os
import logging
from flask import Flask, render_template, g, session, request
from app.config import config_by_name
from app.extensions import init_extensions, login_manager
from app.models.user import User
from app import db as database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_app(config_name=None):
    if config_name is None:
        # Prefer development for local; production only when explicitly set
        config_name = os.getenv("FLASK_ENV") or os.getenv("FLASK_CONFIG") or "development"
        if config_name not in config_by_name:
            config_name = "development"
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
        instance_relative_config=True,
    )
    app.config.from_object(config_by_name.get(config_name, config_by_name["default"]))

    # --- Session / CSRF hard fixes for local HTTP (and LAN IP access) ---
    app_url = str(app.config.get("APP_BASE_URL", "http://localhost")).lower()
    is_https = app_url.startswith("https://")
    # Never use Secure cookies on plain HTTP — otherwise browser drops session → CSRF fails
    if not is_https or app.debug or config_name == "development":
        app.config["SESSION_COOKIE_SECURE"] = False
        app.config["REMEMBER_COOKIE_SECURE"] = False
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_PATH"] = "/"
    # Do not set DOMAIN — allows 127.0.0.1 and LAN IP
    app.config["SESSION_COOKIE_DOMAIN"] = None
    app.config["WTF_CSRF_TIME_LIMIT"] = None
    # Stable secret if missing
    if not app.config.get("SECRET_KEY") or app.config["SECRET_KEY"] == "dev-secret-change-in-production":
        # keep default but log once
        logger.info("Using default FLASK_SECRET_KEY — set a fixed value in .env for stable sessions")

    init_extensions(app)

    # Force-reload mail vars from project-root .env (fixes "Mail NOT configured" when CWD ≠ project)
    try:
        from pathlib import Path
        from dotenv import load_dotenv
        env_file = Path(app.root_path).resolve().parent / ".env"
        load_dotenv(env_file, override=True)
        alias_map = {
            "MAIL_USERNAME": "MAIL_USERNAME",
            "EMAIL_USER": "MAIL_USERNAME",
            "SMTP_USERNAME": "MAIL_USERNAME",
            "SMTP_USER": "MAIL_USERNAME",
            "MAIL_PASSWORD": "MAIL_PASSWORD",
            "EMAIL_PASSWORD": "MAIL_PASSWORD",
            "SMTP_PASSWORD": "MAIL_PASSWORD",
            "MAIL_APP_PASSWORD": "MAIL_PASSWORD",
            "MAIL_SERVER": "MAIL_SERVER",
            "MAIL_PORT": "MAIL_PORT",
            "MAIL_USE_TLS": "MAIL_USE_TLS",
            "MAIL_USE_SSL": "MAIL_USE_SSL",
            "MAIL_DEFAULT_SENDER": "MAIL_DEFAULT_SENDER",
        }
        for src, dest in alias_map.items():
            val = os.getenv(src)
            if val is None or not str(val).strip():
                continue
            cleaned = str(val).strip()
            if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in "'\"":
                cleaned = cleaned[1:-1].strip()
            app.config[dest] = cleaned
        if app.config.get("MAIL_USERNAME") and not app.config.get("MAIL_DEFAULT_SENDER"):
            app.config["MAIL_DEFAULT_SENDER"] = f"Mobile Clinic <{app.config['MAIL_USERNAME']}>"
        if not app.config.get("MAIL_SERVER"):
            app.config["MAIL_SERVER"] = "smtp.gmail.com"
        if not app.config.get("MAIL_PORT"):
            app.config["MAIL_PORT"] = 587
        else:
            try:
                app.config["MAIL_PORT"] = int(app.config["MAIL_PORT"])
            except (TypeError, ValueError):
                app.config["MAIL_PORT"] = 587
        mu = (app.config.get("MAIL_USERNAME") or "").strip()
        mp = (app.config.get("MAIL_PASSWORD") or "").strip()
        if mu and mp:
            logger.info(
                "Mail configured: user=%s server=%s port=%s password_len=%s env=%s",
                mu, app.config.get("MAIL_SERVER"), app.config.get("MAIL_PORT"), len(mp), env_file,
            )
        else:
            logger.warning(
                "Mail NOT configured (user=%s pass=%s). .env path=%s exists=%s — "
                "put MAIL_USERNAME and MAIL_PASSWORD in that file (no quotes needed).",
                bool(mu), bool(mp), env_file, env_file.exists(),
            )
    except Exception as e:
        logger.warning("Mail env reload failed: %s", e)


    @login_manager.user_loader
    def load_user(user_id):
        try:
            return User.get_by_id(int(user_id))
        except Exception:
            return None

    # Register blueprints
    from app.blueprints.main import main_bp
    from app.blueprints.auth import auth_bp
    from app.blueprints.marketplace import marketplace_bp
    from app.blueprints.repair import repair_bp
    from app.blueprints.dashboard import dashboard_bp
    from app.blueprints.api import api_bp
    from app.blueprints.admin import admin_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(marketplace_bp, url_prefix="/phones")
    app.register_blueprint(repair_bp, url_prefix="/repair")
    app.register_blueprint(dashboard_bp, url_prefix="/dashboard")
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(admin_bp, url_prefix="/admin")

    # Context processors
    @app.context_processor
    def inject_globals():
        from app.services.settings_service import get_settings
        settings = get_settings() or {}
        site_name = (settings.get("site_name") or "").strip() or app.config["BUSINESS_NAME"]
        contact_email = (settings.get("contact_email") or "").strip() or app.config["BUSINESS_EMAIL"]
        contact_phone = (settings.get("contact_phone") or "").strip() or app.config["BUSINESS_PHONE"]
        whatsapp = (settings.get("whatsapp_number") or "").strip() or app.config.get("WHATSAPP_NUMBER", "")
        return {
            "business_name": site_name,
            "business_email": contact_email,
            "business_phone": contact_phone,
            "currency": app.config["CURRENCY"],
            "whatsapp": whatsapp,
            "settings": settings,
            "map_tile_url": app.config["MAP_TILE_PROVIDER_URL"],
        }

    # Error handlers
    @app.errorhandler(404)
    def not_found(e):
        return render_template("pages/404.html"), 404

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("pages/403.html"), 403

    @app.errorhandler(500)
    def server_error(e):
        logger.exception("Server error: %s", e)
        return render_template("pages/500.html"), 500

    # Schema + admin seed once per process (avoids Turso lag every request)
    _schema_ready = {"ok": False, "failed": False}

    @app.before_request
    def ensure_db():
        from flask import request as flask_request
        # Skip DB work for static assets (was flooding Turso on every CSS/JS/favicon)
        if flask_request.path.startswith("/static") or flask_request.path == "/favicon.ico":
            return

        session.permanent = True
        if "_ok" not in session:
            session["_ok"] = 1

        if _schema_ready["ok"] or _schema_ready.get("failed"):
            return
        try:
            database.init_schema()
            _schema_ready["ok"] = True
        except Exception as e:
            _schema_ready["failed"] = True
            logger.error("DB init error (will not retry every request): %s", e)

    @app.errorhandler(400)
    def bad_request(e):
        # Friendlier message when CSRF fails
        desc = str(getattr(e, "description", e) or "")
        if "csrf" in desc.lower() or "CSRF" in str(e):
            logger.warning("CSRF failed on %s — session cookie missing? Secure=%s host=%s",
                           request.path, app.config.get("SESSION_COOKIE_SECURE"), request.host)
            from flask import flash, redirect, url_for
            flash("Session expired or cookies blocked. Refresh the page and try again. Use http://127.0.0.1:5000 (not HTTPS).", "error")
            return redirect(request.referrer or url_for("main.home")), 302
        return render_template("pages/500.html"), 400

    return app
