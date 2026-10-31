from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models.user import User
from app.utils.security import hash_password, generate_reset_token, verify_reset_token
from app.utils.helpers import generate_uuid, generate_otp, hash_otp, now_kathmandu, now_naive, parse_dt, is_safe_url
from app.services.email_service import send_otp_email, send_seller_credentials
from app.extensions import limiter

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per hour")
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.customer"))
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        mobile = request.form.get("mobile", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        errors = []
        if not full_name or len(full_name) < 2:
            errors.append("Full name is required.")
        if not email or "@" not in email:
            errors.append("Valid email is required.")
        if not mobile or len(mobile) < 10:
            errors.append("Valid mobile number is required.")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        if password != confirm:
            errors.append("Passwords do not match.")
        if db.fetch_one("SELECT id FROM users WHERE email = ?", (email,)):
            errors.append("Email already registered.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("auth/register.html")

        user_uuid = generate_uuid()
        pw_hash = hash_password(password)
        db.execute(
            """INSERT INTO users (uuid, email, mobile, password_hash, full_name, role, is_active, is_verified)
               VALUES (?, ?, ?, ?, ?, 'customer', 0, 0)""",
            (user_uuid, email, mobile, pw_hash, full_name),
        )
        row = db.fetch_one("SELECT id FROM users WHERE uuid = ?", (user_uuid,))
        user_id = row["id"] if row else None
        if not user_id:
            flash("Registration failed. Please try again.", "error")
            return render_template("auth/register.html")

        otp = generate_otp()
        otp_h = hash_otp(otp)
        expires = (now_naive() + timedelta(minutes=current_app.config.get("OTP_EXPIRY_MINUTES", 10))).strftime("%Y-%m-%d %H:%M:%S")
        db.execute(
            """INSERT INTO email_verifications (user_id, email, otp_hash, expires_at)
               VALUES (?, ?, ?, ?)""",
            (user_id, email, otp_h, expires),
        )

        try:
            send_otp_email(email, otp, full_name)
        except Exception as e:
            # Still allow verify; show OTP in flash only in DEBUG
            current_app.logger.error("OTP email failed: %s", e)
            if current_app.debug:
                flash(f"Email failed (dev OTP: {otp})", "warning")
            else:
                flash("Could not send email. Contact support if OTP does not arrive.", "warning")
        session["pending_verify_user_id"] = user_id
        session["pending_verify_email"] = email
        flash("Account created. Enter the OTP sent to your email.", "success")
        return redirect(url_for("auth.verify_otp"))

    return render_template("auth/register.html")


@auth_bp.route("/verify-otp", methods=["GET", "POST"])
@limiter.limit("15 per hour")
def verify_otp():
    user_id = session.get("pending_verify_user_id")
    email = session.get("pending_verify_email")
    if not user_id or not email:
        flash("No pending verification. Please register first.", "error")
        return redirect(url_for("auth.register"))

    if request.method == "POST":
        otp = request.form.get("otp", "").strip()
        row = db.fetch_one(
            """SELECT * FROM email_verifications
               WHERE user_id = ? AND email = ? AND verified_at IS NULL
               ORDER BY created_at DESC LIMIT 1""",
            (user_id, email),
        )
        if not row:
            flash("No active OTP found. Please register again.", "error")
            return redirect(url_for("auth.register"))
        if row["attempts"] >= 5:
            flash("Too many attempts. Please request a new OTP.", "error")
            return redirect(url_for("auth.register"))
        if parse_dt(row["expires_at"]) < now_naive():
            flash("OTP expired. Please register again.", "error")
            return redirect(url_for("auth.register"))

        db.execute("UPDATE email_verifications SET attempts = attempts + 1 WHERE id = ?", (row["id"],))
        if hash_otp(otp) != row["otp_hash"]:
            flash("Invalid OTP. Please try again.", "error")
            return render_template("auth/verify_otp.html", email=email)

        db.execute("UPDATE email_verifications SET verified_at = datetime('now') WHERE id = ?", (row["id"],))
        db.execute("UPDATE users SET is_active = 1, is_verified = 1, updated_at = datetime('now') WHERE id = ?", (user_id,))
        session.pop("pending_verify_user_id", None)
        session.pop("pending_verify_email", None)
        user = User.get_by_id(user_id)
        login_user(user)
        flash("Email verified! Welcome to Mobile Clinic.", "success")
        return redirect(url_for("dashboard.customer"))

    return render_template("auth/verify_otp.html", email=email)


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("20 per hour")
def login():
    if current_user.is_authenticated:
        return _redirect_by_role(current_user)
    if request.method == "POST":
        email_or_user = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))

        user = User.get_by_email(email_or_user) or User.get_by_username(email_or_user)
        if not user or not user.check_password(password):
            flash("Invalid credentials.", "error")
            return render_template("auth/login.html")
        if not user.is_active:
            flash("Account is not active. Please verify your email.", "error")
            return render_template("auth/login.html")
        if user.restricted:
            flash(f"Account restricted: {user.restriction_reason or 'Contact support'}", "error")
            return render_template("auth/login.html")

        login_user(user, remember=remember)
        db.execute("UPDATE users SET last_login_at = datetime('now') WHERE id = ?", (user.id,))
        if user.must_change_password:
            flash("Please change your temporary password.", "warning")
            return redirect(url_for("dashboard.change_password"))
        next_page = request.args.get("next")
        if next_page and is_safe_url(next_page):
            return redirect(next_page)
        return _redirect_by_role(user)
    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("main.home"))


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("5 per hour")
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.get_by_email(email)
        if user:
            token = generate_reset_token(user.id, user.email)
            # Store hash and send email (simplified)
            from app.utils.helpers import hash_otp as h
            from app.utils.security import hash_password as hp
            token_hash = h(token)
            expires = (now_kathmandu() + timedelta(hours=1)).isoformat()
            db.execute(
                "INSERT INTO password_reset_tokens (user_id, token_hash, expires_at) VALUES (?, ?, ?)",
                (user.id, token_hash, expires),
            )
            reset_url = f"{current_app.config['APP_BASE_URL']}/auth/reset-password/{token}"
            from app.services.email_service import send_email
            send_email(email, "Password Reset — Mobile Clinic", "password_reset", reset_url=reset_url, full_name=user.full_name)
        flash("If that email exists, a reset link has been sent.", "info")
        return redirect(url_for("auth.login"))
    return render_template("auth/forgot_password.html")


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    data = verify_reset_token(token)
    if not data:
        flash("Invalid or expired reset link.", "error")
        return redirect(url_for("auth.forgot_password"))
    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if len(password) < 8 or password != confirm:
            flash("Passwords must match and be at least 8 characters.", "error")
            return render_template("auth/reset_password.html", token=token)
        pw_hash = hash_password(password)
        db.execute(
            "UPDATE users SET password_hash = ?, must_change_password = 0, updated_at = datetime('now') WHERE id = ?",
            (pw_hash, data["user_id"]),
        )
        flash("Password updated. Please log in.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/reset_password.html", token=token)


def _redirect_by_role(user):
    if user.is_admin():
        return redirect(url_for("admin.overview"))
    if user.is_seller():
        return redirect(url_for("dashboard.seller"))
    if user.is_staff():
        return redirect(url_for("dashboard.staff"))
    return redirect(url_for("dashboard.customer"))
