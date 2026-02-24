from __future__ import annotations

from tests.smoke.test_incident_fingerprint_smoke import _smoke_skip_reason


def test_smoke_skip_reason_allows_default_dev_fixture_with_explicit_opt_in() -> None:
    reason = _smoke_skip_reason(
        {
            "RUN_DEV012_FINGERPRINT_SMOKE": "1",
            "DEV012_SMOKE_ENV": "dev",
        }
    )

    assert reason is None


def test_smoke_skip_reason_requires_explicit_opt_in() -> None:
    reason = _smoke_skip_reason({"DEV012_SMOKE_ENV": "dev"})

    assert reason == "Set RUN_DEV012_FINGERPRINT_SMOKE=1 to run fingerprint smoke test"


def test_smoke_skip_reason_rejects_unknown_environment() -> None:
    reason = _smoke_skip_reason(
        {
            "RUN_DEV012_FINGERPRINT_SMOKE": "1",
            "DEV012_SMOKE_ENV": "prod",
        }
    )

    assert reason == "DEV012_SMOKE_ENV must be one of: dev, staging"
