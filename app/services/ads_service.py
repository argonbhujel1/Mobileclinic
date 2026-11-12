"""Site advertisements (news-style placements)."""
from app import db
import logging

log = logging.getLogger(__name__)

PLACEMENTS = [
    ("global_top", "Global top bar (all public pages)"),
    ("header_banner", "Below header"),
    ("home_top", "Home — under hero"),
    ("home_mid", "Home — middle (recommended)"),
    ("home_bottom", "Home — before FAQ"),
    ("browse_top", "Browse phones page top"),
    ("sidebar", "Sidebar slot"),
    ("footer_banner", "Above footer"),
]


def _as_dict(row):
    if row is None:
        return None
    if isinstance(row, dict):
        return dict(row)
    try:
        return {k: row[k] for k in row.keys()}
    except Exception:
        try:
            return dict(row)
        except Exception:
            return None


def get_active_ads(placement=None):
    """Active ads; placement=None returns all active."""
    try:
        rows = db.fetch_all("SELECT * FROM ads ORDER BY sort_order ASC, id DESC")
    except Exception as e:
        log.warning("ads query failed: %s", e)
        return []
    if not rows:
        return []

    out = []
    for raw in rows:
        a = _as_dict(raw)
        if not a:
            continue
        # Accept many truthy forms of is_active
        active = a.get("is_active", 1)
        try:
            if int(active) == 0:
                continue
        except Exception:
            if not active:
                continue
        place = str(a.get("placement") or "home_mid").strip()
        a["placement"] = place
        a["image_url"] = (a.get("image_url") or "").strip() or None
        a["link_url"] = (a.get("link_url") or "").strip() or None
        a["title"] = a.get("title") or "Ad"
        if placement and place != str(placement).strip():
            continue
        out.append(a)
    return out


def get_ads_by_placement():
    by = {}
    for a in get_active_ads():
        by.setdefault(a["placement"], []).append(a)
    return by


def record_ad_click(ad_id: int):
    try:
        db.execute(
            "UPDATE ads SET click_count = COALESCE(click_count, 0) + 1 WHERE id = ?",
            (int(ad_id),),
        )
    except Exception:
        pass
