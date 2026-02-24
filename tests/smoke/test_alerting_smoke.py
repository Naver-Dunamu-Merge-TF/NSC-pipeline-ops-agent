from __future__ import annotations

import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import Queue
from threading import Thread
from typing import Mapping

import json

import pytest

from tools.alerting import TRIAGE_READY, emit_alert


def _smoke_skip_reason(environ: Mapping[str, str]) -> str | None:
    run_smoke = environ.get("RUN_ALERTING_SMOKE", "").strip()
    if run_smoke == "1":
        return None
    return "Set RUN_ALERTING_SMOKE=1 to run alerting smoke test"


def test_dev_alerting_test_event_smoke() -> None:
    skip_reason = _smoke_skip_reason(os.environ)
    if skip_reason:
        pytest.skip(skip_reason)

    received: Queue[tuple[str, str, str, bytes]] = Queue(maxsize=1)

    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            content_length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(content_length)
            received.put(
                (
                    self.command,
                    self.path,
                    self.headers.get("Content-Type", ""),
                    body,
                )
            )
            self.send_response(204)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        emit_alert(
            severity="INFO",
            event_type=TRIAGE_READY,
            summary="dev smoke alert",
            detail={"env": "dev", "smoke": True},
            environ={
                "LOG_ANALYTICS_DCR_ENDPOINT": f"http://127.0.0.1:{server.server_port}",
                "LOG_ANALYTICS_DCR_IMMUTABLE_ID": "dcr-smoke",
                "LOG_ANALYTICS_STREAM_NAME": "Custom-AiAgentEvents",
            },
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    method, path, content_type, body = received.get(timeout=3)

    assert method == "POST"
    assert (
        path
        == "/dataCollectionRules/dcr-smoke/streams/Custom-AiAgentEvents?api-version=2023-01-01"
    )
    assert content_type == "application/json"
    payload = json.loads(body.decode("utf-8"))
    assert payload[0]["eventType"] == TRIAGE_READY
