from __future__ import annotations

import argparse
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import threading
from typing import Callable, Protocol, Sequence

from .claim import claim_issue
from .models import Implementer, IssueContext, Reviewer
from .prompt_renderer import render_issue_prompt
from .snapshot import SCHEMA_VERSION, emit_snapshot_json


class ReadyGateway(Protocol):
    def get_ready_issues(self) -> Sequence[object]: ...


class SessionGateway(ReadyGateway, Protocol):
    def set_issue_status(self, issue_id: str, status: str) -> None: ...

    def add_feedback(self, issue_id: str, content: str) -> None: ...

    def show_issue(self, issue_id: str) -> object: ...


class SessionOrchestrator(Protocol):
    def run_issue(
        self,
        *,
        issue: IssueContext,
        rendered_prompt: str,
        implementer: Implementer,
        spec_reviewer: Reviewer,
        quality_reviewer: Reviewer,
        session_id: str | None = None,
        orchestrator_id: str = "orch-main",
    ) -> object: ...


ClaimIssueFn = Callable[[str], None]
RunIssueSessionFn = Callable[[str], None]


@dataclass(frozen=True)
class _ReadyCandidate:
    issue_id: str
    task_id: str
    priority: int
    ready_at: datetime


class WorkerPoolDispatcher:
    def __init__(
        self,
        *,
        ready_gateway: ReadyGateway,
        claim_issue: ClaimIssueFn,
        run_issue_session: RunIssueSessionFn,
        max_workers: int = 4,
    ) -> None:
        if max_workers <= 0:
            raise ValueError("max_workers must be positive")
        self._ready_gateway = ready_gateway
        self._claim_issue = claim_issue
        self._run_issue_session = run_issue_session
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._max_workers = max_workers
        self._active: dict[str, Future[None]] = {}
        self._caller_thread_id: int | None = None

    def poll_and_dispatch_once(self) -> list[str]:
        self._assert_single_caller()
        self._collect_finished()
        available_slots = self._max_workers - len(self._active)
        if available_slots <= 0:
            return []

        ready = self._ready_gateway.get_ready_issues()
        candidates = self._sorted_candidates(ready)
        selected = self._select_candidates(candidates, available_slots)

        for candidate in selected:
            issue_id = candidate.issue_id
            self._active[issue_id] = self._executor.submit(
                self._run_claimed_issue, issue_id
            )

        return [candidate.issue_id for candidate in selected]

    def wait_for_idle(self) -> None:
        self._assert_single_caller()
        while self._active:
            future = next(iter(self._active.values()))
            future.result()
            self._collect_finished()

    def shutdown(self) -> None:
        self._assert_single_caller()
        self._executor.shutdown(wait=True)

    def _assert_single_caller(self) -> None:
        current_thread_id = threading.get_ident()
        if self._caller_thread_id is None:
            self._caller_thread_id = current_thread_id
            return
        if self._caller_thread_id != current_thread_id:
            raise RuntimeError(
                "WorkerPoolDispatcher enforces single-caller thread usage"
            )

    def _run_claimed_issue(self, issue_id: str) -> None:
        self._claim_issue(issue_id)
        self._run_issue_session(issue_id)

    def _collect_finished(self) -> None:
        finished_ids = [
            issue_id for issue_id, future in self._active.items() if future.done()
        ]
        for issue_id in finished_ids:
            future = self._active.pop(issue_id)
            future.result()

    def _select_candidates(
        self, candidates: list[_ReadyCandidate], available_slots: int
    ) -> list[_ReadyCandidate]:
        selected: list[_ReadyCandidate] = []
        seen_issue_ids: set[str] = set()
        for candidate in candidates:
            issue_id = candidate.issue_id
            if issue_id in self._active:
                continue
            if issue_id in seen_issue_ids:
                continue
            selected.append(candidate)
            seen_issue_ids.add(issue_id)
            if len(selected) == available_slots:
                break
        return selected

    def _sorted_candidates(self, issues: Sequence[object]) -> list[_ReadyCandidate]:
        candidates = [_as_candidate(issue) for issue in issues]
        return sorted(
            candidates,
            key=lambda candidate: (
                candidate.priority,
                candidate.ready_at,
                candidate.issue_id,
            ),
        )


def _as_candidate(issue: object) -> _ReadyCandidate:
    issue_id_raw = _read_attr(issue, "issue_id")
    if not isinstance(issue_id_raw, str) or not issue_id_raw.strip():
        raise TypeError("issue_id must be non-empty string")
    issue_id = issue_id_raw

    task_id = _read_optional_str(issue, "task_id") or issue_id
    priority_value = _read_attr(issue, "priority")
    if not isinstance(priority_value, int) or isinstance(priority_value, bool):
        raise TypeError("priority must be int")
    priority = priority_value
    if priority < 0 or priority > 4:
        raise ValueError("priority must be between 0 and 4")

    ready_at_value = _read_attr(issue, "ready_at")
    if not isinstance(ready_at_value, datetime):
        raise TypeError("ready_at must be datetime")

    return _ReadyCandidate(
        issue_id=issue_id,
        task_id=task_id,
        priority=priority,
        ready_at=ready_at_value,
    )


def _read_attr(issue: object, name: str) -> object:
    if isinstance(issue, dict):
        return issue[name]
    return getattr(issue, name)


def _read_optional_str(issue: object, name: str) -> str | None:
    try:
        if isinstance(issue, dict):
            value = issue.get(name)
        else:
            value = getattr(issue, name)
    except AttributeError:
        return None
    if value is None:
        return None
    return str(value)


class IssueSessionRunner:
    def __init__(
        self,
        *,
        gateway: SessionGateway,
        orchestrator: SessionOrchestrator,
        orchestrator_id: str,
        prompt_template: str,
        implementer: Implementer,
        spec_reviewer: Reviewer,
        quality_reviewer: Reviewer,
    ) -> None:
        self._gateway = gateway
        self._orchestrator = orchestrator
        self._orchestrator_id = orchestrator_id
        self._prompt_template = prompt_template
        self._implementer = implementer
        self._spec_reviewer = spec_reviewer
        self._quality_reviewer = quality_reviewer

    def poll_ready_and_run_once(self) -> str | None:
        candidates = _sorted_candidates(self._gateway.get_ready_issues())
        if not candidates:
            return None
        selected = candidates[0]
        self.claim_and_run_issue(selected.issue_id, selected.task_id)
        return selected.issue_id

    def claim_and_run_issue(self, issue_id: str, task_id: str | None = None) -> None:
        resolved_task_id = task_id or issue_id
        claim_result = claim_issue(
            issue_id=issue_id,
            task_id=resolved_task_id,
            orchestrator_id=self._orchestrator_id,
            gateway=self._gateway,
            emit_snapshot=self._emit_claim_snapshot,
        )

        try:
            issue = self._load_issue(issue_id)
            rendered_prompt = render_issue_prompt(self._prompt_template, issue)
        except Exception as exc:
            self._emit_runner_error_snapshot(
                issue_id=issue_id,
                task_id=resolved_task_id,
                session_id=claim_result.session_id,
                message=str(exc),
            )
            self._gateway.set_issue_status(issue_id, "open")
            raise

        try:
            self._orchestrator.run_issue(
                issue=issue,
                rendered_prompt=rendered_prompt,
                implementer=self._implementer,
                spec_reviewer=self._spec_reviewer,
                quality_reviewer=self._quality_reviewer,
                session_id=claim_result.session_id,
                orchestrator_id=self._orchestrator_id,
            )
        except Exception:
            self._gateway.set_issue_status(issue_id, "open")
            raise

    def _emit_claim_snapshot(self, payload: dict[str, object]) -> None:
        issue_id = payload.get("issue_id")
        if not isinstance(issue_id, str):
            raise ValueError("issue_id must be present in claim snapshot")
        self._gateway.add_feedback(issue_id, emit_snapshot_json(payload))

    def _emit_runner_error_snapshot(
        self,
        *,
        issue_id: str,
        task_id: str,
        session_id: str,
        message: str,
    ) -> None:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "session_id": session_id,
            "orchestrator_id": self._orchestrator_id,
            "issue_id": issue_id,
            "task_id": task_id,
            "event_type": "SESSION_ERROR",
            "stage": "RUNNING",
            "status": "FAIL",
            "attempts": {"spec": 0, "quality": 0},
            "failed_items": [message],
            "fix_list": [],
            "verify": None,
            "timestamp": _utc_now_iso(),
        }
        self._gateway.add_feedback(issue_id, emit_snapshot_json(payload))

    def _load_issue(self, issue_id: str) -> IssueContext:
        payload = self._gateway.show_issue(issue_id)
        issue_payload = _coerce_issue_payload(payload)
        return IssueContext(
            issue_id=str(issue_payload["issue_id"]),
            manifest_id=str(issue_payload["manifest_id"]),
            task_id=str(issue_payload["task_id"]),
            gate_id=str(issue_payload["gate_id"]),
            epic_id=str(issue_payload["epic_id"]),
            title=str(issue_payload["title"]),
            depends_on=str(issue_payload["depends_on"]),
            dod_checklist_full=str(issue_payload["dod_checklist_full"]),
        )


def _sorted_candidates(issues: Sequence[object]) -> list[_ReadyCandidate]:
    return sorted(
        [_as_candidate(issue) for issue in issues],
        key=lambda candidate: (
            candidate.priority,
            candidate.ready_at,
            candidate.issue_id,
        ),
    )


def _coerce_issue_payload(payload: object) -> dict[str, object]:
    if isinstance(payload, dict) and isinstance(payload.get("issue"), dict):
        return payload["issue"]
    if isinstance(payload, dict):
        return payload
    raise TypeError("show_issue payload must be a mapping")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run_dry_run() -> dict[str, object]:
    from .models import ImplementerResult, ReviewResult, VerificationEvidence
    from .session_loop import SingleSessionOrchestrator

    class _DryRunGateway:
        def __init__(self) -> None:
            self._polled = False
            self.status_updates: list[tuple[str, str]] = []
            self.feedback: list[tuple[str, str]] = []

        def get_ready_issues(self) -> list[dict[str, object]]:
            if self._polled:
                return []
            self._polled = True
            return [
                {
                    "issue_id": "i-dry1",
                    "task_id": "DRY-001",
                    "priority": 0,
                    "ready_at": datetime(2026, 2, 21, 12, 0, tzinfo=timezone.utc),
                }
            ]

        def show_issue(self, issue_id: str) -> dict[str, str]:
            return {
                "issue_id": issue_id,
                "manifest_id": "m-dry",
                "task_id": "DRY-001",
                "gate_id": "G-DRY",
                "epic_id": "EPIC-DRY",
                "title": "Dry run orchestrator",
                "depends_on": "-",
                "dod_checklist_full": "* [ ] dry-run check",
            }

        def set_issue_status(self, issue_id: str, status: str) -> None:
            self.status_updates.append((issue_id, status))

        def add_feedback(self, issue_id: str, content: str) -> None:
            self.feedback.append((issue_id, content))

        def create_fix_issue(self, title: str, body: str) -> str:
            raise RuntimeError(f"unexpected fix issue creation: {title} {body}")

        def link_issues(self, from_id: str, to_id: str, relation: str) -> None:
            raise RuntimeError(
                f"unexpected issue linking: {from_id} {to_id} {relation}"
            )

    now = datetime(2026, 2, 21, 12, 5, tzinfo=timezone.utc)

    def implementer(_: str, __: list[str] | None) -> ImplementerResult:
        return ImplementerResult(
            verification=VerificationEvidence(
                command="python -m pytest tests/unit/ -x",
                output="ok",
                exit_code=0,
                produced_at=now,
            ),
            code_changed_at=now - timedelta(seconds=1),
            notes="dry-run implementer",
        )

    def reviewer(_: str, __: ImplementerResult, ___: int) -> ReviewResult:
        return ReviewResult(passed=True, failed_items=[], fix_list=[], notes="pass")

    gateway = _DryRunGateway()
    orchestrator = SingleSessionOrchestrator(gateway=gateway)
    runner = IssueSessionRunner(
        gateway=gateway,
        orchestrator=orchestrator,
        orchestrator_id="orch-dry-run",
        prompt_template=(
            "Task {{task_id}} {{title}} {{manifest_id}} "
            "{{gate_id}} {{epic_id}} {{depends_on}} {{dod_checklist_full}}"
        ),
        implementer=implementer,
        spec_reviewer=reviewer,
        quality_reviewer=reviewer,
    )

    processed_issue = runner.poll_ready_and_run_once()
    last_snapshot = json.loads(gateway.feedback[-1][1]) if gateway.feedback else {}
    return {
        "processed_issue": processed_issue,
        "status_updates": gateway.status_updates,
        "snapshot_count": len(gateway.feedback),
        "last_event_type": last_snapshot.get("event_type"),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m sudocode_orchestrator.runner",
        description="Sudocode orchestrator helper commands",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run local dry-run simulation with mocked gateway",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    if not args.dry_run:
        parser.error("pass --dry-run to run local simulation")

    print(json.dumps(run_dry_run(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
