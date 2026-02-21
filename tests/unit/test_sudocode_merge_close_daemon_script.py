from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType


def _load_script_module() -> ModuleType:
    script_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "sudocode_merge_close_daemon.py"
    )
    spec = importlib.util.spec_from_file_location(
        "sudocode_merge_close_daemon_script", script_path
    )
    if spec is None or spec.loader is None:
        raise AssertionError("failed to load sudocode_merge_close_daemon.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SCRIPT = _load_script_module()


def test_main_defaults_db_path_to_shared_cache(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    class _Poller:
        def __init__(self, **kwargs: object) -> None:
            captured["poller_kwargs"] = kwargs

    class _Gateway:
        def __init__(self, **kwargs: object) -> None:
            captured["gateway_kwargs"] = kwargs

    class _Daemon:
        def __init__(self, **kwargs: object) -> None:
            captured["daemon_kwargs"] = kwargs

        def run_once_with_lock(self) -> None:
            captured["ran_once"] = True

        def run_forever(self, *, poll_interval_seconds: float) -> None:
            captured["ran_forever"] = poll_interval_seconds

    monkeypatch.setattr(SCRIPT, "GhCliPoller", _Poller)
    monkeypatch.setattr(SCRIPT, "SudocodeCliGateway", _Gateway)
    monkeypatch.setattr(SCRIPT, "MergeCloseDaemon", _Daemon)

    exit_code = SCRIPT.main(
        [
            "--once",
            "--checkpoint",
            str(tmp_path / "checkpoint.json"),
            "--lock-file",
            str(tmp_path / "daemon.lock"),
            "--heartbeat",
            str(tmp_path / "heartbeat.json"),
        ]
    )

    assert exit_code == 0
    assert captured["ran_once"] is True
    gateway_kwargs = captured["gateway_kwargs"]
    assert isinstance(gateway_kwargs, dict)
    db_path = gateway_kwargs.get("db_path")
    assert isinstance(db_path, str)
    assert Path(db_path).is_absolute()
    assert "/.worktrees/" not in db_path
    assert db_path.endswith("/.sudocode/cache.db")
