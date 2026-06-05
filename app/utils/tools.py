from datetime import datetime, timezone


def standard_now() -> str:
    return datetime.now(timezone.utc).isoformat()
