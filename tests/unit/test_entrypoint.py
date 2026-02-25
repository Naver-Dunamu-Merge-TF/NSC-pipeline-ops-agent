from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import entrypoint


def test_entrypoint_calls_watchdog_run_once(monkeypatch) -> None:
    called: dict[str, bool] = {"run_once": False}

    def _fake_run_once() -> dict[str, object]:
        called["run_once"] = True
        return {
            "target_pipelines": ["pipeline_silver"],
            "polled_pipelines": ["pipeline_silver"],
        }

    monkeypatch.setattr("runtime.watchdog.run_once", _fake_run_once)

    assert entrypoint.main() == 0
    assert called["run_once"] is True


def test_entrypoint_imports_without_src_pythonpath() -> None:
    project_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    result = subprocess.run(
        [sys.executable, "-c", "import entrypoint"],
        cwd=project_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
