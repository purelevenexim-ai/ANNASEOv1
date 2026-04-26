"""
Reward engine — aggregates content_events into metrics and computes
a reward signal for the humanization bandit.

Also provides record_event() with input validation and GDPR-safe
IP hashing for use by the tracking endpoint.
"""
import hashlib
import logging
import re
from typing import Dict, Optional

log = logging.getLogger("annaseo.humanize.reward")

# ── Allowed event types (whitelist) ──────────────────────────────────────────

ALLOWED_EVENTS = frozenset({
    "page_view",
    "scroll_50",
    "scroll_75",
    "time_spent",
    "cta_click",
    "conversion",
})

# Salt for IP hashing — keeps hashes site-specific and non-reversible
_IP_SALT = "annaseo_v2_ip_salt_2026"

# ── Input validation ──────────────────────────────────────────────────────────

_ARTICLE_ID_RE = re.compile(r'^[a-zA-Z0-9_-]{1,100}$')


def validate_article_id(article_id: str) -> bool:
    return bool(_ARTICLE_ID_RE.match(article_id or ""))


def hash_ip(ip: str) -> str:
    """Return SHA-256(ip + salt) — GDPR-safe, never stores the raw IP."""
    raw = (ip or "") + _IP_SALT
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


# ── Event recording ───────────────────────────────────────────────────────────

def record_event(
    article_id: str,
    event_type: str,
    value: float,
    ip: str,
    db,
) -> bool:
    """Insert a single content event into the DB.

    Returns True on success, False on validation failure or DB error.
    `db` is a raw sqlite3 connection (from get_db()).
    """
    if event_type not in ALLOWED_EVENTS:
        log.warning("record_event: rejected unknown event_type %r", event_type)
        return False
    if not validate_article_id(article_id):
        log.warning("record_event: rejected invalid article_id %r", article_id)
        return False

    # Clamp value to a reasonable range to prevent log pollution
    safe_value = max(0.0, min(float(value or 0), 86400.0))
    ip_hash = hash_ip(ip)

    try:
        db.execute(
            "INSERT INTO content_events(article_id, event_type, value, ip_hash) VALUES(?,?,?,?)",
            (article_id, event_type, safe_value, ip_hash),
        )
        db.commit()
        return True
    except Exception as e:
        log.warning("record_event DB error: %s", e)
        return False


# ── Metrics aggregation ───────────────────────────────────────────────────────

def compute_metrics(article_id: str, db) -> Dict:
    """Aggregate content_events for an article into engagement metrics.

    Returns a dict with keys:
        page_views, unique_views, avg_time_seconds, scroll_50_rate,
        scroll_75_rate, cta_clicks, conversions, conversion_rate
    """
    rows = db.execute(
        "SELECT event_type, value FROM content_events WHERE article_id = ?",
        (article_id,),
    ).fetchall()

    page_views = 0
    unique_ips: set = set()
    time_values = []
    scroll_50_hits = 0
    scroll_75_hits = 0
    cta_clicks = 0
    conversions = 0

    # Count by event type
    type_counts: Dict[str, int] = {}
    for event_type, value in rows:
        type_counts[event_type] = type_counts.get(event_type, 0) + 1
        if event_type == "page_view":
            page_views += 1
        elif event_type == "time_spent":
            time_values.append(float(value or 0))
        elif event_type == "scroll_50":
            scroll_50_hits += 1
        elif event_type == "scroll_75":
            scroll_75_hits += 1
        elif event_type == "cta_click":
            cta_clicks += 1
        elif event_type == "conversion":
            conversions += 1

    avg_time = sum(time_values) / len(time_values) if time_values else 0.0
    scroll_50_rate = scroll_50_hits / page_views if page_views else 0.0
    scroll_75_rate = scroll_75_hits / page_views if page_views else 0.0
    conversion_rate = conversions / page_views if page_views else 0.0

    return {
        "page_views": page_views,
        "avg_time_seconds": round(avg_time, 1),
        "scroll_50_rate": round(scroll_50_rate, 3),
        "scroll_75_rate": round(scroll_75_rate, 3),
        "cta_clicks": cta_clicks,
        "conversions": conversions,
        "conversion_rate": round(conversion_rate, 4),
        "event_counts": type_counts,
    }


# ── Reward function ───────────────────────────────────────────────────────────

def compute_reward(
    metrics: Dict,
    ai_reduction: float = 0.0,
) -> float:
    """Combine engagement metrics and AI score improvement into a single reward.

    Weights (sum to 1.0):
        conversion_rate  0.40
        ai_reduction     0.30  (0–100 scale, normalized)
        avg_time         0.20  (normalized to 0–300s window)
        scroll_depth     0.10  (uses scroll_75_rate as proxy)

    Returns float in [0, 100].
    """
    conversion_score = min(1.0, metrics.get("conversion_rate", 0.0) * 100)  # scale to ~0-1
    ai_score = min(1.0, max(0.0, ai_reduction / 100.0))

    # Normalize avg time: 180s → 1.0 (anything above is capped)
    avg_time = metrics.get("avg_time_seconds", 0.0)
    time_score = min(1.0, avg_time / 180.0)

    scroll_score = metrics.get("scroll_75_rate", 0.0)

    reward = (
        0.40 * conversion_score +
        0.30 * ai_score +
        0.20 * time_score +
        0.10 * scroll_score
    ) * 100.0

    return round(reward, 2)
