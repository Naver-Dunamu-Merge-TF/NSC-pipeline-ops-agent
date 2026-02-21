from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import TypeVar


class TransientMCPError(Exception):
    pass


class InvalidMCPResponseError(Exception):
    pass


JSONDict = dict[str, object]
T = TypeVar("T")


class SudocodeGateway:
    """Thin wrapper around Sudocode MCP callables.

    Retry policy is intentionally explicit: only ``TransientMCPError`` is retryable.
    All other exceptions are treated as permanent and are propagated immediately.
    """

    MAX_RETRIES = 3
    INITIAL_BACKOFF_SECONDS = 1.0
    RETRYABLE_EXCEPTIONS = (TransientMCPError,)

    def __init__(
        self,
        *,
        mcp_ready: Callable[[], object],
        mcp_show_issue: Callable[[str], JSONDict],
        mcp_upsert_issue: Callable[..., JSONDict],
        mcp_add_feedback: Callable[..., JSONDict],
        mcp_link: Callable[..., JSONDict],
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._mcp_ready = mcp_ready
        self._mcp_show_issue = mcp_show_issue
        self._mcp_upsert_issue = mcp_upsert_issue
        self._mcp_add_feedback = mcp_add_feedback
        self._mcp_link = mcp_link
        self._sleep = sleep

    def get_ready_issues(self) -> list[JSONDict]:
        payload = self._call_with_retry(self._mcp_ready)
        return self._extract_ready_issues(payload)

    def show_issue(self, issue_id: str) -> JSONDict:
        return self._call_with_retry(self._mcp_show_issue, issue_id)

    def set_issue_status(self, issue_id: str, status: str) -> None:
        self._call_with_retry(
            self._mcp_upsert_issue,
            issue_id=issue_id,
            status=status,
        )

    def add_feedback(self, issue_id: str, snapshot_json: str) -> None:
        self._call_with_retry(
            self._mcp_add_feedback,
            issue_id=issue_id,
            to_id=issue_id,
            content=snapshot_json,
        )

    def create_fix_issue(self, title: str, body: str) -> str:
        result = self._call_with_retry(
            self._mcp_upsert_issue,
            title=title,
            description=body,
        )
        issue_id = self._extract_issue_id(result)
        return issue_id

    def link_issues(self, from_id: str, to_id: str, relation: str) -> None:
        self._call_with_retry(
            self._mcp_link,
            from_id=from_id,
            to_id=to_id,
            type=relation,
        )

    def _extract_issue_id(self, payload: Mapping[str, object] | object) -> str:
        if not isinstance(payload, Mapping):
            raise InvalidMCPResponseError(
                "Expected mapping response with string 'issue_id' field"
            )

        issue_id = payload.get("issue_id")
        if not isinstance(issue_id, str) or not issue_id.strip():
            raise InvalidMCPResponseError(
                "Expected non-empty string field 'issue_id' in MCP response"
            )
        return issue_id

    def _extract_ready_issues(self, payload: object) -> list[JSONDict]:
        if isinstance(payload, Mapping):
            ready = payload.get("ready")
            if isinstance(ready, Mapping) and isinstance(ready.get("issues"), list):
                return self._coerce_issue_list(ready["issues"])

            issues = payload.get("issues")
            if isinstance(issues, list):
                return self._coerce_issue_list(issues)

        raise InvalidMCPResponseError("Expected ready payload with list field 'issues'")

    def _coerce_issue_list(self, issues: list[object]) -> list[JSONDict]:
        coerced: list[JSONDict] = []
        for issue in issues:
            if not isinstance(issue, Mapping):
                raise InvalidMCPResponseError(
                    "Expected each ready issue to be a mapping"
                )
            coerced.append(dict(issue))
        return coerced

    def _call_with_retry(
        self, fn: Callable[..., T], *args: object, **kwargs: object
    ) -> T:
        delay = self.INITIAL_BACKOFF_SECONDS
        for attempt in range(self.MAX_RETRIES):
            try:
                return fn(*args, **kwargs)
            except self.RETRYABLE_EXCEPTIONS:
                if attempt == self.MAX_RETRIES - 1:
                    raise
                self._sleep(delay)
                delay *= 2
        raise RuntimeError("Retry loop exhausted unexpectedly")
