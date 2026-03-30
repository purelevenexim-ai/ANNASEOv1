import math
from datetime import datetime

HALF_LIFE_DAYS = 7  # tune this for speed vs stability


def compute_decay_factor(last_seen: str) -> float:
    if not last_seen:
        return 0.5

    if isinstance(last_seen, str):
        try:
            last_seen_dt = datetime.fromisoformat(last_seen)
        except ValueError:
            # fallback for sqlite date formats
            try:
                last_seen_dt = datetime.strptime(last_seen, "%Y-%m-%d %H:%M:%S")
            except Exception:
                return 0.5
    else:
        last_seen_dt = last_seen

    age_days = (datetime.utcnow() - last_seen_dt).total_seconds() / 86400.0
    decay = math.exp(-math.log(2) * age_days / HALF_LIFE_DAYS)
    return max(0.0, min(1.0, decay))
