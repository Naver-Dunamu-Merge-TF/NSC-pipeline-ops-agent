from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from utils.time import parse_pipeline_ts, to_kst, to_utc


def test_parse_pipeline_ts_normalizes_timezone_aware_input_to_utc() -> None:
    parsed = parse_pipeline_ts("2026-02-19T00:03:00+09:00")

    assert parsed == datetime(2026, 2, 18, 15, 3, tzinfo=timezone.utc)


def test_parse_pipeline_ts_treats_naive_input_as_utc() -> None:
    parsed = parse_pipeline_ts("2026-02-18T15:03:00")

    assert parsed == datetime(2026, 2, 18, 15, 3, tzinfo=timezone.utc)


def test_to_utc_handles_timezone_aware_datetime_with_date_rollover() -> None:
    kst = timezone(timedelta(hours=9))
    converted = to_utc(datetime(2026, 2, 19, 0, 3, tzinfo=kst))

    assert converted == datetime(2026, 2, 18, 15, 3, tzinfo=timezone.utc)


def test_to_utc_handles_timezone_aware_string_with_date_rollover() -> None:
    converted = to_utc("2026-02-19T00:03:00+09:00")

    assert converted == datetime(2026, 2, 18, 15, 3, tzinfo=timezone.utc)


def test_to_kst_formats_exact_display_string_at_midnight_boundary() -> None:
    value = datetime(2026, 2, 18, 15, 3, tzinfo=timezone.utc)

    assert to_kst(value) == "2026-02-19 00:03 KST"


def test_to_kst_accepts_naive_input() -> None:
    assert to_kst("2026-02-18T15:03:00") == "2026-02-19 00:03 KST"


def test_parse_pipeline_ts_raises_clear_exception_for_invalid_format() -> None:
    with pytest.raises(ValueError, match="Invalid pipeline timestamp format"):
        parse_pipeline_ts("2026/02/18 15:03:00")
