from __future__ import annotations

import os
import re
from typing import Mapping, Protocol


class SecretBackend(Protocol):
    provider: str

    def get(self, key: str) -> str: ...


class SecretError(RuntimeError):
    def __init__(
        self, *, classification: str, key: str, provider: str, reason: str
    ) -> None:
        self.classification = classification
        self.key = key
        self.provider = provider
        self.reason = reason
        super().__init__(
            f"[SECRET][{classification}] provider={provider} key={key} reason={reason}"
        )


class TransientSecretError(SecretError):
    def __init__(self, *, key: str, provider: str, reason: str) -> None:
        super().__init__(
            classification="TRANSIENT",
            key=key,
            provider=provider,
            reason=reason,
        )


class PermanentSecretError(SecretError):
    def __init__(self, *, key: str, provider: str, reason: str) -> None:
        super().__init__(
            classification="PERMANENT",
            key=key,
            provider=provider,
            reason=reason,
        )


class EnvSecretsBackend:
    provider = "env"

    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        self._environ = environ if environ is not None else os.environ

    def get(self, key: str) -> str:
        env_key = _key_to_env_name(key)
        value = self._environ.get(env_key, "").strip()
        if not value:
            raise KeyError(env_key)
        return value


class DatabricksSecretBackend:
    provider = "databricks"

    def __init__(self, *, scope: str, dbutils: object | None = None) -> None:
        self.scope = scope
        self._dbutils = dbutils

    def get(self, key: str) -> str:
        dbutils = self._dbutils if self._dbutils is not None else _resolve_dbutils()
        self._dbutils = dbutils
        value = dbutils.secrets.get(scope=self.scope, key=key)
        if not isinstance(value, str) or not value.strip():
            raise KeyError(key)
        return value


def get_secret(
    key: str,
    *,
    backend: SecretBackend | None = None,
    environ: Mapping[str, str] | None = None,
) -> str:
    key_name = key.strip()
    if not key_name:
        raise PermanentSecretError(
            key=key,
            provider="secrets",
            reason="empty key is not allowed",
        )

    if backend is not None:
        return _get_from_backend(backend, key_name)

    env = environ if environ is not None else os.environ
    env_backend = EnvSecretsBackend(environ=env)
    try:
        return env_backend.get(key_name)
    except KeyError:
        pass

    scope = (
        env.get("DATABRICKS_SECRET_SCOPE", "").strip()
        or env.get("KEY_VAULT_SECRET_SCOPE", "").strip()
    )
    if not scope:
        raise PermanentSecretError(
            key=key_name,
            provider="secrets",
            reason=(
                "missing env stub and no DATABRICKS_SECRET_SCOPE/KEY_VAULT_SECRET_SCOPE"
            ),
        )
    return _get_from_backend(DatabricksSecretBackend(scope=scope), key_name)


def _get_from_backend(backend: SecretBackend, key: str) -> str:
    provider = getattr(backend, "provider", backend.__class__.__name__)
    try:
        return backend.get(key)
    except SecretError:
        raise
    except Exception as exc:
        raise _classify_secret_error(exc, key=key, provider=provider) from exc


def _classify_secret_error(error: Exception, *, key: str, provider: str) -> SecretError:
    reason = str(error).strip() or error.__class__.__name__
    lower_reason = reason.lower()
    transient_markers = (
        "timeout",
        "temporar",
        "throttl",
        "too many requests",
        "429",
        "502",
        "503",
        "504",
        "connection",
        "unavailable",
        "try again",
    )
    if isinstance(error, (TimeoutError, ConnectionError)) or any(
        marker in lower_reason for marker in transient_markers
    ):
        return TransientSecretError(key=key, provider=provider, reason=reason)
    return PermanentSecretError(key=key, provider=provider, reason=reason)


def _key_to_env_name(key: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", key).strip("_").upper()
    return f"SECRET_{normalized}"


def _resolve_dbutils() -> object:
    try:
        from pyspark.dbutils import DBUtils
        from pyspark.sql import SparkSession
    except ModuleNotFoundError as exc:
        raise RuntimeError("pyspark is not available") from exc

    spark = SparkSession.getActiveSession() or SparkSession.builder.getOrCreate()
    return DBUtils(spark)


__all__ = [
    "DatabricksSecretBackend",
    "EnvSecretsBackend",
    "PermanentSecretError",
    "SecretError",
    "TransientSecretError",
    "get_secret",
]
