from datetime import datetime, timezone


def weeks_since(iso_timestamp: str) -> float:
    dt = datetime.fromisoformat(iso_timestamp)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return (now - dt).total_seconds() / (7 * 24 * 3600)
