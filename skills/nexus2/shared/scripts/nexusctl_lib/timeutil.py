from datetime import datetime, timedelta, timezone
from typing import Any

from .constants import DEFAULT_LEASE_MINUTES


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(value: Any) -> datetime | None:
    if not value or str(value).lower() in ("null", "none"):
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def lease_until_iso(minutes: int = DEFAULT_LEASE_MINUTES) -> str:
    return (
        now_utc() + timedelta(minutes=minutes)
    ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
