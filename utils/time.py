from __future__ import annotations

from datetime import datetime


def to_utc(value: str) -> datetime:
    _ = value
    raise NotImplementedError("UTC conversion is not implemented in this skeleton.")


def to_kst(value: str) -> datetime:
    _ = value
    raise NotImplementedError("KST conversion is not implemented in this skeleton.")


def parse_pipeline_ts(value: str) -> datetime:
    _ = value
    raise NotImplementedError(
        "Pipeline timestamp parsing is not implemented in this skeleton."
    )
