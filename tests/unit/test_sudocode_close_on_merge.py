from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest


def _load_script_module() -> ModuleType:
    script_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "sudocode_close_on_merge.py"
    )
    spec = importlib.util.spec_from_file_location(
        "sudocode_close_on_merge", script_path
    )
    if spec is None or spec.loader is None:
        raise AssertionError("failed to load sudocode_close_on_merge.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SCRIPT = _load_script_module()


def _event(*, body: str, merged: bool = True) -> dict[str, object]:
    return {
        "pull_request": {
            "merged": merged,
            "html_url": "https://github.com/org/repo/pull/7",
            "merge_commit_sha": "deadbeef",
            "merged_at": "2026-02-21T00:00:00Z",
            "body": body,
        }
    }


def test_extract_sudocode_issue_id_accepts_single_canonical_line() -> None:
    body = "Intro\nSudocode-Issue: i-ab12\nFooter"

    issue_id = SCRIPT.extract_sudocode_issue_id(body)

    assert issue_id == "i-ab12"


def test_extract_sudocode_issue_id_rejects_missing_line() -> None:
    with pytest.raises(ValueError, match="missing canonical"):
        SCRIPT.extract_sudocode_issue_id("No canonical field here")


def test_extract_sudocode_issue_id_rejects_duplicate_lines() -> None:
    body = "Sudocode-Issue: i-ab12\nSudocode-Issue: i-cd34"

    with pytest.raises(ValueError, match="multiple Sudocode-Issue"):
        SCRIPT.extract_sudocode_issue_id(body)


def test_extract_sudocode_issue_id_rejects_malformed_line() -> None:
    body = "Sudocode-Issue: i-AB12"

    with pytest.raises(ValueError, match="missing canonical"):
        SCRIPT.extract_sudocode_issue_id(body)


def test_dispatch_from_event_invokes_merge_closer_for_valid_payload() -> None:
    calls: list[object] = []

    def fake_apply(**kwargs: object):
        calls.append(kwargs)
        return SCRIPT.MergeCloseResult(
            applied=True,
            reason="ok",
            feedback_marker="MERGE_CLOSE_APPLIED",
        )

    outcome = SCRIPT.dispatch_from_event(
        event=_event(body="Sudocode-Issue: i-ab12"),
        gateway=object(),
        apply_fn=fake_apply,
    )

    assert outcome.invoked is True
    assert outcome.result is not None
    assert outcome.payload is not None
    assert outcome.payload.issue_id == "i-ab12"
    assert len(calls) == 1


def test_dispatch_from_event_does_not_invoke_when_issue_id_missing() -> None:
    calls: list[object] = []

    def fake_apply(**kwargs: object):
        calls.append(kwargs)
        return SCRIPT.MergeCloseResult(
            applied=True,
            reason="ok",
            feedback_marker="MERGE_CLOSE_APPLIED",
        )

    outcome = SCRIPT.dispatch_from_event(
        event=_event(body="No issue line"),
        gateway=object(),
        apply_fn=fake_apply,
    )

    assert outcome.invoked is False
    assert outcome.payload is None
    assert outcome.result is None
    assert calls == []


def test_dispatch_from_event_does_not_invoke_when_issue_id_ambiguous() -> None:
    calls: list[object] = []

    def fake_apply(**kwargs: object):
        calls.append(kwargs)
        return SCRIPT.MergeCloseResult(
            applied=True,
            reason="ok",
            feedback_marker="MERGE_CLOSE_APPLIED",
        )

    outcome = SCRIPT.dispatch_from_event(
        event=_event(body="Sudocode-Issue: i-ab12\nSudocode-Issue: i-cd34"),
        gateway=object(),
        apply_fn=fake_apply,
    )

    assert outcome.invoked is False
    assert outcome.payload is None
    assert calls == []


def test_main_dry_run_event_file_outputs_preview(
    capsys: pytest.CaptureFixture[str],
) -> None:
    event_file = (
        Path(__file__).resolve().parents[1] / "fixtures" / "pr_merged_event.json"
    )

    exit_code = SCRIPT.main(["--event-file", str(event_file), "--dry-run"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["invoked"] is False
    assert payload["would_invoke_merge_closer"] is True
    assert payload["payload"]["issue_id"] == "i-ab12"


def test_main_dry_run_operator_mode_outputs_preview(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = SCRIPT.main(
        [
            "--issue-id",
            "i-ab12",
            "--pr-url",
            "https://github.com/org/repo/pull/1",
            "--merge-sha",
            "deadbeef",
            "--merged-at",
            "2026-02-21T00:00:00Z",
            "--dry-run",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["invoked"] is False
    assert payload["would_invoke_merge_closer"] is True
    assert payload["payload"]["issue_id"] == "i-ab12"
