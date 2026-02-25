from __future__ import annotations

from typing import Any

from graph.state import AgentState
from tools.bad_records_summarizer import summarize_bad_records

READ_FIELDS = ("pipeline", "run_id", "pipeline_states", "detected_issues")
WRITE_FIELDS = ("exceptions", "dq_tags", "bad_records_summary")


class CollectError(RuntimeError):
    pass


class CollectTransientError(CollectError):
    pass


class CollectPermanentError(CollectError):
    pass


def _expect_list(value: Any, field_name: str) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    raise CollectPermanentError(f"{field_name} must be a list")


def _collect_exceptions(raw_exceptions: list[Any]) -> list[dict[str, Any]]:
    return [row for row in raw_exceptions if isinstance(row, dict)]


def _collect_dq_tags(raw_dq_status: list[Any]) -> list[str]:
    tags = {
        row.get("dq_tag")
        for row in raw_dq_status
        if isinstance(row, dict) and isinstance(row.get("dq_tag"), str)
    }
    return sorted(tag for tag in tags if tag)


def _classify_collect_error(exc: Exception) -> CollectError:
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return CollectTransientError(str(exc).strip() or exc.__class__.__name__)
    if isinstance(exc, CollectError):
        return exc
    return CollectPermanentError(str(exc).strip() or exc.__class__.__name__)


def run(state: AgentState) -> dict[str, Any]:
    try:
        raw_exceptions = _expect_list(state.get("exception_ledger"), "exception_ledger")
        raw_dq_status = _expect_list(state.get("dq_status"), "dq_status")
        raw_bad_records = _expect_list(state.get("bad_records"), "bad_records")

        exceptions = _collect_exceptions(raw_exceptions)
        dq_tags = _collect_dq_tags(raw_dq_status)
        bad_records_summary = summarize_bad_records(
            [row for row in raw_bad_records if isinstance(row, dict)]
        )
    except Exception as exc:  # pragma: no cover - exercised via classification tests
        raise _classify_collect_error(exc) from exc

    return {
        "exceptions": exceptions,
        "dq_tags": dq_tags,
        "bad_records_summary": bad_records_summary,
    }
