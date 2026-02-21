from __future__ import annotations

import json
from pathlib import Path
import stat
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR)


def test_operator_fallback_closes_issue_via_merge_closer_path(tmp_path: Path) -> None:
    state_path = tmp_path / "fake-sudocode-state.json"
    state_path.write_text(
        json.dumps(
            {
                "issues": {
                    "i-canary": {
                        "issue_id": "i-canary",
                        "status": "needs_review",
                        "feedback_history": [
                            {
                                "event_type": "SESSION_DONE",
                                "stage": "REVIEW_GATE",
                                "status": "NEEDS_REVIEW",
                                "timestamp": "2026-02-22T09:59:00Z",
                            }
                        ],
                    }
                }
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    sudocode_path = tmp_path / "sudocode"
    _write_executable(
        sudocode_path,
        """#!/usr/bin/env python3
import json
from pathlib import Path
import sys


def _load(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"issues": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _issue(state: dict[str, object], issue_id: str) -> dict[str, object]:
    issues = state.setdefault("issues", {})
    assert isinstance(issues, dict)
    issue = issues.setdefault(
        issue_id,
        {
            "issue_id": issue_id,
            "status": "open",
            "feedback_history": [],
        },
    )
    assert isinstance(issue, dict)
    return issue


args = sys.argv[1:]
db_path = None
if len(args) >= 2 and args[0] == "--db":
    db_path = args[1]
    args = args[2:]
state_file = Path(db_path) if db_path is not None else Path("state.json")

if not args or args[0] != "--json":
    raise SystemExit(2)
args = args[1:]

state = _load(state_file)

if args[:2] == ["issue", "show"] and len(args) >= 3:
    issue_id = args[2]
    issues = state.get("issues", {})
    if not isinstance(issues, dict) or issue_id not in issues:
        sys.stderr.write(f"Issue not found: {issue_id}")
        raise SystemExit(1)
    print(json.dumps(issues[issue_id], sort_keys=True))
    raise SystemExit(0)

if args[:2] == ["issue", "update"] and len(args) >= 5:
    issue_id = args[2]
    status_index = args.index("--status")
    new_status = args[status_index + 1]
    issue = _issue(state, issue_id)
    issue["status"] = new_status
    _save(state_file, state)
    print(json.dumps({"issue_id": issue_id, "status": new_status}, sort_keys=True))
    raise SystemExit(0)

if args[:2] == ["feedback", "add"] and len(args) >= 6:
    issue_id = args[2]
    content_index = args.index("--content")
    content = args[content_index + 1]
    issue = _issue(state, issue_id)
    history = issue.setdefault("feedback_history", [])
    assert isinstance(history, list)
    history.append({"content": content})
    _save(state_file, state)
    print(json.dumps({"ok": True}, sort_keys=True))
    raise SystemExit(0)

sys.stderr.write("unsupported fake sudocode command")
raise SystemExit(1)
""",
    )

    command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "sudocode_close_on_merge.py"),
        "--issue-id",
        "i-canary",
        "--pr-url",
        "https://github.com/acme/repo/pull/901",
        "--merge-sha",
        "sha-canary",
        "--merged-at",
        "2026-02-22T10:00:00Z",
        "--source",
        "operator",
        "--sudocode-bin",
        str(sudocode_path),
        "--db-path",
        str(state_path),
    ]
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert payload["invoked"] is True
    assert payload["result"]["applied"] is True
    assert payload["result"]["feedback_marker"] == "MERGE_CLOSE_APPLIED"

    state = json.loads(state_path.read_text(encoding="utf-8"))
    issue = state["issues"]["i-canary"]
    assert issue["status"] == "closed"

    markers: list[str] = []
    sources: list[str] = []
    for entry in issue["feedback_history"]:
        content = entry.get("content")
        if not isinstance(content, str):
            continue
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            continue
        marker = parsed.get("marker")
        source = parsed.get("source")
        if isinstance(marker, str):
            markers.append(marker)
        if isinstance(source, str):
            sources.append(source)

    assert "MERGE_EVIDENCE_RECORDED" in markers
    assert "MERGE_CLOSE_APPLIED" in markers
    assert "operator" in sources
