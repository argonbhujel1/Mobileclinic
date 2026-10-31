"""
Branded email notifications for Mobile Clinic.
"""
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask import current_app, render_template
from flask_mail import Message
from app.extensions import mail
from app import db
from app.utils.helpers import now_kathmandu

logger = logging.getLogger(__name__)


def _log_email(recipient, subject, template_name, status, error=None, related_type=None, related_id=None):
    try:
        db.execute(
            """INSERT INTO email_delivery_logs
               (recipient, subject, template_name, status, error_message, related_type, related_id, sent_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                recipient,
                subject,
                template_name,
                status,
                error,
                related_type,
                related_id,
                now_kathmandu().isoformat() if status == "sent" else None,
            ),
        )
    except Exception as e:
        logger.warning("Could not log email: %s", e)


def _mail_creds():
    """Resolve mail credentials from app config and live environment (fresh .env)."""
    import os
    from pathlib import Path
    try:
        from dotenv import load_dotenv
        root = Path(current_app.root_path).resolve().parent
        load_dotenv(root / ".env", override=True)
    except Exception:
        pass

    def clean(v):
        if v is None:
            return ""
        v = str(v).strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
            v = v[1:-1].strip()
        return v

    user = clean(current_app.config.get("MAIL_USERNAME")) or clean(
        os.getenv("MAIL_USERNAME")
        or os.getenv("EMAIL_USER")
        or os.getenv("SMTP_USERNAME")
        or os.getenv("SMTP_USER")
    )
    password = clean(current_app.config.get("MAIL_PASSWORD")) or clean(
        os.getenv("MAIL_PASSWORD")
        or os.getenv("EMAIL_PASSWORD")
        or os.getenv("SMTP_PASSWORD")
        or os.getenv("MAIL_APP_PASSWORD")
    )
    # If config was empty at import time, push live values back into app.config
    if user:
        current_app.config["MAIL_USERNAME"] = user
    if password:
        current_app.config["MAIL_PASSWORD"] = password
    if user and not current_app.config.get("MAIL_DEFAULT_SENDER"):
        current_app.config["MAIL_DEFAULT_SENDER"] = f"Mobile Clinic <{user}>"
    return user, password


def mail_configured() -> bool:
    user, password = _mail_creds()
    return bool(user and password)


def send_email(
    to: str,
    subject: str,
    template: str,
    **context,
) -> bool:
    """Send a branded HTML email. Returns True if sent successfully."""
    if not to:
        return False
    try:
        html = render_template(
            f"emails/{template}.html",
            **context,
            business_name=current_app.config.get("BUSINESS_NAME", "Mobile Clinic"),
        )
    except Exception as e:
        logger.error("Email template render failed (%s): %s", template, e)
        _log_email(to, subject, template, "failed", error=f"template: {e}")
        return False

    if not mail_configured():
        logger.error(
            "Mail not configured — set MAIL_USERNAME and MAIL_PASSWORD (Gmail App Password) in .env"
        )
        _log_email(to, subject, template, "failed", error="MAIL_USERNAME/PASSWORD not set")
        # Dev convenience: log OTP/password to server log
        if current_app.debug:
            logger.warning("DEV email to %s | %s | context keys=%s", to, subject, list(context.keys()))
            if context.get("otp"):
                logger.warning("DEV OTP for %s: %s", to, context.get("otp"))
            if context.get("password"):
                logger.warning("DEV seller password for %s: %s / user=%s", to, context.get("password"), context.get("username"))
        return False

    # Prefer Flask-Mail; fall back to raw SMTP if it fails
    try:
        msg = Message(
            subject=subject,
            recipients=[to],
            html=html,
            sender=current_app.config.get("MAIL_DEFAULT_SENDER")
            or current_app.config.get("MAIL_USERNAME"),
        )
        mail.send(msg)
        _log_email(
            to,
            subject,
            template,
            "sent",
            related_type=context.get("related_type"),
            related_id=context.get("related_id"),
        )
        logger.info("Email sent to %s: %s", to, subject)
        return True
    except Exception as e:
        logger.error("Flask-Mail failed to %s: %s — trying raw SMTP", to, e)

    try:
        return _send_raw_smtp(to, subject, html, template, context)
    except Exception as e2:
        logger.error("Raw SMTP also failed to %s: %s", to, e2)
        _log_email(to, subject, template, "failed", error=str(e2), related_type=context.get("related_type"), related_id=context.get("related_id"))
        return False


def _send_raw_smtp(to: str, subject: str, html: str, template: str, context: dict) -> bool:
    server = current_app.config.get("MAIL_SERVER", "smtp.gmail.com")
    port = int(current_app.config.get("MAIL_PORT", 587))
    username = current_app.config.get("MAIL_USERNAME", "").strip()
    password = current_app.config.get("MAIL_PASSWORD", "").strip()
    use_tls = current_app.config.get("MAIL_USE_TLS", True)
    use_ssl = current_app.config.get("MAIL_USE_SSL", False)
    sender = current_app.config.get("MAIL_DEFAULT_SENDER") or username

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender if isinstance(sender, str) else username
    msg["To"] = to
    msg.attach(MIMEText(html, "html", "utf-8"))

    if use_ssl or port == 465:
        smtp = smtplib.SMTP_SSL(server, port, timeout=30)
    else:
        smtp = smtplib.SMTP(server, port, timeout=30)
        smtp.ehlo()
        if use_tls:
            smtp.starttls()
            smtp.ehlo()
    try:
        smtp.login(username, password)
        smtp.sendmail(username, [to], msg.as_string())
    finally:
        try:
            smtp.quit()
        except Exception:
            pass
    _log_email(to, subject, template, "sent", related_type=context.get("related_type"), related_id=context.get("related_id"))
    logger.info("Email sent via raw SMTP to %s: %s", to, subject)
    return True


def send_otp_email(email: str, otp: str, full_name: str) -> bool:
    return send_email(
        to=email,
        subject=f"Your Mobile Clinic Verification Code: {otp}",
        template="otp",
        full_name=full_name,
        otp=otp,
        expiry_minutes=current_app.config.get("OTP_EXPIRY_MINUTES", 10),
    )


def send_order_confirmation(order: dict, items: list, tracking_url: str) -> bool:
    email = order.get("guest_email") or order.get("email")
    if not email:
        return False
    return send_email(
        to=email,
        subject=f"Order Confirmed — {order['order_id']} | Mobile Clinic",
        template="order_confirmation",
        order=order,
        items=items,
        tracking_url=tracking_url,
        related_type="order",
        related_id=order["order_id"],
    )


def send_repair_confirmation(ticket: dict, tracking_url: str) -> bool:
    email = ticket.get("guest_email") or ticket.get("email")
    if not email:
        return False
    return send_email(
        to=email,
        subject=f"Repair Ticket {ticket['ticket_id']} Received | Mobile Clinic",
        template="repair_confirmation",
        ticket=ticket,
        tracking_url=tracking_url,
        related_type="repair",
        related_id=ticket["ticket_id"],
    )


def send_seller_credentials(
    email: str,
    username: str,
    password: str,
    full_name: str,
    login_url: str = None,
    seller_panel_url: str = None,
) -> bool:
    base = (current_app.config.get("APP_BASE_URL") or "http://127.0.0.1:5000").rstrip("/")
    login_url = login_url or f"{base}/auth/login"
    seller_panel_url = seller_panel_url or f"{base}/dashboard/seller"
    return send_email(
        to=email,
        subject="Your Mobile Clinic Seller Account — Login Details",
        template="seller_credentials",
        full_name=full_name,
        username=username,
        password=password,
        login_url=login_url,
        seller_panel_url=seller_panel_url,
    )


def send_commission_reminder(email: str, seller_name: str, amount: float, deadline: str) -> bool:
    return send_email(
        to=email,
        subject=f"Commission Payment Reminder — NPR {amount:,.0f} Due",
        template="commission_reminder",
        seller_name=seller_name,
        amount=amount,
        deadline=deadline,
    )


def send_payment_verified(email: str, amount: float) -> bool:
    return send_email(
        to=email,
        subject="Commission Payment Verified | Mobile Clinic",
        template="payment_verified",
        amount=amount,
    )
