from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Protocol
from uuid import NAMESPACE_URL, uuid5

from .snapshot import SCHEMA_VERSION


class ClaimGateway(Protocol):
    def set_issue_status(self, issue_id: str, status: str) -> None: ...


SnapshotEmitter = Callable[[dict[str, object]], None]
SessionIdFactory = Callable[[str], str]


@dataclass(frozen=True)
class ClaimResult:
    issue_id: str
    session_id: str


def claim_issue(
    *,
    issue_id: str,
    task_id: str,
    orchestrator_id: str,
    gateway: ClaimGateway,
    emit_snapshot: SnapshotEmitter,
    make_session_id: SessionIdFactory | None = None,
) -> ClaimResult:
    session_id_factory = make_session_id or _default_session_id
    session_id = session_id_factory(issue_id)

    gateway.set_issue_status(issue_id, "in_progress")
    emit_snapshot(
        {
            "schema_version": SCHEMA_VERSION,
            "event_type": "SESSION_START",
            "issue_id": issue_id,
            "task_id": task_id,
            "orchestrator_id": orchestrator_id,
            "session_id": session_id,
            "stage": "RUNNING",
            "status": "START",
            "attempts": {"spec": 0, "quality": 0},
            "failed_items": [],
            "fix_list": [],
            "verify": None,
            "timestamp": _utc_now_iso(),
        }
    )

    return ClaimResult(issue_id=issue_id, session_id=session_id)


def _default_session_id(issue_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"sudocode-session:{issue_id}"))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
