from __future__ import annotations

from typing import Any


def run_domain_validation(pipeline: str, run_id: str | None) -> dict[str, Any]:
    _ = (pipeline, run_id)
    raise NotImplementedError("Domain validation is not implemented in this skeleton.")
