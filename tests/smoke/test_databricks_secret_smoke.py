from __future__ import annotations

import os
from typing import Mapping

import pytest

from utils.secrets import DatabricksSecretBackend, get_secret


def _smoke_skip_reason(environ: Mapping[str, str]) -> str | None:
    scope = (
        environ.get("DATABRICKS_SECRET_SCOPE", "").strip()
        or environ.get("KEY_VAULT_SECRET_SCOPE", "").strip()
    )
    if not scope:
        return "Set DATABRICKS_SECRET_SCOPE or KEY_VAULT_SECRET_SCOPE for smoke test"

    run_smoke = environ.get("RUN_DATABRICKS_SECRET_SMOKE", "").strip()
    if run_smoke == "1":
        return None

    if environ.get("DATABRICKS_RUNTIME_VERSION", "").strip():
        return None

    return "Set RUN_DATABRICKS_SECRET_SMOKE=1 or run on Databricks runtime"


def test_dev_databricks_reads_key_vault_backed_secret_smoke() -> None:
    skip_reason = _smoke_skip_reason(os.environ)
    if skip_reason:
        pytest.skip(skip_reason)

    scope = (
        os.getenv("DATABRICKS_SECRET_SCOPE", "").strip()
        or os.getenv("KEY_VAULT_SECRET_SCOPE", "").strip()
    )
    assert scope

    key = os.getenv("DATABRICKS_SMOKE_SECRET_KEY", "azure-openai-endpoint")

    value = get_secret(key, backend=DatabricksSecretBackend(scope=scope))

    assert isinstance(value, str)
    assert value.strip()
