from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Mapping
from urllib import error, request

TRIAGE_READY = "TRIAGE_READY"
APPROVAL_TIMEOUT = "APPROVAL_TIMEOUT"
EXECUTION_FAILED = "EXECUTION_FAILED"
POSTMORTEM_FAILED = "POSTMORTEM_FAILED"

SEVERITY_INFO = "INFO"
SEVERITY_WARNING = "WARNING"
SEVERITY_ERROR = "ERROR"
SEVERITY_CRITICAL = "CRITICAL"


class AlertError(RuntimeError):
    def __init__(
        self, *, classification: str, event_type: str, target: str, reason: str
    ) -> None:
        self.classification = classification
        self.event_type = event_type
        self.target = target
        self.reason = reason
        super().__init__(
            f"[ALERT][{classification}] event_type={event_type} target={target} reason={reason}"
        )


class TransientAlertError(AlertError):
    def __init__(self, *, event_type: str, target: str, reason: str) -> None:
        super().__init__(
            classification="TRANSIENT",
            event_type=event_type,
            target=target,
            reason=reason,
        )


class PermanentAlertError(AlertError):
    def __init__(self, *, event_type: str, target: str, reason: str) -> None:
        super().__init__(
            classification="PERMANENT",
            event_type=event_type,
            target=target,
            reason=reason,
        )


def emit_alert(
    severity: str,
    event_type: str,
    summary: str,
    detail: dict[str, Any],
    *,
    environ: Mapping[str, str] | None = None,
    sender: Any | None = None,
) -> None:
    env = environ if environ is not None else os.environ
    endpoint = env.get("LOG_ANALYTICS_DCR_ENDPOINT", "").strip()
    dcr_immutable_id = env.get("LOG_ANALYTICS_DCR_IMMUTABLE_ID", "").strip()
    stream_name = env.get("LOG_ANALYTICS_STREAM_NAME", "").strip()
    api_version = env.get("LOG_ANALYTICS_DCR_API_VERSION", "2023-01-01").strip()
    timeout_seconds = _parse_timeout(env.get("ALERTING_HTTP_TIMEOUT_SECONDS", "5"))
    max_retries = _parse_retry_count(env.get("ALERTING_MAX_RETRIES", "2"))

    if not endpoint or not dcr_immutable_id or not stream_name:
        raise PermanentAlertError(
            event_type=event_type,
            target="dcr-config",
            reason=(
                "missing LOG_ANALYTICS_DCR_ENDPOINT/LOG_ANALYTICS_DCR_IMMUTABLE_ID/"
                "LOG_ANALYTICS_STREAM_NAME"
            ),
        )

    url = (
        f"{endpoint.rstrip('/')}"
        f"/dataCollectionRules/{dcr_immutable_id}/streams/{stream_name}"
        f"?api-version={api_version}"
    )
    body = _serialize_event_payload(
        severity=severity,
        event_type=event_type,
        summary=summary,
        detail=detail,
    )
    req = request.Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    send = sender if sender is not None else _default_sender

    for attempt in range(max_retries + 1):
        try:
            response = send(req, timeout_seconds)
            status = getattr(response, "status", None)
            if status is None and hasattr(response, "getcode"):
                status = response.getcode()
            if status is None or 200 <= int(status) < 300:
                return
            if int(status) in {408, 429, 500, 502, 503, 504}:
                raise TransientAlertError(
                    event_type=event_type,
                    target=url,
                    reason=f"http status {int(status)}",
                )
            raise PermanentAlertError(
                event_type=event_type,
                target=url,
                reason=f"http status {int(status)}",
            )
        except AlertError as exc:
            if isinstance(exc, TransientAlertError) and attempt < max_retries:
                continue
            raise
        except Exception as exc:
            classified = _classify_alert_error(exc, event_type=event_type, target=url)
            if isinstance(classified, TransientAlertError) and attempt < max_retries:
                continue
            raise classified from exc


def _serialize_event_payload(
    *, severity: str, event_type: str, summary: str, detail: dict[str, Any]
) -> bytes:
    payload = [
        {
            "occurredAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "severity": severity,
            "eventType": event_type,
            "summary": summary,
            "detail": detail,
        }
    ]
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _classify_alert_error(
    exc: Exception, *, event_type: str, target: str
) -> AlertError:
    reason = str(exc).strip() or exc.__class__.__name__
    if isinstance(exc, error.HTTPError):
        if exc.code in {408, 429, 500, 502, 503, 504}:
            return TransientAlertError(
                event_type=event_type, target=target, reason=reason
            )
        return PermanentAlertError(event_type=event_type, target=target, reason=reason)

    if isinstance(exc, (TimeoutError, ConnectionError, error.URLError)):
        return TransientAlertError(event_type=event_type, target=target, reason=reason)

    lower_reason = reason.lower()
    transient_markers = (
        "timeout",
        "temporar",
        "throttl",
        "too many requests",
        "429",
        "500",
        "502",
        "503",
        "504",
        "connection",
        "unavailable",
        "try again",
    )
    if any(marker in lower_reason for marker in transient_markers):
        return TransientAlertError(event_type=event_type, target=target, reason=reason)

    return PermanentAlertError(event_type=event_type, target=target, reason=reason)


def _parse_retry_count(raw: str) -> int:
    try:
        retries = int(raw)
    except ValueError as exc:
        raise PermanentAlertError(
            event_type="CONFIG",
            target="ALERTING_MAX_RETRIES",
            reason="ALERTING_MAX_RETRIES must be an integer",
        ) from exc
    if retries < 0:
        raise PermanentAlertError(
            event_type="CONFIG",
            target="ALERTING_MAX_RETRIES",
            reason="ALERTING_MAX_RETRIES must be >= 0",
        )
    return retries


def _parse_timeout(raw: str) -> float:
    try:
        timeout = float(raw)
    except ValueError as exc:
        raise PermanentAlertError(
            event_type="CONFIG",
            target="ALERTING_HTTP_TIMEOUT_SECONDS",
            reason="ALERTING_HTTP_TIMEOUT_SECONDS must be a number",
        ) from exc
    if timeout <= 0:
        raise PermanentAlertError(
            event_type="CONFIG",
            target="ALERTING_HTTP_TIMEOUT_SECONDS",
            reason="ALERTING_HTTP_TIMEOUT_SECONDS must be > 0",
        )
    return timeout


def _default_sender(req: request.Request, timeout: float) -> Any:
    with request.urlopen(req, timeout=timeout) as response:
        return response


__all__ = [
    "APPROVAL_TIMEOUT",
    "EXECUTION_FAILED",
    "POSTMORTEM_FAILED",
    "PermanentAlertError",
    "SEVERITY_CRITICAL",
    "SEVERITY_ERROR",
    "SEVERITY_INFO",
    "SEVERITY_WARNING",
    "TRIAGE_READY",
    "TransientAlertError",
    "emit_alert",
]
