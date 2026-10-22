"""RFC3339 handling shared by status (``since``) and logs (``ts`` and the time filters)."""

from __future__ import annotations

import re
from datetime import UTC, datetime

_FRACTION_RE = re.compile(r"\.(\d+)")
_MIN_YEAR = 2000


def parse_rfc3339(raw: str | None) -> datetime | None:
    """Parse an RFC3339 string with any fraction width into an aware datetime; ``None`` when unparseable."""
    if not raw:
        return None
    try:
        trimmed = _FRACTION_RE.sub(lambda m: "." + m.group(1)[:6].ljust(6, "0"), raw, count=1)
        parsed = datetime.fromisoformat(trimmed)
    except ValueError:
        return None
    if parsed.year < _MIN_YEAR:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def format_utc(moment: datetime) -> str:
    """Microsecond-precision RFC3339 in UTC with a ``Z`` suffix."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def normalize_timestamp(raw: str | None) -> str | None:
    """RFC3339 with nanoseconds and an offset -> microsecond UTC ``...Z``; ``None`` when unparseable."""
    parsed = parse_rfc3339(raw)
    return format_utc(parsed) if parsed is not None else None
