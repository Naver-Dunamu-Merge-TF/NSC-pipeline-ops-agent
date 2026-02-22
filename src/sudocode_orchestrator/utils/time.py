from __future__ import annotations

from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


def parse_pipeline_ts(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError(f"Invalid pipeline timestamp format: {value!r}") from exc
    else:
        raise ValueError(f"Invalid pipeline timestamp format: {value!r}")

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def to_utc(value: str | datetime) -> datetime:
    return parse_pipeline_ts(value)


def to_kst(value: str | datetime) -> str:
    converted = to_utc(value).astimezone(KST)
    return converted.strftime("%Y-%m-%d %H:%M KST")
