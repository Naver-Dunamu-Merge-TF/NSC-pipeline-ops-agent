from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Literal, Protocol


@dataclass(frozen=True)
class IssueContext:
    issue_id: str
    manifest_id: str
    task_id: str
    gate_id: str
    epic_id: str
    title: str
    depends_on: str
    dod_checklist_full: str


@dataclass(frozen=True)
class VerificationEvidence:
    command: str
    output: str
    exit_code: int
    produced_at: datetime


@dataclass(frozen=True)
class ImplementerResult:
    verification: VerificationEvidence | None
    code_changed_at: datetime
    notes: str


@dataclass(frozen=True)
class ReviewResult:
    passed: bool
    failed_items: list[str]
    fix_list: list[str]
    notes: str


@dataclass(frozen=True)
class SessionOutcome:
    final_state: Literal["DONE", "NEEDS_REVIEW", "OVERFLOW", "VERIFY_FAILED"]
    fix_issue_id: str | None


class SudocodeGateway(Protocol):
    def set_issue_status(self, issue_id: str, status: str) -> None: ...

    def add_feedback(self, issue_id: str, content: str) -> None: ...

    def create_fix_issue(self, title: str, body: str) -> str: ...

    def link_issues(self, from_id: str, to_id: str, relation: str) -> None: ...


Implementer = Callable[[str, list[str] | None], ImplementerResult]
Reviewer = Callable[[str, ImplementerResult, int], ReviewResult]
