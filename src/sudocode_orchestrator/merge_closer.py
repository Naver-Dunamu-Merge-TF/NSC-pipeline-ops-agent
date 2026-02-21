from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Mapping, Protocol


@dataclass(frozen=True)
class MergeClosePayload:
    issue_id: str
    pr_url: str
    merge_sha: str
    merged_at: str
    merged: bool
    source: Literal["daemon", "workflow", "operator"]


@dataclass(frozen=True)
class MergeCloseResult:
    applied: bool
    reason: str
    feedback_marker: str


class MergeCloseGateway(Protocol):
    def show_issue(self, issue_id: str) -> object: ...

    def set_issue_status(self, issue_id: str, status: str) -> None: ...

    def add_feedback(self, issue_id: str, content: str) -> None: ...


def apply_merge_close(
    *, gateway: MergeCloseGateway, payload: MergeClosePayload
) -> MergeCloseResult:
    issue = _coerce_issue_payload(gateway.show_issue(payload.issue_id))
    issue_id = payload.issue_id
    status = _normalized_status(issue)
    history = _extract_feedback_history(issue)

    if status == "closed":
        if not _has_merge_close_applied_marker(history):
            _append_feedback(
                gateway,
                issue_id,
                "MERGE_CLOSE_APPLIED",
                reason="backfill merge-close marker for already closed issue",
                payload=payload,
            )

        marker = "MERGE_CLOSE_SKIPPED_ALREADY_CLOSED"
        _append_feedback(
            gateway,
            issue_id,
            marker,
            reason="issue already closed",
            payload=payload,
        )
        return MergeCloseResult(
            applied=False,
            reason="issue already closed",
            feedback_marker="MERGE_CLOSE_SKIPPED_ALREADY_CLOSED",
        )

    if status != "needs_review":
        reason = "close allowed only from needs_review"
        return _reject(gateway, issue_id, payload, reason)

    if not payload.merged:
        reason = "close requires merged=true precondition"
        return _reject(gateway, issue_id, payload, reason)

    review_gate_marker_at = _latest_review_gate_marker_timestamp(history)
    if review_gate_marker_at is None:
        reason = "missing review-gate marker in feedback history"
        return _reject(gateway, issue_id, payload, reason)

    latest_reopen_at = _latest_reopen_timestamp(history)
    if latest_reopen_at is not None and review_gate_marker_at <= latest_reopen_at:
        reason = "review-gate marker is older than last reopen"
        return _reject(gateway, issue_id, payload, reason)

    _append_feedback(
        gateway,
        issue_id,
        "MERGE_EVIDENCE_RECORDED",
        reason="merge evidence recorded",
        payload=payload,
    )

    gateway.set_issue_status(issue_id, "closed")
    _append_feedback(
        gateway,
        issue_id,
        "MERGE_CLOSE_APPLIED",
        reason="merge close applied",
        payload=payload,
    )

    if _is_fix_child(issue):
        for parent_id in _linked_parent_issue_ids(issue):
            parent_issue = _coerce_issue_payload(gateway.show_issue(parent_id))
            if _normalized_status(parent_issue) != "needs_review":
                continue
            gateway.set_issue_status(parent_id, "closed")
            _append_feedback(
                gateway,
                parent_id,
                "OVERFLOW_PARENT_CLOSED_BY_FIX",
                reason=f"closed by fix child {issue_id}",
                payload=payload,
            )

    return MergeCloseResult(
        applied=True,
        reason="merge close applied",
        feedback_marker="MERGE_CLOSE_APPLIED",
    )


def _has_merge_close_applied_marker(history: list[dict[str, object]]) -> bool:
    for entry in history:
        marker = entry.get("marker")
        if marker == "MERGE_CLOSE_APPLIED":
            return True
    return False


def _reject(
    gateway: MergeCloseGateway,
    issue_id: str,
    payload: MergeClosePayload,
    reason: str,
) -> MergeCloseResult:
    marker = "MERGE_CLOSE_REJECTED"
    _append_feedback(gateway, issue_id, marker, reason=reason, payload=payload)
    return MergeCloseResult(applied=False, reason=reason, feedback_marker=marker)


def _append_feedback(
    gateway: MergeCloseGateway,
    issue_id: str,
    marker: str,
    *,
    reason: str,
    payload: MergeClosePayload,
) -> None:
    content = json.dumps(
        {
            "marker": marker,
            "reason": reason,
            "issue_id": issue_id,
            "pr_url": payload.pr_url,
            "merge_sha": payload.merge_sha,
            "merged_at": payload.merged_at,
            "merged": payload.merged,
            "source": payload.source,
        },
        sort_keys=True,
    )
    gateway.add_feedback(issue_id, content)


def _coerce_issue_payload(payload: object) -> dict[str, object]:
    if isinstance(payload, Mapping) and isinstance(payload.get("issue"), Mapping):
        return dict(payload["issue"])
    if isinstance(payload, Mapping):
        return dict(payload)
    raise TypeError("show_issue payload must be a mapping")


def _normalized_status(issue: Mapping[str, object]) -> str:
    status = issue.get("status")
    if isinstance(status, str):
        return status.strip().lower()
    return ""


def _extract_feedback_history(issue: Mapping[str, object]) -> list[dict[str, object]]:
    for key in ("feedback_history", "feedback", "history", "feedback_entries"):
        raw = issue.get(key)
        if isinstance(raw, list):
            return [_coerce_history_entry(item) for item in raw]
    return []


def _coerce_history_entry(item: object) -> dict[str, object]:
    if isinstance(item, Mapping):
        if isinstance(item.get("content"), str):
            parsed = _parse_json_object(item["content"])
            if parsed is not None:
                return parsed
        return dict(item)
    if isinstance(item, str):
        parsed = _parse_json_object(item)
        if parsed is not None:
            return parsed
    return {}


def _parse_json_object(value: str) -> dict[str, object] | None:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        return parsed
    return None


def _latest_review_gate_marker_timestamp(
    history: list[dict[str, object]],
) -> datetime | None:
    latest: datetime | None = None
    for entry in history:
        event_type = entry.get("event_type")
        stage = entry.get("stage")
        status = entry.get("status")
        if event_type not in {"SESSION_DONE", "OVERFLOW_FIX_CREATED"}:
            continue
        if stage != "REVIEW_GATE" or status != "NEEDS_REVIEW":
            continue
        timestamp = _parse_timestamp(entry.get("timestamp"))
        if timestamp is None:
            continue
        if latest is None or timestamp > latest:
            latest = timestamp
    return latest


def _latest_reopen_timestamp(history: list[dict[str, object]]) -> datetime | None:
    latest: datetime | None = None
    for entry in history:
        event_type = entry.get("event_type")
        status = entry.get("status")
        is_reopen = event_type in {"SESSION_REOPENED", "ISSUE_REOPENED"} or (
            isinstance(status, str) and status.strip().upper() == "OPEN"
        )
        if not is_reopen:
            continue
        timestamp = _parse_timestamp(entry.get("timestamp"))
        if timestamp is None:
            continue
        if latest is None or timestamp > latest:
            latest = timestamp
    return latest


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_fix_child(issue: Mapping[str, object]) -> bool:
    title = issue.get("title")
    return isinstance(title, str) and title.startswith("[FIX]")


def _linked_parent_issue_ids(issue: Mapping[str, object]) -> list[str]:
    parent_ids: set[str] = set()
    linked_parents = issue.get("linked_parents")
    if isinstance(linked_parents, list):
        for item in linked_parents:
            if isinstance(item, Mapping) and isinstance(item.get("issue_id"), str):
                parent_ids.add(item["issue_id"])

    current_issue_id = issue.get("issue_id")

    relationships = issue.get("relationships")
    if isinstance(current_issue_id, str) and isinstance(relationships, Mapping):
        incoming = relationships.get("incoming")
        if isinstance(incoming, list):
            for relation in incoming:
                if not isinstance(relation, Mapping):
                    continue
                from_id = relation.get("from_id")
                to_id = relation.get("to_id")
                relation_type = relation.get("relationship_type")
                if not isinstance(from_id, str) or not isinstance(to_id, str):
                    continue
                if to_id != current_issue_id:
                    continue
                if relation_type not in ("depends-on", "depends_on"):
                    continue
                parent_ids.add(from_id)

    links = issue.get("links")
    if isinstance(current_issue_id, str) and isinstance(links, list):
        for link in links:
            if not isinstance(link, Mapping):
                continue
            from_id = link.get("from_id")
            to_id = link.get("to_id")
            relation = link.get("type")
            if not isinstance(from_id, str) or not isinstance(to_id, str):
                continue
            if to_id != current_issue_id:
                continue
            if relation not in ("depends-on", "depends_on"):
                continue
            parent_ids.add(from_id)

    return sorted(parent_ids)
