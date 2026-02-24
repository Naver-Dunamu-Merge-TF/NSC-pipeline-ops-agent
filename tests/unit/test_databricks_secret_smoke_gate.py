from __future__ import annotations

from tests.smoke.test_databricks_secret_smoke import _smoke_skip_reason


def test_smoke_skip_reason_allows_databricks_runtime_with_scope() -> None:
    reason = _smoke_skip_reason(
        {
            "DATABRICKS_RUNTIME_VERSION": "14.3",
            "DATABRICKS_SECRET_SCOPE": "kv-dev",
        }
    )

    assert reason is None


def test_smoke_skip_reason_requires_scope() -> None:
    reason = _smoke_skip_reason({"DATABRICKS_RUNTIME_VERSION": "14.3"})

    assert (
        reason == "Set DATABRICKS_SECRET_SCOPE or KEY_VAULT_SECRET_SCOPE for smoke test"
    )


def test_smoke_skip_reason_respects_explicit_opt_in_outside_databricks() -> None:
    reason = _smoke_skip_reason(
        {
            "RUN_DATABRICKS_SECRET_SMOKE": "1",
            "DATABRICKS_SECRET_SCOPE": "kv-dev",
        }
    )

    assert reason is None


def test_smoke_skip_reason_rejects_whitespace_only_scope() -> None:
    reason = _smoke_skip_reason(
        {
            "DATABRICKS_RUNTIME_VERSION": "14.3",
            "DATABRICKS_SECRET_SCOPE": "   ",
        }
    )

    assert (
        reason == "Set DATABRICKS_SECRET_SCOPE or KEY_VAULT_SECRET_SCOPE for smoke test"
    )


def test_smoke_skip_reason_normalizes_scope_whitespace() -> None:
    reason = _smoke_skip_reason(
        {
            "DATABRICKS_RUNTIME_VERSION": "14.3",
            "DATABRICKS_SECRET_SCOPE": "  kv-dev  ",
        }
    )

    assert reason is None
