from __future__ import annotations

try:
    from orchestrator.utils.secrets import (
        DatabricksSecretBackend,
        EnvSecretsBackend,
        PermanentSecretError,
        SecretError,
        TransientSecretError,
        get_secret,
    )
except ModuleNotFoundError as exc:
    if exc.name is None or exc.name.split(".", 1)[0] != "orchestrator":
        raise
    from src.orchestrator.utils.secrets import (
        DatabricksSecretBackend,
        EnvSecretsBackend,
        PermanentSecretError,
        SecretError,
        TransientSecretError,
        get_secret,
    )

__all__ = [
    "DatabricksSecretBackend",
    "EnvSecretsBackend",
    "PermanentSecretError",
    "SecretError",
    "TransientSecretError",
    "get_secret",
]
