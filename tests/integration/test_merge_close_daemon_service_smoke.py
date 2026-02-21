from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR)


def test_daemon_one_cycle_smoke_writes_heartbeat_and_checkpoint(tmp_path: Path) -> None:
    checkpoint_path = tmp_path / "checkpoint.json"
    heartbeat_path = tmp_path / "heartbeat.json"
    lock_path = tmp_path / "daemon.lock"
    gh_path = tmp_path / "gh"
    sudocode_path = tmp_path / "sudocode"

    _write_executable(
        gh_path,
        """#!/usr/bin/env python3
import json
import sys

if sys.argv[1:] == ["repo", "view", "--json", "nameWithOwner"]:
    print(json.dumps({"nameWithOwner": "acme/repo"}))
    raise SystemExit(0)

if len(sys.argv) >= 3 and sys.argv[1] == "api" and sys.argv[2] == "graphql":
    print(
        json.dumps(
            {
                "data": {
                    "repository": {
                        "pullRequests": {
                            "nodes": [],
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                        }
                    }
                }
            }
        )
    )
    raise SystemExit(0)

raise SystemExit(1)
""",
    )
    _write_executable(
        sudocode_path,
        """#!/usr/bin/env python3
raise SystemExit(0)
""",
    )

    command = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "sudocode_merge_close_daemon.py"),
        "--once",
        "--checkpoint",
        str(checkpoint_path),
        "--lock-file",
        str(lock_path),
        "--heartbeat",
        str(heartbeat_path),
        "--gh-bin",
        str(gh_path),
        "--sudocode-bin",
        str(sudocode_path),
    ]
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert checkpoint_path.exists()
    assert heartbeat_path.exists()

    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    heartbeat = json.loads(heartbeat_path.read_text(encoding="utf-8"))

    assert checkpoint["schema_version"] == 1
    assert checkpoint["safe_mode"] is False
    assert checkpoint["processed"] == {}
    assert heartbeat["safe_mode"] is False
    assert heartbeat["poll_ok"] is True
    assert isinstance(heartbeat["updated_at"], str)
    assert heartbeat["updated_at"]
