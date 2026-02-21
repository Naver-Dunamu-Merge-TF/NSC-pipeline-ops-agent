from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import cast

import pytest

from sudocode_orchestrator.claim import claim_issue
from sudocode_orchestrator.models import IssueContext
from sudocode_orchestrator.models import SessionOutcome
from sudocode_orchestrator.runner import (
    IssueSessionRunner,
    WorkerPoolDispatcher,
    run_dry_run,
)
from sudocode_orchestrator.snapshot import validate_snapshot


@dataclass(frozen=True)
class ReadyIssue:
    issue_id: str
    priority: int
    ready_at: datetime


class FakeReadyGateway:
    def __init__(self, ready_issues: list[ReadyIssue]) -> None:
        self.ready_issues = ready_issues

    def get_ready_issues(self) -> list[ReadyIssue]:
        return list(self.ready_issues)


class SequencedReadyGateway:
    def __init__(self, polls: list[list[ReadyIssue]]) -> None:
        self._polls = polls
        self._index = 0

    def get_ready_issues(self) -> list[ReadyIssue]:
        if self._index >= len(self._polls):
            return []
        result = list(self._polls[self._index])
        self._index += 1
        return result


class IntegrationGateway:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.status_updates: list[tuple[str, str]] = []
        self.feedback: list[tuple[str, str]] = []
        self.shown_issue_ids: list[str] = []

    def get_ready_issues(self) -> list[ReadyIssue]:
        self.calls.append("get_ready_issues")
        return [
            ReadyIssue(
                issue_id="i-abc1",
                priority=0,
                ready_at=datetime(2026, 2, 21, 12, 0, tzinfo=timezone.utc),
            )
        ]

    def set_issue_status(self, issue_id: str, status: str) -> None:
        self.calls.append(f"set_issue_status:{issue_id}:{status}")
        self.status_updates.append((issue_id, status))

    def add_feedback(self, issue_id: str, content: str) -> None:
        self.calls.append(f"add_feedback:{issue_id}")
        self.feedback.append((issue_id, content))

    def show_issue(self, issue_id: str) -> dict[str, str]:
        self.calls.append(f"show_issue:{issue_id}")
        self.shown_issue_ids.append(issue_id)
        return {
            "issue_id": "i-abc1",
            "manifest_id": "m-001",
            "task_id": "DEV-001",
            "gate_id": "G1",
            "epic_id": "EPIC-01",
            "title": "Lock SSOT schema",
            "depends_on": "-",
            "dod_checklist_full": "* [ ] item 1",
        }


def test_run_dry_run_reports_done_session_to_needs_review() -> None:
    result = run_dry_run()

    assert result["processed_issue"] == "i-dry1"
    assert result["last_event_type"] == "SESSION_DONE"
    assert result["snapshot_count"] >= 3
    assert result["status_updates"][-1] == ("i-dry1", "needs_review")


def test_issue_session_runner_claims_then_renders_prompt_and_runs_orchestrator() -> (
    None
):
    gateway = IntegrationGateway()
    called: list[tuple[str, str]] = []

    class FakeOrchestrator:
        def run_issue(self, **kwargs: object) -> SessionOutcome:
            issue = cast(IssueContext, kwargs["issue"])
            rendered_prompt = kwargs["rendered_prompt"]
            assert isinstance(rendered_prompt, str)
            called.append((issue.issue_id, rendered_prompt))
            return SessionOutcome(final_state="DONE", fix_issue_id=None)

    runner = IssueSessionRunner(
        gateway=gateway,
        orchestrator=FakeOrchestrator(),
        orchestrator_id="orch-main",
        prompt_template="Task {{task_id}} {{title}} {{dod_checklist_full}}",
        implementer=lambda _prompt, _fixes: None,  # type: ignore[arg-type]
        spec_reviewer=lambda _prompt, _result, _attempt: None,  # type: ignore[arg-type]
        quality_reviewer=lambda _prompt, _result, _attempt: None,  # type: ignore[arg-type]
    )

    processed = runner.poll_ready_and_run_once()

    assert processed == "i-abc1"
    assert gateway.status_updates == [("i-abc1", "in_progress")]
    assert gateway.shown_issue_ids == ["i-abc1"]
    assert called == [("i-abc1", "Task DEV-001 Lock SSOT schema * [ ] item 1")]
    assert gateway.calls[:4] == [
        "get_ready_issues",
        "set_issue_status:i-abc1:in_progress",
        "add_feedback:i-abc1",
        "show_issue:i-abc1",
    ]

    _, snapshot_json = gateway.feedback[0]
    snapshot = validate_snapshot(json.loads(snapshot_json))
    assert snapshot["event_type"] == "SESSION_START"


def test_issue_session_runner_reopens_when_orchestrator_errors() -> None:
    gateway = IntegrationGateway()

    class FailingOrchestrator:
        def run_issue(self, **kwargs: object) -> SessionOutcome:
            _ = kwargs
            raise RuntimeError("orchestrator boom")

    runner = IssueSessionRunner(
        gateway=gateway,
        orchestrator=FailingOrchestrator(),
        orchestrator_id="orch-main",
        prompt_template="Task {{task_id}} {{title}} {{dod_checklist_full}}",
        implementer=lambda _prompt, _fixes: None,  # type: ignore[arg-type]
        spec_reviewer=lambda _prompt, _result, _attempt: None,  # type: ignore[arg-type]
        quality_reviewer=lambda _prompt, _result, _attempt: None,  # type: ignore[arg-type]
    )

    with pytest.raises(RuntimeError, match="orchestrator boom"):
        runner.poll_ready_and_run_once()

    assert gateway.status_updates == [
        ("i-abc1", "in_progress"),
        ("i-abc1", "open"),
    ]


def test_claim_issue_sets_in_progress_and_emits_session_start_snapshot() -> None:
    status_updates: list[tuple[str, str]] = []
    snapshots: list[dict[str, object]] = []

    class Gateway:
        def set_issue_status(self, issue_id: str, status: str) -> None:
            status_updates.append((issue_id, status))

    def emit_snapshot(payload: dict[str, object]) -> None:
        snapshots.append(payload)

    result = claim_issue(
        issue_id="i-abc1",
        task_id="DEV-001",
        orchestrator_id="orch-main",
        gateway=Gateway(),
        emit_snapshot=emit_snapshot,
    )

    assert status_updates == [("i-abc1", "in_progress")]
    assert result.issue_id == "i-abc1"
    assert isinstance(result.session_id, str)
    assert result.session_id
    assert len(snapshots) == 1

    snapshot = validate_snapshot(snapshots[0])
    assert snapshot["schema_version"] == "loop_snapshot.v1"
    assert snapshot["event_type"] == "SESSION_START"
    assert snapshot["issue_id"] == "i-abc1"
    assert snapshot["task_id"] == "DEV-001"
    assert snapshot["orchestrator_id"] == "orch-main"
    assert snapshot["session_id"] == result.session_id
    assert snapshot["stage"] == "RUNNING"
    assert snapshot["status"] == "START"
    assert snapshot["attempts"] == {"spec": 0, "quality": 0}
    assert snapshot["failed_items"] == []
    assert snapshot["fix_list"] == []
    assert snapshot["verify"] is None
    assert isinstance(snapshot["timestamp"], str)


def test_dispatcher_sorts_candidates_by_priority_then_ready_time_then_issue_id() -> (
    None
):
    now = datetime(2026, 2, 21, 12, 0, tzinfo=timezone.utc)
    ready = [
        ReadyIssue("i-z9", priority=1, ready_at=now),
        ReadyIssue("i-a1", priority=0, ready_at=now),
        ReadyIssue("i-a0", priority=0, ready_at=now),
        ReadyIssue("i-b1", priority=0, ready_at=now.replace(minute=1)),
        ReadyIssue("i-c1", priority=2, ready_at=now),
    ]

    claims: list[str] = []
    executed: list[str] = []

    dispatcher = WorkerPoolDispatcher(
        ready_gateway=FakeReadyGateway(ready),
        claim_issue=lambda issue_id: claims.append(issue_id),
        run_issue_session=lambda issue_id: executed.append(issue_id),
        max_workers=3,
    )

    dispatched = dispatcher.poll_and_dispatch_once()
    dispatcher.wait_for_idle()
    dispatcher.shutdown()

    assert dispatched == ["i-a0", "i-a1", "i-b1"]
    assert sorted(claims) == ["i-a0", "i-a1", "i-b1"]
    assert sorted(executed) == ["i-a0", "i-a1", "i-b1"]


def test_dispatcher_default_max_workers_is_four() -> None:
    now = datetime(2026, 2, 21, 12, 0, tzinfo=timezone.utc)
    ready = [
        ReadyIssue("i-a", priority=0, ready_at=now),
        ReadyIssue("i-b", priority=0, ready_at=now),
        ReadyIssue("i-c", priority=0, ready_at=now),
        ReadyIssue("i-d", priority=0, ready_at=now),
        ReadyIssue("i-e", priority=0, ready_at=now),
    ]

    claims: list[str] = []
    executed: list[str] = []
    dispatcher = WorkerPoolDispatcher(
        ready_gateway=FakeReadyGateway(ready),
        claim_issue=lambda issue_id: claims.append(issue_id),
        run_issue_session=lambda issue_id: executed.append(issue_id),
    )

    dispatched = dispatcher.poll_and_dispatch_once()
    dispatcher.wait_for_idle()
    dispatcher.shutdown()

    assert dispatched == ["i-a", "i-b", "i-c", "i-d"]
    assert sorted(claims) == ["i-a", "i-b", "i-c", "i-d"]
    assert sorted(executed) == ["i-a", "i-b", "i-c", "i-d"]


def test_dispatcher_uses_worker_slots_for_parallel_issues_only() -> None:
    now = datetime(2026, 2, 21, 13, 0, tzinfo=timezone.utc)
    ready = [
        ReadyIssue("i-a", priority=0, ready_at=now),
        ReadyIssue("i-b", priority=0, ready_at=now),
        ReadyIssue("i-c", priority=0, ready_at=now),
    ]
    started: list[str] = []
    lock = threading.Lock()
    release = threading.Event()

    def run_issue(issue_id: str) -> None:
        with lock:
            started.append(issue_id)
        release.wait(timeout=2)

    claimed: list[str] = []
    dispatcher = WorkerPoolDispatcher(
        ready_gateway=SequencedReadyGateway([ready, [ready[2]]]),
        claim_issue=lambda issue_id: claimed.append(issue_id),
        run_issue_session=run_issue,
        max_workers=2,
    )

    first_batch = dispatcher.poll_and_dispatch_once()

    deadline = time.time() + 1
    while len(started) < 2 and time.time() < deadline:
        time.sleep(0.01)

    second_batch = dispatcher.poll_and_dispatch_once()

    release.set()
    dispatcher.wait_for_idle()
    third_batch = dispatcher.poll_and_dispatch_once()
    dispatcher.wait_for_idle()
    dispatcher.shutdown()

    assert sorted(first_batch) == ["i-a", "i-b"]
    assert second_batch == []
    assert third_batch == ["i-c"]
    assert sorted(claimed) == ["i-a", "i-b", "i-c"]


def test_dispatcher_deduplicates_same_issue_id_within_poll_cycle() -> None:
    now = datetime(2026, 2, 21, 14, 0, tzinfo=timezone.utc)
    ready = [
        ReadyIssue("i-a", priority=0, ready_at=now),
        ReadyIssue("i-a", priority=0, ready_at=now),
        ReadyIssue("i-b", priority=1, ready_at=now),
    ]
    claimed: list[str] = []
    executed: list[str] = []

    dispatcher = WorkerPoolDispatcher(
        ready_gateway=FakeReadyGateway(ready),
        claim_issue=lambda issue_id: claimed.append(issue_id),
        run_issue_session=lambda issue_id: executed.append(issue_id),
        max_workers=3,
    )

    dispatched = dispatcher.poll_and_dispatch_once()
    dispatcher.wait_for_idle()
    dispatcher.shutdown()

    assert dispatched == ["i-a", "i-b"]
    assert sorted(claimed) == ["i-a", "i-b"]
    assert sorted(executed) == ["i-a", "i-b"]


def test_dispatcher_can_redispatch_issue_on_later_poll_after_completion() -> None:
    now = datetime(2026, 2, 21, 15, 0, tzinfo=timezone.utc)
    ready = ReadyIssue("i-a", priority=0, ready_at=now)

    claimed: list[str] = []
    executed: list[str] = []
    dispatcher = WorkerPoolDispatcher(
        ready_gateway=SequencedReadyGateway([[ready], [ready]]),
        claim_issue=lambda issue_id: claimed.append(issue_id),
        run_issue_session=lambda issue_id: executed.append(issue_id),
        max_workers=1,
    )

    first_batch = dispatcher.poll_and_dispatch_once()
    dispatcher.wait_for_idle()
    second_batch = dispatcher.poll_and_dispatch_once()
    dispatcher.wait_for_idle()
    dispatcher.shutdown()

    assert first_batch == ["i-a"]
    assert second_batch == ["i-a"]
    assert claimed == ["i-a", "i-a"]
    assert executed == ["i-a", "i-a"]


def test_dispatcher_rejects_calls_from_different_threads() -> None:
    dispatcher = WorkerPoolDispatcher(
        ready_gateway=FakeReadyGateway([]),
        claim_issue=lambda _: None,
        run_issue_session=lambda _: None,
        max_workers=1,
    )
    dispatcher.poll_and_dispatch_once()

    errors: list[Exception] = []

    def call_from_other_thread() -> None:
        try:
            dispatcher.poll_and_dispatch_once()
        except Exception as exc:  # pragma: no cover - assertion below validates path
            errors.append(exc)

    thread = threading.Thread(target=call_from_other_thread)
    thread.start()
    thread.join()
    dispatcher.shutdown()

    assert len(errors) == 1
    assert isinstance(errors[0], RuntimeError)
    assert "single-caller" in str(errors[0])


def test_dispatcher_raises_for_malformed_ready_at_type() -> None:
    malformed_ready = [
        {"issue_id": "i-bad", "priority": 0, "ready_at": "not-a-datetime"}
    ]
    dispatcher = WorkerPoolDispatcher(
        ready_gateway=FakeReadyGateway(malformed_ready),  # type: ignore[arg-type]
        claim_issue=lambda _: None,
        run_issue_session=lambda _: None,
        max_workers=1,
    )

    with pytest.raises(TypeError, match="ready_at must be datetime"):
        dispatcher.poll_and_dispatch_once()
    dispatcher.shutdown()


def test_dispatcher_raises_for_invalid_priority_range() -> None:
    malformed_ready = [
        {
            "issue_id": "i-bad",
            "priority": 8,
            "ready_at": datetime(2026, 2, 21, 12, 0, tzinfo=timezone.utc),
        }
    ]
    dispatcher = WorkerPoolDispatcher(
        ready_gateway=FakeReadyGateway(malformed_ready),  # type: ignore[arg-type]
        claim_issue=lambda _: None,
        run_issue_session=lambda _: None,
        max_workers=1,
    )

    with pytest.raises(ValueError, match="priority"):
        dispatcher.poll_and_dispatch_once()
    dispatcher.shutdown()


def test_issue_session_runner_emits_session_error_when_show_issue_fails() -> None:
    class FailingShowGateway(IntegrationGateway):
        def show_issue(self, issue_id: str) -> dict[str, str]:
            self.calls.append(f"show_issue:{issue_id}")
            raise RuntimeError("show failed")

    gateway = FailingShowGateway()

    runner = IssueSessionRunner(
        gateway=gateway,
        orchestrator=object(),  # type: ignore[arg-type]
        orchestrator_id="orch-main",
        prompt_template="Task {{task_id}}",
        implementer=lambda _prompt, _fixes: None,  # type: ignore[arg-type]
        spec_reviewer=lambda _prompt, _result, _attempt: None,  # type: ignore[arg-type]
        quality_reviewer=lambda _prompt, _result, _attempt: None,  # type: ignore[arg-type]
    )

    with pytest.raises(RuntimeError, match="show failed"):
        runner.poll_ready_and_run_once()

    assert gateway.status_updates == [
        ("i-abc1", "in_progress"),
        ("i-abc1", "open"),
    ]
    assert len(gateway.feedback) == 2

    _, claim_snapshot_json = gateway.feedback[0]
    claim_snapshot = validate_snapshot(json.loads(claim_snapshot_json))
    assert claim_snapshot["event_type"] == "SESSION_START"

    _, error_snapshot_json = gateway.feedback[1]
    error_snapshot = validate_snapshot(json.loads(error_snapshot_json))
    assert error_snapshot["event_type"] == "SESSION_ERROR"
    assert error_snapshot["status"] == "FAIL"
