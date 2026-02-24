from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

import pytest

from utils.incident import make_fingerprint


_ALLOWED_SMOKE_ENVS = ("dev", "staging")


def _runtime_input_path(environ: Mapping[str, str]) -> Path:
    target_env = (environ.get("DEV012_SMOKE_ENV", "dev").strip() or "dev").lower()
    explicit_path = environ.get("DEV012_RUNTIME_INPUT_PATH", "").strip()
    if explicit_path:
        return Path(explicit_path)

    return (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "runtime_inputs"
        / f"{target_env}_incident_input.json"
    )


def _smoke_skip_reason(environ: Mapping[str, str]) -> str | None:
    run_smoke = environ.get("RUN_DEV012_FINGERPRINT_SMOKE", "").strip()
    if run_smoke != "1":
        return "Set RUN_DEV012_FINGERPRINT_SMOKE=1 to run fingerprint smoke test"

    target_env = (environ.get("DEV012_SMOKE_ENV", "dev").strip() or "dev").lower()
    if target_env not in _ALLOWED_SMOKE_ENVS:
        return "DEV012_SMOKE_ENV must be one of: dev, staging"

    runtime_input_path = _runtime_input_path(environ)
    if not runtime_input_path.is_file():
        return f"Runtime input file not found: {runtime_input_path}"

    return None


def _load_runtime_input(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Runtime input payload must be a JSON object")
    return payload


def _emit_artifact(environ: Mapping[str, str], artifact: dict[str, Any]) -> None:
    line = json.dumps(artifact, sort_keys=True, ensure_ascii=True)
    artifact_file = environ.get("DEV012_FINGERPRINT_SMOKE_ARTIFACT_FILE", "").strip()
    if artifact_file:
        artifact_path = Path(artifact_file)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        with artifact_path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.write("\n")
    print(line)


def test_dev_staging_runtime_input_fingerprint_reproducibility_smoke() -> None:
    skip_reason = _smoke_skip_reason(os.environ)
    if skip_reason:
        pytest.skip(skip_reason)

    target_env = (os.getenv("DEV012_SMOKE_ENV", "dev").strip() or "dev").lower()
    runtime_input_path = _runtime_input_path(os.environ)
    payload = _load_runtime_input(runtime_input_path)

    pipeline = str(payload["pipeline"])
    run_id = payload.get("run_id")
    detected_issues = payload.get("detected_issues") or []
    if not isinstance(detected_issues, list):
        raise ValueError("detected_issues must be a list")

    first = make_fingerprint(pipeline, run_id, detected_issues)
    second = make_fingerprint(pipeline, run_id, list(reversed(detected_issues)))

    assert first == second
    assert first

    artifact = {
        "fingerprint": first,
        "input_sha256": hashlib.sha256(runtime_input_path.read_bytes()).hexdigest(),
        "result": "pass",
        "runtime_input_path": str(runtime_input_path),
        "smoke_env": target_env,
        "timestamp_utc": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    _emit_artifact(os.environ, artifact)
