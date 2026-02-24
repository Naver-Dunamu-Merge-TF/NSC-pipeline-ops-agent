from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any


def build_pipeline_state_query(pipeline: str) -> dict[str, Any]:
    return {
        "sql": (
            "SELECT pipeline_name, CAST(NULL AS STRING) AS status, last_success_ts, last_processed_end, last_run_id "
            "FROM gold.pipeline_state "
            "WHERE pipeline_name = %(pipeline_name)s"
        ),
        "params": {"pipeline_name": pipeline},
        "result_shape": "single",
    }


def build_dq_status_query(run_id: str, window_start_ts: str) -> dict[str, Any]:
    return {
        "sql": (
            "SELECT source_table, dq_tag, severity, run_id, window_end_ts, date_kst "
            "FROM silver.dq_status "
            "WHERE run_id = %(run_id)s "
            "AND window_end_ts >= %(window_start_ts)s"
        ),
        "params": {
            "run_id": run_id,
            "window_start_ts": window_start_ts,
        },
        "result_shape": "list",
    }


def build_exception_ledger_query(run_id: str, window_start_ts: str) -> dict[str, Any]:
    return {
        "sql": (
            "SELECT severity, domain, exception_type, source_table, metric, metric_value, run_id, generated_at "
            "FROM gold.exception_ledger "
            "WHERE domain = %(domain)s "
            "AND run_id = %(run_id)s "
            "AND generated_at >= %(window_start_ts)s"
        ),
        "params": {
            "domain": "dq",
            "run_id": run_id,
            "window_start_ts": window_start_ts,
        },
        "result_shape": "list",
    }


def collect_pipeline_context(pipeline: str, run_id: str | None) -> dict[str, Any]:
    if run_id is None:
        raise ValueError("run_id is required")

    window_start_ts = (datetime.now(tz=UTC) - timedelta(hours=24)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    return {
        "pipeline_state": build_pipeline_state_query(pipeline),
        "dq_status": build_dq_status_query(
            run_id=run_id, window_start_ts=window_start_ts
        ),
        "exception_ledger": build_exception_ledger_query(
            run_id=run_id,
            window_start_ts=window_start_ts,
        ),
    }
