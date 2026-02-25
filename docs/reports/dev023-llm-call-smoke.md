# DEV-023-INFRA-SMOKE (i-14fx)

## Scope

- DoD target: run one real LLM call smoke in dev context.
- Setup path used in this run: jumpbox (`jump-aks-20260224-2dt026`) private-network secret fetch + local env variable injection.

## Real LLM Smoke (Jumpbox Private Path)

- Log path: `.agents/logs/verification/20260225T084043Z_i-14fx_dev023_llm_smoke/00_jumpbox_real_llm_smoke.log`
- Execution time (UTC): `2026-02-25T08:40:43Z` ~ `2026-02-25T08:41:17Z`
- Command summary: `az vm run-command invoke` on `jump-aks-20260224-2dt026`, managed identity login, secret fetch from `nsc-kv-dev`, one Azure OpenAI chat completion call against host `nsc-aoai-dev.openai.azure.com` with deployment value loaded from Key Vault at runtime (redacted in evidence).
- Result summary: `pass` (`http_status=200`, assistant reply `smoke-ok`, no API key plaintext in logs).

## Changed-Scope Re-Verification

- Log path: `.agents/logs/verification/20260225T084043Z_i-14fx_dev023_llm_smoke/01_pytest_llm_client.log`
- Execution time (UTC): `2026-02-25T08:41:17Z` ~ `2026-02-25T08:41:17Z`
- Command: `pytest tests/unit/test_llm_client.py -q`
- Result summary: `exit_code=0`

## Verdict

- DoD 1 (`dev 환경 실 LLM 1회 호출`): **satisfied**.
- DoD 2 (`대체 검증 증적 포맷`): **conditionally satisfied** for the final pass (fallback execution is N/A in this run; required evidence format is still present with sanitized command template, UTC timestamps, exit code, and result summary).
