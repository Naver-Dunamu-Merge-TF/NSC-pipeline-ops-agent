from __future__ import annotations

try:
    from orchestrator.utils.time import parse_pipeline_ts, to_kst, to_utc
except ModuleNotFoundError as exc:
    if exc.name is None or exc.name.split(".", 1)[0] != "orchestrator":
        raise
    from src.orchestrator.utils.time import parse_pipeline_ts, to_kst, to_utc

__all__ = ["parse_pipeline_ts", "to_utc", "to_kst"]
