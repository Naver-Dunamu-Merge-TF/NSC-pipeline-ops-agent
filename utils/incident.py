from __future__ import annotations

try:
    from orchestrator.utils.incident import make_fingerprint, make_incident_id
except ModuleNotFoundError as exc:
    if exc.name is None or exc.name.split(".", 1)[0] != "orchestrator":
        raise
    from src.orchestrator.utils.incident import make_fingerprint, make_incident_id

__all__ = ["make_incident_id", "make_fingerprint"]
