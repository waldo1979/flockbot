from datetime import datetime, timezone


def decay_weight(age_weeks: float) -> float:
    if age_weeks <= 2:
        return 1.0
    elif age_weeks <= 4:
        return 0.75
    elif age_weeks <= 6:
        return 0.50
    elif age_weeks <= 8:
        return 0.25
    else:
        return 0.0


def weeks_since(iso_timestamp: str) -> float:
    dt = datetime.fromisoformat(iso_timestamp)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return (now - dt).total_seconds() / (7 * 24 * 3600)
