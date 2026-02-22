from __future__ import annotations

from typing import Any


def emit_alert(
    severity: str, event_type: str, summary: str, detail: dict[str, Any]
) -> None:
    _ = (severity, event_type, summary, detail)
    raise NotImplementedError(
        "Alerting integration is not implemented in this skeleton."
    )
