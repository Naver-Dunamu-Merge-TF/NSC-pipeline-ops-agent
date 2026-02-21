from __future__ import annotations

from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from .models import (
    Implementer,
    ImplementerResult,
    IssueContext,
    Reviewer,
    SessionOutcome,
    SudocodeGateway,
    VerificationEvidence,
)
from .snapshot import SCHEMA_VERSION, emit_snapshot_json


class SingleSessionOrchestrator:
    SPEC_MAX_ATTEMPTS = 3
    QUALITY_MAX_ATTEMPTS = 2

    def __init__(self, gateway: SudocodeGateway) -> None:
        self.gateway = gateway

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
    ) -> SessionOutcome:
        resolved_session_id = session_id or self._default_session_id(issue.issue_id)
        spec_attempt = 0
        quality_attempt = 0
        implementer_result: ImplementerResult | None = None

        try:
            self.gateway.set_issue_status(issue.issue_id, "in_progress")
            implementer_result = implementer(rendered_prompt, None)
            self._snapshot(
                issue=issue,
                session_id=resolved_session_id,
                orchestrator_id=orchestrator_id,
                event_type="IMPLEMENT_DONE",
                stage="RUNNING",
                status="PASS",
                spec_attempt=spec_attempt,
                quality_attempt=quality_attempt,
                verify=implementer_result.verification,
            )

            while True:
                spec_attempt += 1
                spec_result = spec_reviewer(
                    rendered_prompt, implementer_result, spec_attempt
                )
                self._snapshot(
                    issue=issue,
                    session_id=resolved_session_id,
                    orchestrator_id=orchestrator_id,
                    event_type=(
                        "SPEC_REVIEW_PASS" if spec_result.passed else "SPEC_REVIEW_FAIL"
                    ),
                    stage="SPEC_REVIEW",
                    status="PASS" if spec_result.passed else "FAIL",
                    spec_attempt=spec_attempt,
                    quality_attempt=quality_attempt,
                    failed_items=spec_result.failed_items,
                    fix_list=spec_result.fix_list,
                    verify=implementer_result.verification,
                )

                if spec_result.passed:
                    break

                if spec_attempt >= self.SPEC_MAX_ATTEMPTS:
                    return self._handle_overflow(
                        issue=issue,
                        session_id=resolved_session_id,
                        orchestrator_id=orchestrator_id,
                        overflow_reason=f"SPEC_REVIEW failed at attempt {spec_attempt}/{self.SPEC_MAX_ATTEMPTS}",
                        failed_items=spec_result.failed_items,
                        verification=implementer_result.verification,
                        spec_attempt=spec_attempt,
                        quality_attempt=quality_attempt,
                    )

                implementer_result = implementer(rendered_prompt, spec_result.fix_list)
                self._snapshot(
                    issue=issue,
                    session_id=resolved_session_id,
                    orchestrator_id=orchestrator_id,
                    event_type="SPEC_FIX_APPLIED",
                    stage="SPEC_FIX",
                    status="PASS",
                    spec_attempt=spec_attempt,
                    quality_attempt=quality_attempt,
                    verify=implementer_result.verification,
                )

            while True:
                quality_attempt += 1
                quality_result = quality_reviewer(
                    rendered_prompt,
                    implementer_result,
                    quality_attempt,
                )
                self._snapshot(
                    issue=issue,
                    session_id=resolved_session_id,
                    orchestrator_id=orchestrator_id,
                    event_type=(
                        "QUALITY_REVIEW_PASS"
                        if quality_result.passed
                        else "QUALITY_REVIEW_FAIL"
                    ),
                    stage="QUALITY_REVIEW",
                    status="PASS" if quality_result.passed else "FAIL",
                    spec_attempt=spec_attempt,
                    quality_attempt=quality_attempt,
                    failed_items=quality_result.failed_items,
                    fix_list=quality_result.fix_list,
                    verify=implementer_result.verification,
                )

                if quality_result.passed:
                    break

                if quality_attempt >= self.QUALITY_MAX_ATTEMPTS:
                    return self._handle_overflow(
                        issue=issue,
                        session_id=resolved_session_id,
                        orchestrator_id=orchestrator_id,
                        overflow_reason=f"QUALITY_REVIEW failed at attempt {quality_attempt}/{self.QUALITY_MAX_ATTEMPTS}",
                        failed_items=quality_result.failed_items,
                        verification=implementer_result.verification,
                        spec_attempt=spec_attempt,
                        quality_attempt=quality_attempt,
                    )

                implementer_result = implementer(
                    rendered_prompt, quality_result.fix_list
                )
                self._snapshot(
                    issue=issue,
                    session_id=resolved_session_id,
                    orchestrator_id=orchestrator_id,
                    event_type="QUALITY_FIX_APPLIED",
                    stage="QUALITY_FIX",
                    status="PASS",
                    spec_attempt=spec_attempt,
                    quality_attempt=quality_attempt,
                    verify=implementer_result.verification,
                )

            if not self._fresh_verification_passed(implementer_result):
                self._snapshot(
                    issue=issue,
                    session_id=resolved_session_id,
                    orchestrator_id=orchestrator_id,
                    event_type="VERIFY_FAILED",
                    stage="VERIFICATION",
                    status="VERIFY_FAILED",
                    spec_attempt=spec_attempt,
                    quality_attempt=quality_attempt,
                    verify=implementer_result.verification,
                )
                return SessionOutcome(final_state="VERIFY_FAILED", fix_issue_id=None)

            self.gateway.set_issue_status(issue.issue_id, "needs_review")
            self._snapshot(
                issue=issue,
                session_id=resolved_session_id,
                orchestrator_id=orchestrator_id,
                event_type="SESSION_DONE",
                stage="REVIEW_GATE",
                status="NEEDS_REVIEW",
                spec_attempt=spec_attempt,
                quality_attempt=quality_attempt,
                verify=implementer_result.verification,
            )
            return SessionOutcome(final_state="NEEDS_REVIEW", fix_issue_id=None)
        except Exception as exc:
            self._snapshot(
                issue=issue,
                session_id=resolved_session_id,
                orchestrator_id=orchestrator_id,
                event_type="SESSION_ERROR",
                stage="RUNNING",
                status="FAIL",
                spec_attempt=spec_attempt,
                quality_attempt=quality_attempt,
                failed_items=[str(exc)],
                verify=(
                    None
                    if implementer_result is None
                    else implementer_result.verification
                ),
            )
            raise

    def _fresh_verification_passed(self, implementer_result: ImplementerResult) -> bool:
        verification = implementer_result.verification
        if verification is None:
            return False
        if verification.exit_code != 0:
            return False
        return verification.produced_at >= implementer_result.code_changed_at

    def _handle_overflow(
        self,
        *,
        issue: IssueContext,
        session_id: str,
        orchestrator_id: str,
        overflow_reason: str,
        failed_items: list[str],
        verification: VerificationEvidence | None,
        spec_attempt: int,
        quality_attempt: int,
    ) -> SessionOutcome:
        fix_title = f"[FIX] {issue.task_id}: {issue.title}"
        fix_body = self._build_fix_issue_body(
            issue=issue,
            overflow_reason=overflow_reason,
            failed_items=failed_items,
            verification=verification,
        )
        fix_issue_id = self.gateway.create_fix_issue(fix_title, fix_body)
        self.gateway.link_issues(issue.issue_id, fix_issue_id, "depends-on")
        self.gateway.set_issue_status(issue.issue_id, "needs_review")
        self._snapshot(
            issue=issue,
            session_id=session_id,
            orchestrator_id=orchestrator_id,
            event_type="OVERFLOW_FIX_CREATED",
            stage="REVIEW_GATE",
            status="NEEDS_REVIEW",
            spec_attempt=spec_attempt,
            quality_attempt=quality_attempt,
            failed_items=failed_items,
            fix_list=[overflow_reason],
            verify=verification,
        )
        return SessionOutcome(final_state="OVERFLOW", fix_issue_id=fix_issue_id)

    def _build_fix_issue_body(
        self,
        *,
        issue: IssueContext,
        overflow_reason: str,
        failed_items: list[str],
        verification: VerificationEvidence | None,
    ) -> str:
        verify_output = "verify_output: NOT_RUN"
        if verification is not None:
            verify_output = (
                f"command: {verification.command}\n"
                f"exit_code: {verification.exit_code}\n"
                f"output:\n{verification.output}"
            )

        failed_lines = "\n".join(f"- {item}" for item in failed_items) or "- (none)"
        return (
            f"original task id: {issue.issue_id}\n"
            f"overflow reason: {overflow_reason}\n"
            "failed acceptance items:\n"
            f"{failed_lines}\n\n"
            "latest verification evidence/output:\n"
            f"{verify_output}\n\n"
            "full original DoD:\n"
            f"{issue.dod_checklist_full}"
        )

    def _snapshot(
        self,
        *,
        issue: IssueContext,
        session_id: str,
        orchestrator_id: str,
        event_type: str,
        stage: str,
        status: str,
        spec_attempt: int,
        quality_attempt: int,
        failed_items: list[str] | None = None,
        fix_list: list[str] | None = None,
        verify: VerificationEvidence | None = None,
    ) -> None:
        snapshot = {
            "schema_version": SCHEMA_VERSION,
            "session_id": session_id,
            "orchestrator_id": orchestrator_id,
            "issue_id": issue.issue_id,
            "task_id": issue.task_id,
            "event_type": event_type,
            "stage": stage,
            "status": status,
            "attempts": {"spec": spec_attempt, "quality": quality_attempt},
            "failed_items": failed_items or [],
            "fix_list": fix_list or [],
            "verify": self._serialize_verify(verify),
            "timestamp": self._utc_now_iso(),
        }
        self.gateway.add_feedback(issue.issue_id, emit_snapshot_json(snapshot))

    def _serialize_verify(
        self, verification: VerificationEvidence | None
    ) -> dict[str, object] | None:
        if verification is None:
            return None
        return {
            "command": verification.command,
            "exit_code": verification.exit_code,
            "produced_at": verification.produced_at.isoformat().replace("+00:00", "Z"),
        }

    def _default_session_id(self, issue_id: str) -> str:
        return str(uuid5(NAMESPACE_URL, f"sudocode-session:{issue_id}"))

    def _utc_now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
