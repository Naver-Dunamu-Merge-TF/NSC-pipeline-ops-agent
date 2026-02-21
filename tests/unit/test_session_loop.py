from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json

from sudocode_orchestrator.models import (
    ImplementerResult,
    IssueContext,
    ReviewResult,
    VerificationEvidence,
)
from sudocode_orchestrator.session_loop import SingleSessionOrchestrator
from sudocode_orchestrator.snapshot import validate_snapshot


@dataclass
class FakeGateway:
    status_updates: list[tuple[str, str]]
    feedback: list[tuple[str, str]]
    created_fix_issues: list[tuple[str, str]]
    links: list[tuple[str, str, str]]

    def set_issue_status(self, issue_id: str, status: str) -> None:
        self.status_updates.append((issue_id, status))

    def add_feedback(self, issue_id: str, content: str) -> None:
        self.feedback.append((issue_id, content))

    def create_fix_issue(self, title: str, body: str) -> str:
        self.created_fix_issues.append((title, body))
        return "i-fix01"

    def link_issues(self, from_id: str, to_id: str, relation: str) -> None:
        self.links.append((from_id, to_id, relation))


def _issue() -> IssueContext:
    return IssueContext(
        issue_id="i-abc1",
        manifest_id="m-001",
        task_id="DEV-001",
        gate_id="G1",
        epic_id="EPIC-01",
        title="Lock SSOT schema",
        depends_on="-",
        dod_checklist_full="* [ ] item 1",
    )


def _rendered_prompt() -> str:
    return "rendered prompt"


def _validated_snapshots(gateway: FakeGateway) -> list[dict[str, object]]:
    return [validate_snapshot(json.loads(content)) for _, content in gateway.feedback]


def test_overflow_on_third_spec_failure_closes_original_and_creates_fix() -> None:
    gateway = FakeGateway([], [], [], [])
    now = datetime(2026, 2, 21, 9, 0, tzinfo=timezone.utc)
    quality_calls = 0

    def implementer(_: str, __: list[str] | None) -> ImplementerResult:
        return ImplementerResult(
            verification=VerificationEvidence(
                command="pytest tests/unit -x",
                output="ok",
                exit_code=0,
                produced_at=now,
            ),
            code_changed_at=now - timedelta(seconds=1),
            notes="implemented",
        )

    def spec_reviewer(_: str, __: ImplementerResult, ___: int) -> ReviewResult:
        return ReviewResult(
            passed=False,
            failed_items=["DoD #1"],
            fix_list=["Fix DoD #1"],
            notes="failed",
        )

    def quality_reviewer(_: str, __: ImplementerResult, ___: int) -> ReviewResult:
        nonlocal quality_calls
        quality_calls += 1
        return ReviewResult(passed=True, failed_items=[], fix_list=[], notes="pass")

    orchestrator = SingleSessionOrchestrator(gateway=gateway)
    outcome = orchestrator.run_issue(
        issue=_issue(),
        rendered_prompt=_rendered_prompt(),
        implementer=implementer,
        spec_reviewer=spec_reviewer,
        quality_reviewer=quality_reviewer,
    )

    assert outcome.final_state == "OVERFLOW"
    assert gateway.status_updates[-1] == ("i-abc1", "closed")
    assert quality_calls == 0
    assert gateway.created_fix_issues
    assert gateway.created_fix_issues[0][0] == "[FIX] DEV-001: Lock SSOT schema"
    assert ("i-abc1", "i-fix01", "related") in gateway.links
    snapshots = _validated_snapshots(gateway)
    assert snapshots[-1]["event_type"] == "OVERFLOW_FIX_CREATED"
    assert snapshots[-1]["stage"] == "OVERFLOW"
    assert snapshots[-1]["status"] == "FIX_CREATED"


def test_quality_runs_only_after_spec_pass() -> None:
    gateway = FakeGateway([], [], [], [])
    now = datetime(2026, 2, 21, 10, 0, tzinfo=timezone.utc)
    spec_calls = 0
    quality_calls = 0
    impl_calls = 0

    def implementer(_: str, __: list[str] | None) -> ImplementerResult:
        nonlocal impl_calls
        impl_calls += 1
        changed_at = now + timedelta(minutes=impl_calls)
        return ImplementerResult(
            verification=VerificationEvidence(
                command="pytest tests/unit -x",
                output="ok",
                exit_code=0,
                produced_at=changed_at + timedelta(seconds=2),
            ),
            code_changed_at=changed_at,
            notes="implemented",
        )

    def spec_reviewer(_: str, __: ImplementerResult, ___: int) -> ReviewResult:
        nonlocal spec_calls
        spec_calls += 1
        if spec_calls == 1:
            return ReviewResult(
                passed=False,
                failed_items=["DoD #2"],
                fix_list=["Fix DoD #2"],
                notes="failed",
            )
        return ReviewResult(passed=True, failed_items=[], fix_list=[], notes="pass")

    def quality_reviewer(_: str, __: ImplementerResult, ___: int) -> ReviewResult:
        nonlocal quality_calls
        quality_calls += 1
        return ReviewResult(passed=True, failed_items=[], fix_list=[], notes="pass")

    orchestrator = SingleSessionOrchestrator(gateway=gateway)
    outcome = orchestrator.run_issue(
        issue=_issue(),
        rendered_prompt=_rendered_prompt(),
        implementer=implementer,
        spec_reviewer=spec_reviewer,
        quality_reviewer=quality_reviewer,
    )

    assert spec_calls == 2
    assert quality_calls == 1
    assert impl_calls == 2
    assert outcome.final_state == "DONE"
    assert gateway.status_updates[-1] == ("i-abc1", "closed")
    snapshots = _validated_snapshots(gateway)
    event_types = [snapshot["event_type"] for snapshot in snapshots]
    assert event_types == [
        "IMPLEMENT_DONE",
        "SPEC_REVIEW_FAIL",
        "SPEC_FIX_APPLIED",
        "SPEC_REVIEW_PASS",
        "QUALITY_REVIEW_PASS",
        "SESSION_DONE",
    ]


def test_done_requires_fresh_verify_exit_code_zero() -> None:
    gateway = FakeGateway([], [], [], [])
    now = datetime(2026, 2, 21, 11, 0, tzinfo=timezone.utc)

    def implementer(_: str, __: list[str] | None) -> ImplementerResult:
        return ImplementerResult(
            verification=VerificationEvidence(
                command="pytest tests/unit -x",
                output="failed",
                exit_code=1,
                produced_at=now + timedelta(seconds=3),
            ),
            code_changed_at=now,
            notes="implemented",
        )

    def pass_reviewer(_: str, __: ImplementerResult, ___: int) -> ReviewResult:
        return ReviewResult(passed=True, failed_items=[], fix_list=[], notes="pass")

    orchestrator = SingleSessionOrchestrator(gateway=gateway)
    outcome = orchestrator.run_issue(
        issue=_issue(),
        rendered_prompt=_rendered_prompt(),
        implementer=implementer,
        spec_reviewer=pass_reviewer,
        quality_reviewer=pass_reviewer,
    )

    assert outcome.final_state == "VERIFY_FAILED"
    assert ("i-abc1", "closed") not in gateway.status_updates
    snapshots = _validated_snapshots(gateway)
    assert snapshots[-1]["event_type"] == "VERIFY_FAILED"
    assert snapshots[-1]["stage"] == "VERIFICATION"
    assert snapshots[-1]["status"] == "VERIFY_FAILED"


def test_quality_fix_event_is_emitted_when_quality_retry_happens() -> None:
    gateway = FakeGateway([], [], [], [])
    now = datetime(2026, 2, 21, 12, 0, tzinfo=timezone.utc)
    quality_calls = 0

    def implementer(_: str, __: list[str] | None) -> ImplementerResult:
        return ImplementerResult(
            verification=VerificationEvidence(
                command="pytest tests/unit -x",
                output="ok",
                exit_code=0,
                produced_at=now + timedelta(seconds=2),
            ),
            code_changed_at=now,
            notes="implemented",
        )

    def pass_reviewer(_: str, __: ImplementerResult, ___: int) -> ReviewResult:
        return ReviewResult(passed=True, failed_items=[], fix_list=[], notes="pass")

    def quality_reviewer(_: str, __: ImplementerResult, ___: int) -> ReviewResult:
        nonlocal quality_calls
        quality_calls += 1
        if quality_calls == 1:
            return ReviewResult(
                passed=False,
                failed_items=["Quality #1"],
                fix_list=["Fix Quality #1"],
                notes="failed",
            )
        return ReviewResult(passed=True, failed_items=[], fix_list=[], notes="pass")

    orchestrator = SingleSessionOrchestrator(gateway=gateway)
    outcome = orchestrator.run_issue(
        issue=_issue(),
        rendered_prompt=_rendered_prompt(),
        implementer=implementer,
        spec_reviewer=pass_reviewer,
        quality_reviewer=quality_reviewer,
    )

    assert outcome.final_state == "DONE"
    snapshots = _validated_snapshots(gateway)
    event_types = [snapshot["event_type"] for snapshot in snapshots]
    assert "QUALITY_REVIEW_FAIL" in event_types
    assert "QUALITY_FIX_APPLIED" in event_types


def test_session_error_snapshot_emitted_on_unhandled_exception() -> None:
    gateway = FakeGateway([], [], [], [])

    def failing_implementer(_: str, __: list[str] | None) -> ImplementerResult:
        raise RuntimeError("boom")

    def pass_reviewer(_: str, __: ImplementerResult, ___: int) -> ReviewResult:
        return ReviewResult(passed=True, failed_items=[], fix_list=[], notes="pass")

    orchestrator = SingleSessionOrchestrator(gateway=gateway)

    try:
        orchestrator.run_issue(
            issue=_issue(),
            rendered_prompt=_rendered_prompt(),
            implementer=failing_implementer,
            spec_reviewer=pass_reviewer,
            quality_reviewer=pass_reviewer,
        )
    except RuntimeError as exc:
        assert str(exc) == "boom"
    else:
        raise AssertionError("expected RuntimeError")

    snapshots = _validated_snapshots(gateway)
    assert snapshots[-1]["event_type"] == "SESSION_ERROR"
    assert snapshots[-1]["status"] == "FAIL"
