from __future__ import annotations

from typing import Any

import pytest

import graph.graph as graph_module
from graph.nodes import collect


def _base_state() -> dict[str, Any]:
    return {
        "pipeline": "pipeline_silver",
        "run_id": "run-017",
        "pipeline_states": {
            "pipeline_silver": {
                "status": "success",
                "last_success_ts": "2026-02-25T00:10:00+00:00",
            }
        },
        "detected_issues": [{"type": "critical_dq", "severity": "critical"}],
        "exception_ledger": [
            {
                "severity": "CRITICAL",
                "domain": "dq",
                "exception_type": "SchemaViolation",
                "source_table": "silver.orders",
            }
        ],
        "dq_status": [
            {
                "severity": "CRITICAL",
                "dq_tag": "SOURCE_STALE",
                "source_table": "silver.orders",
            },
            {
                "severity": "WARN",
                "dq_tag": "DUP_SUSPECTED",
                "source_table": "silver.orders",
            },
        ],
        "bad_records": [
            {
                "source_table": "silver.orders",
                "reason": '{"field":"amount","detail":"amount <= 0"}',
                "record_json": '{"id":1,"amount":0}',
            }
        ],
    }


def test_collect_populates_exceptions_tags_and_summary_shape() -> None:
    result = collect.run(_base_state())

    assert result["exceptions"] == [
        {
            "severity": "CRITICAL",
            "domain": "dq",
            "exception_type": "SchemaViolation",
            "source_table": "silver.orders",
        }
    ]
    assert result["dq_tags"] == ["DUP_SUSPECTED", "SOURCE_STALE"]
    assert result["bad_records_summary"] == {
        "total_records": 1,
        "type_count": 1,
        "types_truncated": False,
        "types": [
            {
                "source_table": "silver.orders",
                "field": "amount",
                "reason": "amount <= 0",
                "count": 1,
                "samples_truncated": False,
                "samples": [{"record_json": '{"id":1,"amount":0}'}],
            }
        ],
    }


def test_collect_output_keeps_dq_tag_only_analyze_skip_path() -> None:
    state = _base_state()
    state["pipeline_states"] = {
        "pipeline_silver": {
            "status": "success",
            "last_success_ts": "2026-02-25T00:10:00+00:00",
        }
    }
    state["exception_ledger"] = []
    state["bad_records"] = []

    updates = collect.run(state)
    route_key = graph_module._route_collect({**state, **updates})

    assert updates["exceptions"] == []
    assert updates["dq_tags"] == ["DUP_SUSPECTED", "SOURCE_STALE"]
    assert route_key == "triage"


def test_collect_normalizes_dq_tags_as_string_only_dedup_and_sorted() -> None:
    state = _base_state()
    state["dq_status"] = [
        {"dq_tag": "SOURCE_STALE"},
        {"dq_tag": ""},
        {"dq_tag": "DUP_SUSPECTED"},
        {"dq_tag": "SOURCE_STALE"},
        {"dq_tag": None},
        {"dq_tag": 7},
        "not-a-dict",
    ]

    updates = collect.run(state)

    assert updates["dq_tags"] == ["DUP_SUSPECTED", "SOURCE_STALE"]


def test_collect_classifies_failure_for_retry_vs_escalation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _base_state()

    def _raise_timeout(_rows: list[dict[str, Any]]) -> dict[str, Any]:
        raise TimeoutError("temporary collector timeout")

    monkeypatch.setattr(collect, "summarize_bad_records", _raise_timeout)

    with pytest.raises(
        collect.CollectTransientError, match="temporary collector timeout"
    ):
        collect.run(state)

    state["dq_status"] = "not-a-list"
    with pytest.raises(collect.CollectPermanentError, match="dq_status must be a list"):
        collect.run(state)


def test_collect_classifies_connection_error_as_transient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _base_state()

    def _raise_connection_error(_rows: list[dict[str, Any]]) -> dict[str, Any]:
        raise ConnectionError("temporary collector connection issue")

    monkeypatch.setattr(collect, "summarize_bad_records", _raise_connection_error)

    with pytest.raises(
        collect.CollectTransientError, match="temporary collector connection issue"
    ):
        collect.run(state)


def test_collect_classifies_non_network_error_as_permanent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _base_state()

    def _raise_non_network_error(_rows: list[dict[str, Any]]) -> dict[str, Any]:
        raise ValueError("unexpected collector format")

    monkeypatch.setattr(collect, "summarize_bad_records", _raise_non_network_error)

    with pytest.raises(
        collect.CollectPermanentError, match="unexpected collector format"
    ):
        collect.run(state)
