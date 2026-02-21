from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable, Literal, Mapping

from .merge_closer import MergeClosePayload, MergeCloseResult, apply_merge_close

ISSUE_FIELD_RE = re.compile(r"^Sudocode-Issue:\s*(i-[a-z0-9]+)\s*$", re.MULTILINE)
CloseSource = Literal["daemon", "workflow", "operator"]
ApplyFn = Callable[..., MergeCloseResult]


@dataclass(frozen=True)
class DispatchOutcome:
    invoked: bool
    reason: str
    payload: MergeClosePayload | None
    result: MergeCloseResult | None


def extract_sudocode_issue_id(pr_body: str) -> str:
    matches = ISSUE_FIELD_RE.findall(pr_body)
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ValueError("missing canonical Sudocode-Issue line in PR body")
    raise ValueError("multiple Sudocode-Issue lines found in PR body")


def build_payload_from_event(
    event: Mapping[str, object],
    *,
    source: CloseSource = "workflow",
) -> MergeClosePayload:
    pull_request = _as_mapping(event.get("pull_request"), "pull_request")
    merged = pull_request.get("merged") is True
    if not merged:
        raise ValueError("pull_request.merged must be true")

    body_raw = pull_request.get("body")
    body = body_raw if isinstance(body_raw, str) else ""
    issue_id = extract_sudocode_issue_id(body)

    return MergeClosePayload(
        issue_id=issue_id,
        pr_url=_required_str(pull_request, "html_url", "pull_request.html_url"),
        merge_sha=_required_str(
            pull_request,
            "merge_commit_sha",
            "pull_request.merge_commit_sha",
        ),
        merged_at=_required_str(pull_request, "merged_at", "pull_request.merged_at"),
        merged=merged,
        source=source,
    )


def build_operator_payload(
    *,
    issue_id: str,
    pr_url: str,
    merge_sha: str,
    merged_at: str,
    source: CloseSource = "operator",
) -> MergeClosePayload:
    return MergeClosePayload(
        issue_id=issue_id.strip(),
        pr_url=pr_url.strip(),
        merge_sha=merge_sha.strip(),
        merged_at=merged_at.strip(),
        merged=True,
        source=source,
    )


def dispatch_from_event(
    *,
    event: Mapping[str, object],
    gateway: object,
    source: CloseSource = "workflow",
    apply_fn: ApplyFn = apply_merge_close,
) -> DispatchOutcome:
    try:
        payload = build_payload_from_event(event, source=source)
    except ValueError as exc:
        return DispatchOutcome(
            invoked=False,
            reason=str(exc),
            payload=None,
            result=None,
        )
    return dispatch_merge_close(payload=payload, gateway=gateway, apply_fn=apply_fn)


def dispatch_merge_close(
    *,
    payload: MergeClosePayload,
    gateway: object,
    apply_fn: ApplyFn = apply_merge_close,
) -> DispatchOutcome:
    result = apply_fn(gateway=gateway, payload=payload)
    return DispatchOutcome(
        invoked=True,
        reason="merge closer invoked",
        payload=payload,
        result=result,
    )


def preview_from_event(
    *,
    event: Mapping[str, object],
    source: CloseSource = "workflow",
) -> DispatchOutcome:
    try:
        payload = build_payload_from_event(event, source=source)
    except ValueError as exc:
        return DispatchOutcome(
            invoked=False,
            reason=str(exc),
            payload=None,
            result=None,
        )
    return DispatchOutcome(
        invoked=False,
        reason="dry-run: merge closer invocation skipped",
        payload=payload,
        result=None,
    )


def _as_mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be an object")
    return value


def _required_str(mapping: Mapping[str, object], key: str, field_name: str) -> str:
    value = mapping.get(key)
    if isinstance(value, str) and value.strip():
        return value
    raise ValueError(f"{field_name} must be a non-empty string")
