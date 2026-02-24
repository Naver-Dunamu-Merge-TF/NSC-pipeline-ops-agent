from __future__ import annotations

import pytest

from utils.secrets import PermanentSecretError, TransientSecretError, get_secret


class _StubBackend:
    def __init__(
        self, *, provider: str, value: str | None = None, error: Exception | None = None
    ) -> None:
        self.provider = provider
        self._value = value
        self._error = error

    def get(self, key: str) -> str:
        if self._error is not None:
            raise self._error
        if self._value is None:
            raise KeyError(key)
        return self._value


def test_get_secret_reads_env_stub_with_keyvault_style_key() -> None:
    secret = get_secret(
        "azure-openai-api-key",
        environ={"SECRET_AZURE_OPENAI_API_KEY": "env-secret"},
    )

    assert secret == "env-secret"


def test_get_secret_supports_backend_test_double() -> None:
    backend = _StubBackend(provider="test-double", value="backend-secret")

    secret = get_secret("databricks-agent-token", backend=backend)

    assert secret == "backend-secret"


def test_get_secret_raises_permanent_error_with_message_contract() -> None:
    backend = _StubBackend(provider="test-double", error=KeyError("missing"))

    with pytest.raises(PermanentSecretError) as exc_info:
        get_secret("azure-openai-api-key", backend=backend)

    message = str(exc_info.value)
    assert message.startswith("[SECRET][PERMANENT]")
    assert "provider=test-double" in message
    assert "key=azure-openai-api-key" in message
    assert "reason=" in message


def test_get_secret_raises_transient_error_with_message_contract() -> None:
    backend = _StubBackend(provider="test-double", error=TimeoutError("timed out"))

    with pytest.raises(TransientSecretError) as exc_info:
        get_secret("azure-openai-endpoint", backend=backend)

    message = str(exc_info.value)
    assert message.startswith("[SECRET][TRANSIENT]")
    assert "provider=test-double" in message
    assert "key=azure-openai-endpoint" in message
    assert "reason=timed out" in message
