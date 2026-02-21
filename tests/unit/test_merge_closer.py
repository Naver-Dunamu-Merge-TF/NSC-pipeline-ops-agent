from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from sudocode_orchestrator.merge_closer import MergeClosePayload, apply_merge_close


@dataclass
class FakeGateway:
    issues: dict[str, dict[str, Any]]
    status_updates: list[tuple[str, str]]
    feedback: list[tuple[str, str]]
    events: list[tuple[str, str, str]] = field(default_factory=list)

    def show_issue(self, issue_id: str) -> dict[str, Any]:
        return self.issues[issue_id]

    def set_issue_status(self, issue_id: str, status: str) -> None:
        self.status_updates.append((issue_id, status))
        self.events.append(("status", issue_id, status))
        self.issues[issue_id]["status"] = status

    def add_feedback(self, issue_id: str, content: str) -> None:
        self.feedback.append((issue_id, content))
        marker = ""
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict) and isinstance(parsed.get("marker"), str):
                marker = parsed["marker"]
        except json.JSONDecodeError:
            marker = ""
        self.events.append(("feedback", issue_id, marker))


def _payload(issue_id: str = "i-abc1", merged: bool = True) -> MergeClosePayload:
    return MergeClosePayload(
        issue_id=issue_id,
        pr_url="https://github.com/acme/repo/pull/14",
        merge_sha="deadbeef",
        merged_at="2026-02-21T12:45:00Z",
        merged=merged,
        source="workflow",
    )


def _review_gate_marker(timestamp: str = "2026-02-21T12:00:00Z") -> dict[str, Any]:
    return {
        "event_type": "SESSION_DONE",
        "stage": "REVIEW_GATE",
        "status": "NEEDS_REVIEW",
        "timestamp": timestamp,
    }


def test_close_allowed_only_from_needs_review() -> None:
    gateway = FakeGateway(
        issues={
            "i-abc1": {
                "issue_id": "i-abc1",
                "status": "in_progress",
                "merged": True,
                "feedback_history": [_review_gate_marker()],
                "title": "Regular task",
            }
        },
        status_updates=[],
        feedback=[],
    )

    result = apply_merge_close(gateway=gateway, payload=_payload())

    assert result.applied is False
    assert result.feedback_marker == "MERGE_CLOSE_REJECTED"
    assert "needs_review" in result.reason
    assert gateway.status_updates == []


def test_missing_review_gate_marker_rejects_close() -> None:
    gateway = FakeGateway(
        issues={
            "i-abc1": {
                "issue_id": "i-abc1",
                "status": "needs_review",
                "merged": True,
                "feedback_history": [
                    {
                        "event_type": "QUALITY_REVIEW_PASS",
                        "stage": "QUALITY_REVIEW",
                        "status": "PASS",
                        "timestamp": "2026-02-21T12:10:00Z",
                    }
                ],
                "title": "Regular task",
            }
        },
        status_updates=[],
        feedback=[],
    )

    result = apply_merge_close(gateway=gateway, payload=_payload())

    assert result.applied is False
    assert result.feedback_marker == "MERGE_CLOSE_REJECTED"
    assert "review-gate marker" in result.reason
    assert gateway.status_updates == []


def test_valid_review_gate_marker_in_history_allows_close() -> None:
    gateway = FakeGateway(
        issues={
            "i-abc1": {
                "issue_id": "i-abc1",
                "status": "needs_review",
                "merged": True,
                "feedback_history": [
                    _review_gate_marker(timestamp="2026-02-21T12:00:00Z"),
                    {
                        "event_type": "COMMENT",
                        "timestamp": "2026-02-21T12:30:00Z",
                    },
                ],
                "title": "Regular task",
            }
        },
        status_updates=[],
        feedback=[],
    )

    result = apply_merge_close(gateway=gateway, payload=_payload())

    assert result.applied is True
    assert result.feedback_marker == "MERGE_CLOSE_APPLIED"
    assert gateway.status_updates == [("i-abc1", "closed")]


def test_review_gate_marker_older_than_last_reopen_rejects_close() -> None:
    gateway = FakeGateway(
        issues={
            "i-abc1": {
                "issue_id": "i-abc1",
                "status": "needs_review",
                "merged": True,
                "feedback_history": [
                    _review_gate_marker(timestamp="2026-02-21T12:00:00Z"),
                    {
                        "event_type": "SESSION_REOPENED",
                        "status": "OPEN",
                        "timestamp": "2026-02-21T12:30:00Z",
                    },
                ],
                "title": "Regular task",
            }
        },
        status_updates=[],
        feedback=[],
    )

    result = apply_merge_close(gateway=gateway, payload=_payload())

    assert result.applied is False
    assert result.feedback_marker == "MERGE_CLOSE_REJECTED"
    assert "older than last reopen" in result.reason
    assert gateway.status_updates == []


def test_merge_metadata_feedback_written_on_close() -> None:
    gateway = FakeGateway(
        issues={
            "i-abc1": {
                "issue_id": "i-abc1",
                "status": "needs_review",
                "merged": True,
                "feedback_history": [_review_gate_marker()],
                "title": "Regular task",
            }
        },
        status_updates=[],
        feedback=[],
    )

    result = apply_merge_close(gateway=gateway, payload=_payload())

    assert result.applied is True
    assert gateway.events[:3] == [
        ("feedback", "i-abc1", "MERGE_EVIDENCE_RECORDED"),
        ("status", "i-abc1", "closed"),
        ("feedback", "i-abc1", "MERGE_CLOSE_APPLIED"),
    ]
    issue_id, content = gateway.feedback[0]
    assert issue_id == "i-abc1"
    feedback_payload = json.loads(content)
    assert feedback_payload["marker"] == "MERGE_EVIDENCE_RECORDED"
    assert feedback_payload["pr_url"] == "https://github.com/acme/repo/pull/14"
    assert feedback_payload["merge_sha"] == "deadbeef"
    assert feedback_payload["merged_at"] == "2026-02-21T12:45:00Z"
    assert feedback_payload["source"] == "workflow"

    issue_id, content = gateway.feedback[-1]
    assert issue_id == "i-abc1"
    feedback_payload = json.loads(content)
    assert feedback_payload["marker"] == "MERGE_CLOSE_APPLIED"
    assert feedback_payload["pr_url"] == "https://github.com/acme/repo/pull/14"
    assert feedback_payload["merge_sha"] == "deadbeef"
    assert feedback_payload["merged_at"] == "2026-02-21T12:45:00Z"
    assert feedback_payload["source"] == "workflow"


def test_already_closed_is_idempotent_skip_with_marker() -> None:
    gateway = FakeGateway(
        issues={
            "i-abc1": {
                "issue_id": "i-abc1",
                "status": "closed",
                "merged": False,
                "feedback_history": [
                    _review_gate_marker(),
                    {
                        "marker": "MERGE_CLOSE_APPLIED",
                        "timestamp": "2026-02-21T12:41:00Z",
                    },
                ],
                "title": "Regular task",
            }
        },
        status_updates=[],
        feedback=[],
    )

    result = apply_merge_close(gateway=gateway, payload=_payload())

    assert result.applied is False
    assert result.feedback_marker == "MERGE_CLOSE_SKIPPED_ALREADY_CLOSED"
    assert gateway.status_updates == []
    _, content = gateway.feedback[-1]
    assert json.loads(content)["marker"] == "MERGE_CLOSE_SKIPPED_ALREADY_CLOSED"


def test_already_closed_backfills_missing_merge_close_applied_marker() -> None:
    gateway = FakeGateway(
        issues={
            "i-abc1": {
                "issue_id": "i-abc1",
                "status": "closed",
                "merged": True,
                "feedback_history": [
                    {
                        "marker": "MERGE_EVIDENCE_RECORDED",
                        "timestamp": "2026-02-21T12:40:00Z",
                    }
                ],
                "title": "Regular task",
            }
        },
        status_updates=[],
        feedback=[],
    )

    result = apply_merge_close(gateway=gateway, payload=_payload())

    assert result.applied is False
    assert result.feedback_marker == "MERGE_CLOSE_SKIPPED_ALREADY_CLOSED"
    assert gateway.status_updates == []
    first_issue_id, first_content = gateway.feedback[0]
    assert first_issue_id == "i-abc1"
    first_written = json.loads(first_content)
    assert first_written["marker"] == "MERGE_CLOSE_APPLIED"
    assert "backfill" in first_written["reason"]
    last_issue_id, last_content = gateway.feedback[-1]
    assert last_issue_id == "i-abc1"
    last_written = json.loads(last_content)
    assert last_written["marker"] == "MERGE_CLOSE_SKIPPED_ALREADY_CLOSED"


def test_closing_fix_child_closes_linked_overflow_parent_in_needs_review() -> None:
    gateway = FakeGateway(
        issues={
            "i-fix01": {
                "issue_id": "i-fix01",
                "status": "needs_review",
                "merged": True,
                "feedback_history": [_review_gate_marker()],
                "title": "[FIX] DEV-001: Lock SSOT schema",
                "linked_parents": [{"issue_id": "i-parent1", "type": "related"}],
            },
            "i-parent1": {
                "issue_id": "i-parent1",
                "status": "needs_review",
                "merged": True,
                "feedback_history": [],
                "title": "DEV-001 Lock SSOT schema",
            },
        },
        status_updates=[],
        feedback=[],
    )

    result = apply_merge_close(gateway=gateway, payload=_payload(issue_id="i-fix01"))

    assert result.applied is True
    assert ("i-fix01", "closed") in gateway.status_updates
    assert ("i-parent1", "closed") in gateway.status_updates
    parent_feedback = [
        json.loads(content)
        for issue_id, content in gateway.feedback
        if issue_id == "i-parent1"
    ]
    assert parent_feedback[-1]["marker"] == "OVERFLOW_PARENT_CLOSED_BY_FIX"


def test_fix_child_parent_lookup_falls_back_to_links_shape() -> None:
    gateway = FakeGateway(
        issues={
            "i-fix01": {
                "issue_id": "i-fix01",
                "status": "needs_review",
                "merged": True,
                "feedback_history": [_review_gate_marker()],
                "title": "[FIX] DEV-001: Lock SSOT schema",
                "links": [
                    {
                        "from_id": "i-parent1",
                        "to_id": "i-fix01",
                        "type": "depends-on",
                    }
                ],
            },
            "i-parent1": {
                "issue_id": "i-parent1",
                "status": "needs_review",
                "merged": True,
                "feedback_history": [],
                "title": "DEV-001 Lock SSOT schema",
            },
        },
        status_updates=[],
        feedback=[],
    )

    result = apply_merge_close(gateway=gateway, payload=_payload(issue_id="i-fix01"))

    assert result.applied is True
    assert ("i-parent1", "closed") in gateway.status_updates


def test_fix_child_parent_lookup_falls_back_to_relationships_shape() -> None:
    gateway = FakeGateway(
        issues={
            "i-fix01": {
                "issue_id": "i-fix01",
                "status": "needs_review",
                "merged": True,
                "feedback_history": [_review_gate_marker()],
                "title": "[FIX] DEV-001: Lock SSOT schema",
                "relationships": {
                    "incoming": [
                        {
                            "from_id": "i-parent1",
                            "to_id": "i-fix01",
                            "relationship_type": "depends-on",
                        }
                    ]
                },
            },
            "i-parent1": {
                "issue_id": "i-parent1",
                "status": "needs_review",
                "merged": True,
                "feedback_history": [],
                "title": "DEV-001 Lock SSOT schema",
            },
        },
        status_updates=[],
        feedback=[],
    )

    result = apply_merge_close(gateway=gateway, payload=_payload(issue_id="i-fix01"))

    assert result.applied is True
    assert ("i-parent1", "closed") in gateway.status_updates


def test_requires_merged_true_before_close() -> None:
    gateway = FakeGateway(
        issues={
            "i-abc1": {
                "issue_id": "i-abc1",
                "status": "needs_review",
                "merged": True,
                "feedback_history": [_review_gate_marker()],
                "title": "Regular task",
            }
        },
        status_updates=[],
        feedback=[],
    )

    result = apply_merge_close(gateway=gateway, payload=_payload(merged=False))

    assert result.applied is False
    assert result.feedback_marker == "MERGE_CLOSE_REJECTED"
    assert "merged=true" in result.reason
    assert gateway.status_updates == []
