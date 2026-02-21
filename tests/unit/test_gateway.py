from __future__ import annotations

from collections.abc import Callable

import pytest

from sudocode_orchestrator.gateway import (
    InvalidMCPResponseError,
    SudocodeGateway,
    TransientMCPError,
)


def _build_gateway(
    *,
    mcp_ready: Callable[[], object] | None = None,
    mcp_show_issue: Callable[[str], object] | None = None,
    mcp_upsert_issue: Callable[..., object] | None = None,
    mcp_add_feedback: Callable[..., object] | None = None,
    mcp_link: Callable[..., object] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> SudocodeGateway:
    return SudocodeGateway(
        mcp_ready=mcp_ready or (lambda: {"ready": {"issues": []}}),
        mcp_show_issue=mcp_show_issue or (lambda issue_id: {"issue_id": issue_id}),
        mcp_upsert_issue=mcp_upsert_issue or (lambda **kwargs: kwargs),
        mcp_add_feedback=mcp_add_feedback or (lambda **kwargs: kwargs),
        mcp_link=mcp_link or (lambda **kwargs: kwargs),
        sleep=sleep or (lambda _: None),
    )


def test_get_ready_issues_maps_to_mcp_ready() -> None:
    calls: list[str] = []

    def mcp_ready() -> dict[str, object]:
        calls.append("called")
        return {"ready": {"issues": [{"issue_id": "i-1", "priority": 0}]}}

    gateway = _build_gateway(mcp_ready=mcp_ready)

    result = gateway.get_ready_issues()

    assert result == [{"issue_id": "i-1", "priority": 0}]
    assert calls == ["called"]


def test_get_ready_issues_accepts_flat_issues_shape() -> None:
    gateway = _build_gateway(
        mcp_ready=lambda: {"issues": [{"issue_id": "i-2", "priority": 1}]}
    )

    result = gateway.get_ready_issues()

    assert result == [{"issue_id": "i-2", "priority": 1}]


def test_get_ready_issues_rejects_invalid_shape() -> None:
    gateway = _build_gateway(mcp_ready=lambda: {"ready": {"queue": []}})

    with pytest.raises(InvalidMCPResponseError, match="issues"):
        gateway.get_ready_issues()


def test_get_ready_issues_rejects_non_mapping_issue_item() -> None:
    gateway = _build_gateway(mcp_ready=lambda: {"issues": ["i-1"]})

    with pytest.raises(InvalidMCPResponseError, match="mapping"):
        gateway.get_ready_issues()


def test_show_issue_maps_to_mcp_show_issue() -> None:
    seen: list[str] = []

    def mcp_show_issue(issue_id: str) -> dict[str, str]:
        seen.append(issue_id)
        return {"issue_id": issue_id}

    gateway = _build_gateway(mcp_show_issue=mcp_show_issue)

    result = gateway.show_issue("i-abc")

    assert result == {"issue_id": "i-abc"}
    assert seen == ["i-abc"]


def test_set_issue_status_maps_to_upsert_issue() -> None:
    payloads: list[dict[str, str]] = []

    def mcp_upsert_issue(**kwargs: str) -> dict[str, str]:
        payloads.append(kwargs)
        return kwargs

    gateway = _build_gateway(mcp_upsert_issue=mcp_upsert_issue)

    gateway.set_issue_status("i-123", "in_progress")

    assert payloads == [{"issue_id": "i-123", "status": "in_progress"}]


def test_add_feedback_maps_to_mcp_add_feedback() -> None:
    payloads: list[dict[str, str]] = []

    def mcp_add_feedback(**kwargs: str) -> dict[str, str]:
        payloads.append(kwargs)
        return kwargs

    gateway = _build_gateway(mcp_add_feedback=mcp_add_feedback)

    gateway.add_feedback("i-77", '{"snapshot":true}')

    assert payloads == [
        {
            "issue_id": "i-77",
            "to_id": "i-77",
            "content": '{"snapshot":true}',
        }
    ]


def test_create_fix_issue_uses_upsert_and_returns_issue_id() -> None:
    payloads: list[dict[str, str]] = []

    def mcp_upsert_issue(**kwargs: str) -> dict[str, str]:
        payloads.append(kwargs)
        return {"issue_id": "i-fix1"}

    gateway = _build_gateway(mcp_upsert_issue=mcp_upsert_issue)

    result = gateway.create_fix_issue("Fix title", "Fix body")

    assert result == "i-fix1"
    assert payloads == [{"title": "Fix title", "description": "Fix body"}]


def test_create_fix_issue_raises_on_missing_issue_id() -> None:
    gateway = _build_gateway(mcp_upsert_issue=lambda **_: {"id": "i-fix1"})

    with pytest.raises(InvalidMCPResponseError, match="issue_id"):
        gateway.create_fix_issue("Fix title", "Fix body")


def test_create_fix_issue_raises_on_non_string_issue_id() -> None:
    gateway = _build_gateway(mcp_upsert_issue=lambda **_: {"issue_id": 123})

    with pytest.raises(InvalidMCPResponseError, match="issue_id"):
        gateway.create_fix_issue("Fix title", "Fix body")


def test_create_fix_issue_raises_on_empty_issue_id() -> None:
    gateway = _build_gateway(mcp_upsert_issue=lambda **_: {"issue_id": "  "})

    with pytest.raises(InvalidMCPResponseError, match="issue_id"):
        gateway.create_fix_issue("Fix title", "Fix body")


def test_link_issues_maps_to_mcp_link() -> None:
    payloads: list[dict[str, str]] = []

    def mcp_link(**kwargs: str) -> dict[str, str]:
        payloads.append(kwargs)
        return kwargs

    gateway = _build_gateway(mcp_link=mcp_link)

    gateway.link_issues("i-1", "i-2", "related")

    assert payloads == [{"from_id": "i-1", "to_id": "i-2", "type": "related"}]


def test_transient_failure_retries_with_exponential_backoff() -> None:
    calls = 0
    sleeps: list[float] = []

    def mcp_ready() -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise TransientMCPError("try again")
        return {"issues": [{"issue_id": "i-ok", "priority": 0}]}

    gateway = _build_gateway(mcp_ready=mcp_ready, sleep=sleeps.append)

    result = gateway.get_ready_issues()

    assert result == [{"issue_id": "i-ok", "priority": 0}]
    assert calls == 3
    assert sleeps == [1.0, 2.0]


def test_transient_failure_raises_after_max_retries() -> None:
    calls = 0
    sleeps: list[float] = []

    def mcp_ready() -> dict[str, object]:
        nonlocal calls
        calls += 1
        raise TransientMCPError("still failing")

    gateway = _build_gateway(mcp_ready=mcp_ready, sleep=sleeps.append)

    with pytest.raises(TransientMCPError):
        gateway.get_ready_issues()

    assert calls == 3
    assert sleeps == [1.0, 2.0]


def test_permanent_failure_propagates_without_retry() -> None:
    calls = 0
    sleeps: list[float] = []

    def mcp_ready() -> dict[str, object]:
        nonlocal calls
        calls += 1
        raise ValueError("permanent")

    gateway = _build_gateway(mcp_ready=mcp_ready, sleep=sleeps.append)

    with pytest.raises(ValueError):
        gateway.get_ready_issues()

    assert calls == 1
    assert sleeps == []
