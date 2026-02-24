from __future__ import annotations

import hashlib
import json
from typing import Any


def make_incident_id(pipeline: str, run_id: str | None, detected_at: str) -> str:
    payload = {
        "detected_at": detected_at,
        "pipeline": pipeline,
        "run_id": run_id,
    }
    digest = hashlib.sha256(_stable_json(payload).encode("ascii")).hexdigest()
    return f"inc-{digest[:16]}"


def make_fingerprint(
    pipeline: str, run_id: str | None, detected_issues: list[Any] | None
) -> str:
    canonical_issues = _canonicalize_detected_issues(detected_issues or [])
    payload = {
        "detected_issues": canonical_issues,
        "pipeline": pipeline,
        "run_id": run_id,
    }
    digest = hashlib.sha256(_stable_json(payload).encode("ascii")).hexdigest()
    return digest


def _canonicalize_detected_issues(detected_issues: list[Any]) -> list[str]:
    return sorted(_stable_json(issue) for issue in detected_issues)


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


__all__ = ["make_incident_id", "make_fingerprint"]
