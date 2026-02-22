from __future__ import annotations

from typing import Any


def collect_pipeline_context(pipeline: str, run_id: str | None) -> dict[str, Any]:
    _ = (pipeline, run_id)
    raise NotImplementedError("Data collection is not implemented in this skeleton.")
