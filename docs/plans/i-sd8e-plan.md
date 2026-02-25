# Plan for i-sd8e: ADR-260225-1356

## Task 1: Update `tools/llm_client.py` and `tests/unit/test_llm_client.py`
Add explicit logging for "logical invocation" and "HTTP attempt" in `invoke_llm`.
- Add `import logging` and `logger = logging.getLogger(__name__)`.
- In `invoke_llm`, log an `INFO` message for the logical invocation start: `logger.info("Starting LLM logical invocation")`
- In the retry loop, log an `INFO` message for each HTTP attempt: `logger.info("Starting LLM HTTP attempt %d", attempt + 1)`
- Add a test or update existing tests in `test_llm_client.py` to assert that these logs are emitted (e.g. using `caplog`).
- Ensure all tests pass.

## Task 2: Update documentation specifications
Update `.specs/ai_agent_spec.md` and `.specs/runtime_config.md` to clarify the cap criteria and observation criteria.
- In `.specs/ai_agent_spec.md`, clarify that `LLM_DAILY_CAP` applies to "logical invocations" (논리 호출) and that operational monitoring should track both logical invocations and HTTP attempts (재시도 포함) separately using the added logs.
- In `.specs/runtime_config.md`, add a similar note explaining that `LLM_DAILY_CAP` is per logical invocation, and actual HTTP requests might be higher due to retries.

## Context
Background: ADR-260225-1356 separated the daily cap count from actual HTTP attempts. The daily cap applies per logical invocation.
DoD:
- Implementation gate: Code/config shows LLM_DAILY_CAP evaluated per logical invocation and HTTP attempts tracked separately (via logs).
- Doc gate: Affected `.specs/ai_agent_spec.md` and `.specs/runtime_config.md` reflect the cap criteria and observation criteria.
- ADR Re-evaluation gate: Operational monitoring allows judging if the cap counting unit needs to be changed when retry frequency spikes (via separate logs).