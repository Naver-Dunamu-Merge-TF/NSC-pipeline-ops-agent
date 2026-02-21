from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from sudocode_orchestrator.agent_roles import RoleAgentAdapter
from sudocode_orchestrator.models import ImplementerResult


def test_implementer_parses_result_with_verification() -> None:
    calls: list[tuple[str, str]] = []

    def transport(role: str, prompt: str) -> str:
        calls.append((role, prompt))
        assert "rendered prompt" in prompt
        return json.dumps(
            {
                "code_changed_at": "2026-02-21T10:00:00+00:00",
                "notes": "implemented changes",
                "verification": {
                    "command": "python -m pytest tests/unit -x",
                    "output": "ok",
                    "exit_code": 0,
                    "produced_at": "2026-02-21T10:00:05+00:00",
                },
            }
        )

    adapter = RoleAgentAdapter(transport=transport)
    result = adapter.implementer("rendered prompt", ["fix item 1"])

    assert calls[0][0] == "implementer"
    assert "fix item 1" in calls[0][1]
    assert result.notes == "implemented changes"
    assert result.code_changed_at == datetime(2026, 2, 21, 10, 0, tzinfo=timezone.utc)
    assert result.verification is not None
    assert result.verification.command == "python -m pytest tests/unit -x"
    assert result.verification.exit_code == 0


def test_implementer_parses_result_without_verification() -> None:
    def transport(role: str, prompt: str) -> str:
        assert role == "implementer"
        return json.dumps(
            {
                "code_changed_at": "2026-02-21T10:30:00+00:00",
                "notes": "implemented without test output",
            }
        )

    adapter = RoleAgentAdapter(transport=transport)
    result = adapter.implementer("rendered prompt", None)

    assert result.verification is None
    assert result.notes == "implemented without test output"


def test_spec_and_quality_reviewers_parse_review_result() -> None:
    calls: list[tuple[str, str]] = []

    def transport(role: str, prompt: str) -> str:
        calls.append((role, prompt))
        return json.dumps(
            {
                "passed": role == "spec_reviewer",
                "failed_items": [] if role == "spec_reviewer" else ["readability"],
                "fix_list": [] if role == "spec_reviewer" else ["extract helper"],
                "notes": f"{role} notes",
            }
        )

    adapter = RoleAgentAdapter(transport=transport)
    implementer_result = ImplementerResult(
        verification=None,
        code_changed_at=datetime(2026, 2, 21, 10, 45, tzinfo=timezone.utc),
        notes="impl",
    )

    spec_result = adapter.spec_reviewer("rendered prompt", implementer_result, 1)
    quality_result = adapter.quality_reviewer("rendered prompt", implementer_result, 2)

    assert calls[0][0] == "spec_reviewer"
    assert calls[1][0] == "quality_reviewer"
    assert "attempt: 1" in calls[0][1]
    assert "attempt: 2" in calls[1][1]
    assert spec_result.passed is True
    assert quality_result.passed is False
    assert quality_result.failed_items == ["readability"]
    assert quality_result.fix_list == ["extract helper"]


def test_malformed_implementer_output_raises_clear_error() -> None:
    def transport(_: str, __: str) -> str:
        return "not json"

    adapter = RoleAgentAdapter(transport=transport)

    with pytest.raises(ValueError, match="Malformed implementer output"):
        adapter.implementer("rendered prompt", None)


def test_malformed_reviewer_output_raises_clear_error() -> None:
    def transport(role: str, _: str) -> str:
        if role == "spec_reviewer":
            return json.dumps(
                {
                    "passed": "yes",
                    "failed_items": [],
                    "fix_list": [],
                    "notes": "bad passed type",
                }
            )
        return "{}"

    adapter = RoleAgentAdapter(transport=transport)
    implementer_result = ImplementerResult(
        verification=None,
        code_changed_at=datetime(2026, 2, 21, 10, 45, tzinfo=timezone.utc),
        notes="impl",
    )

    with pytest.raises(ValueError, match="Malformed spec reviewer output"):
        adapter.spec_reviewer("rendered prompt", implementer_result, 1)


def test_implementer_rejects_bool_verification_exit_code() -> None:
    def transport(_: str, __: str) -> str:
        return json.dumps(
            {
                "code_changed_at": "2026-02-21T10:00:00+00:00",
                "notes": "implemented changes",
                "verification": {
                    "command": "python -m pytest tests/unit -x",
                    "output": "ok",
                    "exit_code": True,
                    "produced_at": "2026-02-21T10:00:05+00:00",
                },
            }
        )

    adapter = RoleAgentAdapter(transport=transport)

    with pytest.raises(
        ValueError,
        match="Malformed implementer output: 'verification.exit_code' must be an int",
    ):
        adapter.implementer("rendered prompt", None)


def test_implementer_rejects_naive_code_changed_at_datetime() -> None:
    def transport(_: str, __: str) -> str:
        return json.dumps(
            {
                "code_changed_at": "2026-02-21T10:00:00",
                "notes": "implemented changes",
            }
        )

    adapter = RoleAgentAdapter(transport=transport)

    with pytest.raises(
        ValueError,
        match="Malformed implementer output: 'code_changed_at' must be timezone-aware ISO datetime",
    ):
        adapter.implementer("rendered prompt", None)


def test_implementer_rejects_naive_verification_produced_at_datetime() -> None:
    def transport(_: str, __: str) -> str:
        return json.dumps(
            {
                "code_changed_at": "2026-02-21T10:00:00+00:00",
                "notes": "implemented changes",
                "verification": {
                    "command": "python -m pytest tests/unit -x",
                    "output": "ok",
                    "exit_code": 0,
                    "produced_at": "2026-02-21T10:00:05",
                },
            }
        )

    adapter = RoleAgentAdapter(transport=transport)

    with pytest.raises(
        ValueError,
        match="Malformed implementer output: 'verification.produced_at' must be timezone-aware ISO datetime",
    ):
        adapter.implementer("rendered prompt", None)
