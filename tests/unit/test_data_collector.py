from __future__ import annotations

from datetime import datetime as real_datetime

import pytest

import tools.data_collector as data_collector
from tools.data_collector import (
    build_dq_status_query,
    build_exception_ledger_query,
    collect_pipeline_context,
    build_pipeline_state_query,
)


def test_build_pipeline_state_query_uses_pipeline_filter() -> None:
    result = build_pipeline_state_query("pipeline_silver")

    assert result == {
        "sql": (
            "SELECT pipeline_name, CAST(NULL AS STRING) AS status, last_success_ts, last_processed_end, last_run_id "
            "FROM gold.pipeline_state "
            "WHERE pipeline_name = %(pipeline_name)s"
        ),
        "params": {"pipeline_name": "pipeline_silver"},
        "result_shape": "single",
    }


def test_build_dq_status_query_uses_run_id_and_window_filters() -> None:
    result = build_dq_status_query(
        run_id="run-2026-02-23-001",
        window_start_ts="2026-02-22T00:00:00Z",
    )

    assert result == {
        "sql": (
            "SELECT source_table, dq_tag, severity, run_id, window_end_ts, date_kst "
            "FROM silver.dq_status "
            "WHERE run_id = %(run_id)s "
            "AND window_end_ts >= %(window_start_ts)s"
        ),
        "params": {
            "run_id": "run-2026-02-23-001",
            "window_start_ts": "2026-02-22T00:00:00Z",
        },
        "result_shape": "list",
    }


def test_build_exception_ledger_query_uses_run_id_and_window_filters() -> None:
    result = build_exception_ledger_query(
        run_id="run-2026-02-23-001",
        window_start_ts="2026-02-22T00:00:00Z",
    )

    assert result == {
        "sql": (
            "SELECT severity, domain, exception_type, source_table, metric, metric_value, run_id, generated_at "
            "FROM gold.exception_ledger "
            "WHERE domain = %(domain)s "
            "AND run_id = %(run_id)s "
            "AND generated_at >= %(window_start_ts)s"
        ),
        "params": {
            "domain": "dq",
            "run_id": "run-2026-02-23-001",
            "window_start_ts": "2026-02-22T00:00:00Z",
        },
        "result_shape": "list",
    }


def test_collect_pipeline_context_requires_run_id() -> None:
    with pytest.raises(ValueError, match="run_id is required"):
        collect_pipeline_context("pipeline_silver", None)


def test_collect_pipeline_context_uses_24h_utc_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FrozenDatetime:
        @staticmethod
        def now(*, tz):
            assert tz is data_collector.UTC
            return real_datetime(2026, 2, 23, 12, 0, 0, tzinfo=data_collector.UTC)

    monkeypatch.setattr(data_collector, "datetime", FrozenDatetime)
    result = collect_pipeline_context("pipeline_silver", "run-2026-02-23-001")

    assert result == {
        "pipeline_state": {
            "sql": (
                "SELECT pipeline_name, CAST(NULL AS STRING) AS status, last_success_ts, last_processed_end, last_run_id "
                "FROM gold.pipeline_state "
                "WHERE pipeline_name = %(pipeline_name)s"
            ),
            "params": {"pipeline_name": "pipeline_silver"},
            "result_shape": "single",
        },
        "dq_status": {
            "sql": (
                "SELECT source_table, dq_tag, severity, run_id, window_end_ts, date_kst "
                "FROM silver.dq_status "
                "WHERE run_id = %(run_id)s "
                "AND window_end_ts >= %(window_start_ts)s"
            ),
            "params": {
                "run_id": "run-2026-02-23-001",
                "window_start_ts": "2026-02-22T12:00:00Z",
            },
            "result_shape": "list",
        },
        "exception_ledger": {
            "sql": (
                "SELECT severity, domain, exception_type, source_table, metric, metric_value, run_id, generated_at "
                "FROM gold.exception_ledger "
                "WHERE domain = %(domain)s "
                "AND run_id = %(run_id)s "
                "AND generated_at >= %(window_start_ts)s"
            ),
            "params": {
                "domain": "dq",
                "run_id": "run-2026-02-23-001",
                "window_start_ts": "2026-02-22T12:00:00Z",
            },
            "result_shape": "list",
        },
    }


def test_collect_pipeline_context_query_specs_keep_contract_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FrozenDatetime:
        @staticmethod
        def now(*, tz):
            assert tz is data_collector.UTC
            return real_datetime(2026, 2, 23, 12, 0, 0, tzinfo=data_collector.UTC)

    monkeypatch.setattr(data_collector, "datetime", FrozenDatetime)
    context = collect_pipeline_context("pipeline_silver", "run-2026-02-23-001")

    assert set(context.keys()) == {"pipeline_state", "dq_status", "exception_ledger"}
    for query_spec in context.values():
        assert set(query_spec.keys()) == {"sql", "params", "result_shape"}
        assert isinstance(query_spec["sql"], str)
        assert isinstance(query_spec["params"], dict)
        assert query_spec["result_shape"] in {"single", "list"}

    assert context["pipeline_state"]["result_shape"] == "single"
    assert context["dq_status"]["result_shape"] == "list"
    assert context["exception_ledger"]["result_shape"] == "list"
