"""Website settings with simple in-memory cache to reduce Turso round-trips."""
from app import db

_cache = None
_cache_ts = 0
CACHE_TTL_SEC = 60


def get_settings() -> dict:
    global _cache, _cache_ts
    import time
    now = time.time()
    if _cache is not None and (now - _cache_ts) < CACHE_TTL_SEC:
        return _cache
    try:
        rows = db.fetch_all("SELECT setting_key, setting_value FROM website_settings")
        _cache = {r["setting_key"]: r["setting_value"] for r in (rows or [])}
    except Exception:
        _cache = _cache or {}
    _cache_ts = now
    return _cache


def get_setting(key: str, default=None):
    settings = get_settings()
    return settings.get(key, default)


def set_setting(key: str, value: str, user_id=None):
    global _cache, _cache_ts
    existing = db.fetch_one("SELECT id FROM website_settings WHERE setting_key = ?", (key,))
    if existing:
        db.execute(
            "UPDATE website_settings SET setting_value = ?, updated_at = datetime('now'), updated_by = ? WHERE setting_key = ?",
            (value, user_id, key),
        )
    else:
        db.execute(
            "INSERT INTO website_settings (setting_key, setting_value, updated_by) VALUES (?, ?, ?)",
            (key, value, user_id),
        )
    _cache = None
    _cache_ts = 0


def clear_settings_cache():
    global _cache, _cache_ts
    _cache = None
    _cache_ts = 0
