from __future__ import annotations

from tests.smoke.test_alerting_smoke import _smoke_skip_reason


def test_smoke_skip_reason_requires_explicit_opt_in() -> None:
    reason = _smoke_skip_reason({})

    assert reason == "Set RUN_ALERTING_SMOKE=1 to run alerting smoke test"


def test_smoke_skip_reason_accepts_explicit_opt_in() -> None:
    reason = _smoke_skip_reason({"RUN_ALERTING_SMOKE": "1"})

    assert reason is None
