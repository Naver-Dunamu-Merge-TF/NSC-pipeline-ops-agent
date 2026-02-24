from __future__ import annotations

import json
from urllib.error import HTTPError
from urllib.request import Request

import pytest

from tools.alerting import (
    APPROVAL_TIMEOUT,
    EXECUTION_FAILED,
    POSTMORTEM_FAILED,
    TRIAGE_READY,
    PermanentAlertError,
    TransientAlertError,
    emit_alert,
)


class _StubResponse:
    def __init__(self, status: int) -> None:
        self.status = status

    def getcode(self) -> int:
        return self.status


def test_event_type_constants_are_standardized() -> None:
    assert TRIAGE_READY == "TRIAGE_READY"
    assert APPROVAL_TIMEOUT == "APPROVAL_TIMEOUT"
    assert EXECUTION_FAILED == "EXECUTION_FAILED"
    assert POSTMORTEM_FAILED == "POSTMORTEM_FAILED"


def test_emit_alert_serializes_minimal_payload_and_sends_request() -> None:
    sent: list[tuple[Request, float]] = []

    def sender(request: Request, timeout: float) -> _StubResponse:
        sent.append((request, timeout))
        return _StubResponse(204)

    emit_alert(
        severity="ERROR",
        event_type=EXECUTION_FAILED,
        summary="execution failed for pipeline",
        detail={"pipeline": "nsc_gold", "run_id": "run-1"},
        environ={
            "LOG_ANALYTICS_DCR_ENDPOINT": "https://ingest.monitor.azure.com",
            "LOG_ANALYTICS_DCR_IMMUTABLE_ID": "dcr-abc123",
            "LOG_ANALYTICS_STREAM_NAME": "Custom-AiAgentEvents",
        },
        sender=sender,
    )

    assert len(sent) == 1
    request, timeout = sent[0]
    assert timeout == 5.0
    assert request.full_url == (
        "https://ingest.monitor.azure.com"
        "/dataCollectionRules/dcr-abc123/streams/Custom-AiAgentEvents"
        "?api-version=2023-01-01"
    )
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/json"

    payload = json.loads(request.data.decode("utf-8"))
    assert isinstance(payload, list)
    assert len(payload) == 1
    event = payload[0]
    assert event["severity"] == "ERROR"
    assert event["eventType"] == EXECUTION_FAILED
    assert event["summary"] == "execution failed for pipeline"
    assert event["detail"] == {"pipeline": "nsc_gold", "run_id": "run-1"}
    assert isinstance(event["occurredAt"], str)
    assert event["occurredAt"].endswith("Z")


def test_emit_alert_retries_when_error_is_transient() -> None:
    attempts = 0

    def sender(request: Request, timeout: float) -> _StubResponse:
        del request, timeout
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise HTTPError(
                url="https://ingest.monitor.azure.com",
                code=503,
                msg="service unavailable",
                hdrs=None,
                fp=None,
            )
        return _StubResponse(204)

    emit_alert(
        severity="WARNING",
        event_type=APPROVAL_TIMEOUT,
        summary="approval timed out",
        detail={"incident_id": "inc-1"},
        environ={
            "LOG_ANALYTICS_DCR_ENDPOINT": "https://ingest.monitor.azure.com",
            "LOG_ANALYTICS_DCR_IMMUTABLE_ID": "dcr-abc123",
            "LOG_ANALYTICS_STREAM_NAME": "Custom-AiAgentEvents",
        },
        sender=sender,
    )

    assert attempts == 3


def test_emit_alert_retries_when_transient_status_is_returned() -> None:
    attempts = 0

    def sender(request: Request, timeout: float) -> _StubResponse:
        del request, timeout
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return _StubResponse(503)
        return _StubResponse(204)

    emit_alert(
        severity="WARNING",
        event_type=APPROVAL_TIMEOUT,
        summary="approval timed out",
        detail={"incident_id": "inc-1"},
        environ={
            "LOG_ANALYTICS_DCR_ENDPOINT": "https://ingest.monitor.azure.com",
            "LOG_ANALYTICS_DCR_IMMUTABLE_ID": "dcr-abc123",
            "LOG_ANALYTICS_STREAM_NAME": "Custom-AiAgentEvents",
        },
        sender=sender,
    )

    assert attempts == 3


def test_emit_alert_raises_transient_error_after_retry_limit() -> None:
    attempts = 0

    def sender(request: Request, timeout: float) -> _StubResponse:
        del request, timeout
        nonlocal attempts
        attempts += 1
        raise HTTPError(
            url="https://ingest.monitor.azure.com",
            code=429,
            msg="too many requests",
            hdrs=None,
            fp=None,
        )

    with pytest.raises(TransientAlertError) as exc_info:
        emit_alert(
            severity="WARNING",
            event_type=APPROVAL_TIMEOUT,
            summary="approval timed out",
            detail={"incident_id": "inc-1"},
            environ={
                "LOG_ANALYTICS_DCR_ENDPOINT": "https://ingest.monitor.azure.com",
                "LOG_ANALYTICS_DCR_IMMUTABLE_ID": "dcr-abc123",
                "LOG_ANALYTICS_STREAM_NAME": "Custom-AiAgentEvents",
            },
            sender=sender,
        )

    assert attempts == 3
    assert "[ALERT][TRANSIENT]" in str(exc_info.value)


def test_emit_alert_raises_permanent_error_without_retry() -> None:
    attempts = 0

    def sender(request: Request, timeout: float) -> _StubResponse:
        del request, timeout
        nonlocal attempts
        attempts += 1
        raise HTTPError(
            url="https://ingest.monitor.azure.com",
            code=400,
            msg="bad request",
            hdrs=None,
            fp=None,
        )

    with pytest.raises(PermanentAlertError) as exc_info:
        emit_alert(
            severity="ERROR",
            event_type=EXECUTION_FAILED,
            summary="execution failed",
            detail={"pipeline": "nsc_gold"},
            environ={
                "LOG_ANALYTICS_DCR_ENDPOINT": "https://ingest.monitor.azure.com",
                "LOG_ANALYTICS_DCR_IMMUTABLE_ID": "dcr-abc123",
                "LOG_ANALYTICS_STREAM_NAME": "Custom-AiAgentEvents",
            },
            sender=sender,
        )

    assert attempts == 1
    assert "[ALERT][PERMANENT]" in str(exc_info.value)
