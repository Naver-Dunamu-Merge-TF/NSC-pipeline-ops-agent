from __future__ import annotations

import re

from src.utils import incident as src_incident
from utils.incident import make_fingerprint, make_incident_id


def test_make_incident_id_handles_run_id_none_deterministically() -> None:
    first = make_incident_id(
        pipeline="pipeline_silver",
        run_id=None,
        detected_at="2026-02-24T01:00:00Z",
    )
    second = make_incident_id(
        pipeline="pipeline_silver",
        run_id=None,
        detected_at="2026-02-24T01:00:00Z",
    )

    assert first == second
    assert re.fullmatch(r"inc-[0-9a-f]{16}", first)


def test_make_fingerprint_is_order_invariant_for_detected_issues() -> None:
    issues_a = [
        {"type": "cutoff_delay", "severity": "warning", "detail": {"col": "dt"}},
        {"type": "dq_tag", "severity": "critical", "detail": {"tag": "null_spike"}},
    ]
    issues_b = [
        {"severity": "critical", "detail": {"tag": "null_spike"}, "type": "dq_tag"},
        {"detail": {"col": "dt"}, "severity": "warning", "type": "cutoff_delay"},
    ]

    first = make_fingerprint("pipeline_silver", "run-42", issues_a)
    second = make_fingerprint("pipeline_silver", "run-42", issues_b)

    assert first == second


def test_make_fingerprint_handles_empty_detected_issues() -> None:
    fp = make_fingerprint("pipeline_silver", None, [])

    assert re.fullmatch(r"[0-9a-f]{64}", fp)


def test_make_fingerprint_handles_none_detected_issues() -> None:
    fp = make_fingerprint("pipeline_silver", None, None)

    assert re.fullmatch(r"[0-9a-f]{64}", fp)


def test_src_utils_incident_reexports_orchestrator_implementation() -> None:
    from orchestrator.utils import incident as orchestrator_incident

    assert src_incident.make_incident_id is orchestrator_incident.make_incident_id
    assert src_incident.make_fingerprint is orchestrator_incident.make_fingerprint
