from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from flask import current_app
import ipaddress
from urllib.parse import urlparse
import socket


def hash_password(password: str) -> str:
    return generate_password_hash(password, method="scrypt")


def verify_password(password_hash: str, password: str) -> bool:
    return check_password_hash(password_hash, password)


def generate_reset_token(user_id: int, email: str) -> str:
    s = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    return s.dumps({"user_id": user_id, "email": email}, salt="password-reset")


def verify_reset_token(token: str, max_age: int = 3600):
    s = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    try:
        data = s.loads(token, salt="password-reset", max_age=max_age)
        return data
    except (BadSignature, SignatureExpired):
        return None


def is_private_or_local_url(url: str) -> bool:
    """SSRF protection: block private IPs, localhost, metadata endpoints."""
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return True
        hostname_lower = hostname.lower()
        blocked_hosts = {
            "localhost", "127.0.0.1", "0.0.0.0", "::1",
            "metadata.google.internal", "169.254.169.254",
            "metadata", "instance-data",
        }
        if hostname_lower in blocked_hosts:
            return True
        if hostname_lower.endswith(".local") or hostname_lower.endswith(".internal"):
            return True
        try:
            ip = socket.gethostbyname(hostname)
            ip_obj = ipaddress.ip_address(ip)
            if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_reserved:
                return True
        except (socket.gaierror, ValueError):
            return True
        return False
    except Exception:
        return True


def validate_image_content(file_storage) -> bool:
    """Basic magic-byte check for common image formats."""
    try:
        header = file_storage.read(16)
        file_storage.seek(0)
        # JPEG
        if header[:3] == b"\xff\xd8\xff":
            return True
        # PNG
        if header[:8] == b"\x89PNG\r\n\x1a\n":
            return True
        # GIF
        if header[:6] in (b"GIF87a", b"GIF89a"):
            return True
        # WebP
        if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
            return True
        return False
    except Exception:
        return False
