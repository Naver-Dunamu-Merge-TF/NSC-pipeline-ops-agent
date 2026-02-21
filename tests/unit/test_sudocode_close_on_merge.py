from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from types import ModuleType

import pytest
from sudocode_orchestrator import close_on_merge_runtime as RUNTIME


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

    issue_id = RUNTIME.extract_sudocode_issue_id(body)

    assert issue_id == "i-ab12"


def test_extract_sudocode_issue_id_rejects_missing_line() -> None:
    with pytest.raises(ValueError, match="missing canonical"):
        RUNTIME.extract_sudocode_issue_id("No canonical field here")


def test_extract_sudocode_issue_id_rejects_duplicate_lines() -> None:
    body = "Sudocode-Issue: i-ab12\nSudocode-Issue: i-cd34"

    with pytest.raises(ValueError, match="multiple Sudocode-Issue"):
        RUNTIME.extract_sudocode_issue_id(body)


def test_extract_sudocode_issue_id_rejects_malformed_line() -> None:
    body = "Sudocode-Issue: i-AB12"

    with pytest.raises(ValueError, match="missing canonical"):
        RUNTIME.extract_sudocode_issue_id(body)


def test_dispatch_from_event_invokes_merge_closer_for_valid_payload() -> None:
    calls: list[object] = []

    def fake_apply(**kwargs: object):
        calls.append(kwargs)
        return RUNTIME.MergeCloseResult(
            applied=True,
            reason="ok",
            feedback_marker="MERGE_CLOSE_APPLIED",
        )

    outcome = RUNTIME.dispatch_from_event(
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
        return RUNTIME.MergeCloseResult(
            applied=True,
            reason="ok",
            feedback_marker="MERGE_CLOSE_APPLIED",
        )

    outcome = RUNTIME.dispatch_from_event(
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
        return RUNTIME.MergeCloseResult(
            applied=True,
            reason="ok",
            feedback_marker="MERGE_CLOSE_APPLIED",
        )

    outcome = RUNTIME.dispatch_from_event(
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


def test_main_dry_run_event_path_never_calls_mutation_dispatch(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_file = (
        Path(__file__).resolve().parents[1] / "fixtures" / "pr_merged_event.json"
    )
    called = False

    def _boom(*args: object, **kwargs: object):
        nonlocal called
        called = True
        raise AssertionError("dispatch_merge_close must not be called in dry-run")

    monkeypatch.setattr(SCRIPT, "dispatch_merge_close", _boom)

    exit_code = SCRIPT.main(["--event-file", str(event_file), "--dry-run"])

    assert exit_code == 0
    assert called is False
    payload = json.loads(capsys.readouterr().out)
    assert payload["invoked"] is False


def test_workflow_event_path_runs_audit_only_dry_run() -> None:
    workflow_path = (
        Path(__file__).resolve().parents[2]
        / ".github"
        / "workflows"
        / "sudocode-close-on-merge.yml"
    )
    workflow_text = workflow_path.read_text(encoding="utf-8")

    assert '--event-file "$GITHUB_EVENT_PATH" --dry-run' in workflow_text
    assert "--issue-id" not in workflow_text
    assert "--pr-url" not in workflow_text
    assert "--merge-sha" not in workflow_text
    assert "--merged-at" not in workflow_text


def test_main_rejects_workflow_source_without_dry_run(
    capsys: pytest.CaptureFixture[str],
) -> None:
    event_file = (
        Path(__file__).resolve().parents[1] / "fixtures" / "pr_merged_event.json"
    )

    with pytest.raises(SystemExit) as exc:
        SCRIPT.main(["--event-file", str(event_file), "--source", "workflow"])

    assert exc.value.code == 2
    assert "--event-file mode requires --dry-run" in capsys.readouterr().err


def test_main_rejects_event_file_without_dry_run(
    capsys: pytest.CaptureFixture[str],
) -> None:
    event_file = (
        Path(__file__).resolve().parents[1] / "fixtures" / "pr_merged_event.json"
    )

    with pytest.raises(SystemExit) as exc:
        SCRIPT.main(["--event-file", str(event_file)])

    assert exc.value.code == 2
    assert "--event-file mode requires --dry-run" in capsys.readouterr().err


def test_main_rejects_event_file_without_dry_run_even_with_daemon_source(
    capsys: pytest.CaptureFixture[str],
) -> None:
    event_file = (
        Path(__file__).resolve().parents[1] / "fixtures" / "pr_merged_event.json"
    )

    with pytest.raises(SystemExit) as exc:
        SCRIPT.main(["--event-file", str(event_file), "--source", "daemon"])

    assert exc.value.code == 2
    assert "--event-file mode requires --dry-run" in capsys.readouterr().err


def test_main_rejects_operator_mode_with_workflow_source(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc:
        SCRIPT.main(
            [
                "--issue-id",
                "i-ab12",
                "--pr-url",
                "https://github.com/org/repo/pull/1",
                "--merge-sha",
                "deadbeef",
                "--merged-at",
                "2026-02-21T00:00:00Z",
                "--source",
                "workflow",
            ]
        )

    assert exc.value.code == 2
    assert "operator mode cannot use --source workflow" in capsys.readouterr().err


def test_gateway_bootstraps_db_from_jsonl_when_issue_not_found(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    responses = iter(
        [
            SimpleNamespace(
                returncode=1, stdout="", stderr="✗ Issue not found: i-5swp"
            ),
            SimpleNamespace(returncode=0, stdout="✓ Imported from JSONL\n", stderr=""),
            SimpleNamespace(returncode=0, stdout='{"id":"i-5swp"}\n', stderr=""),
        ]
    )

    def fake_run(*args: object, **kwargs: object) -> object:
        del kwargs
        command = args[0]
        assert isinstance(command, list)
        calls.append(command)
        return next(responses)

    gateway = SCRIPT.SudocodeCliGateway(
        working_dir=tmp_path,
        sudocode_bin="sudocode",
        db_path="/tmp/sudocode-ci-sim.db",
        run_fn=fake_run,
    )

    issue = gateway.show_issue("i-5swp")

    assert issue["id"] == "i-5swp"
    assert calls[0][-3:] == ["issue", "show", "i-5swp"]
    assert calls[1][-3:] == ["import", "-i", str((tmp_path / ".sudocode").resolve())]
    assert calls[2][-3:] == ["issue", "show", "i-5swp"]


def test_gateway_bootstrap_uses_explicit_shared_sudocode_dir(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    responses = iter(
        [
            SimpleNamespace(
                returncode=1, stdout="", stderr="✗ Issue not found: i-5swp"
            ),
            SimpleNamespace(returncode=0, stdout="✓ Imported from JSONL\n", stderr=""),
            SimpleNamespace(returncode=0, stdout='{"id":"i-5swp"}\n', stderr=""),
        ]
    )

    def fake_run(*args: object, **kwargs: object) -> object:
        del kwargs
        command = args[0]
        assert isinstance(command, list)
        calls.append(command)
        return next(responses)

    shared_sudocode_dir = tmp_path / "shared" / ".sudocode"
    gateway = SCRIPT.SudocodeCliGateway(
        working_dir=tmp_path,
        sudocode_bin="sudocode",
        db_path="/tmp/sudocode-ci-sim.db",
        sudocode_dir=shared_sudocode_dir,
        run_fn=fake_run,
    )

    issue = gateway.show_issue("i-5swp")

    assert issue["id"] == "i-5swp"
    assert calls[1][-3:] == ["import", "-i", str(shared_sudocode_dir)]


def test_gateway_does_not_bootstrap_on_non_lookup_failure(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(*args: object, **kwargs: object) -> object:
        del kwargs
        command = args[0]
        assert isinstance(command, list)
        calls.append(command)
        return SimpleNamespace(returncode=1, stdout="", stderr="database locked")

    gateway = SCRIPT.SudocodeCliGateway(
        working_dir=tmp_path,
        sudocode_bin="sudocode",
        sudocode_dir=tmp_path / ".sudocode",
        run_fn=fake_run,
    )

    with pytest.raises(RuntimeError, match="database locked"):
        gateway.show_issue("i-5swp")

    assert len(calls) == 1
