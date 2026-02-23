from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from utils.time import parse_pipeline_ts, to_kst, to_utc


def test_parse_pipeline_ts_normalizes_timezone_aware_input_to_utc() -> None:
    parsed = parse_pipeline_ts("2026-02-19T00:03:00+09:00")

    assert parsed == datetime(2026, 2, 18, 15, 3, tzinfo=timezone.utc)


def test_parse_pipeline_ts_treats_naive_input_as_utc() -> None:
    parsed = parse_pipeline_ts("2026-02-18T15:03:00")

    assert parsed == datetime(2026, 2, 18, 15, 3, tzinfo=timezone.utc)


def test_parse_pipeline_ts_handles_z_suffix_with_surrounding_whitespace() -> None:
    parsed = parse_pipeline_ts(" \n2026-02-18T15:03:00Z\t ")

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


def test_parse_pipeline_ts_raises_value_error_for_non_string_non_datetime_input() -> (
    None
):
    with pytest.raises(ValueError, match="Invalid pipeline timestamp format"):
        parse_pipeline_ts(123)  # type: ignore[arg-type]


def test_utils_time_exports_work_with_repo_root_only_pythonpath() -> None:
    root = Path(__file__).resolve().parents[2]
    script = (
        "from utils.time import parse_pipeline_ts, to_kst, to_utc; "
        "parsed = parse_pipeline_ts('2026-02-18T15:03:00Z'); "
        "utc = to_utc('2026-02-18T15:03:00Z'); "
        "kst = to_kst('2026-02-18T15:03:00Z'); "
        "assert parsed.isoformat() == '2026-02-18T15:03:00+00:00'; "
        "assert utc.isoformat() == '2026-02-18T15:03:00+00:00'; "
        "assert kst == '2026-02-19 00:03 KST'"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root)
    subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def test_parse_pipeline_ts_is_identical_across_root_src_pythonpath_orders() -> None:
    root = Path(__file__).resolve().parents[2]
    src = root / "src"
    script = (
        "import json; "
        "from utils.time import parse_pipeline_ts, to_kst, to_utc; "
        "import utils.time as time_module; "
        "parsed = parse_pipeline_ts('2026-02-18T15:03:00Z'); "
        "utc = to_utc('2026-02-18T15:03:00Z'); "
        "kst = to_kst('2026-02-18T15:03:00Z'); "
        "print(json.dumps({'iso': parsed.isoformat(), 'utc': utc.isoformat(), 'kst': kst, 'module_file': time_module.__file__}))"
    )

    def run_with_path(path_value: str) -> dict[str, str]:
        env = dict(os.environ)
        env["PYTHONPATH"] = path_value
        proc = subprocess.run(
            [sys.executable, "-c", script],
            cwd=root / "tests",
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(proc.stdout)

    root_then_src = run_with_path(f"{root}{os.pathsep}{src}")
    src_then_root = run_with_path(f"{src}{os.pathsep}{root}")

    assert root_then_src["iso"] == "2026-02-18T15:03:00+00:00"
    assert src_then_root["iso"] == "2026-02-18T15:03:00+00:00"
    assert root_then_src["iso"] == src_then_root["iso"]
    assert root_then_src["utc"] == "2026-02-18T15:03:00+00:00"
    assert src_then_root["utc"] == "2026-02-18T15:03:00+00:00"
    assert root_then_src["utc"] == src_then_root["utc"]
    assert root_then_src["kst"] == "2026-02-19 00:03 KST"
    assert src_then_root["kst"] == "2026-02-19 00:03 KST"
    assert root_then_src["kst"] == src_then_root["kst"]
    assert root_then_src["module_file"] != src_then_root["module_file"]
