---
name: run-one
description: "Sudocode single-issue orchestrator skill. Use when the user runs `/run-one` (auto-select by runtime ordering) or `/run-one i-xxxx` (explicit issue ID)."
---

# run-one

Thin contract for the single-issue orchestrator.

This contract is **runtime-aligned as-is** with:
- `src/sudocode_orchestrator/runner.py`
- `src/sudocode_orchestrator/session_loop.py`
- `src/sudocode_orchestrator/claim.py`

Detailed loop mechanics follow those modules while preserving the state/event invariants below.

## Contract

1. Selection is deterministic by `(priority, ready_at, issue_id)`.
2. Runner does not enforce an explicit open-status gate; readiness filtering is owned by `get_ready_issues()`.
3. Claim starts the session by setting issue status to `in_progress` and emitting `SESSION_START` (`loop_snapshot.v1`).
4. Gate order is fixed: implementer -> spec reviewer -> quality reviewer.
5. Retry caps are fixed: spec retry cap 3, quality retry cap 2.
6. Verification requires fresh passing evidence (`exit_code == 0` and `produced_at >= code_changed_at`).
7. Success terminal (current runtime): set status to `closed`, then emit `SESSION_DONE`.
8. Failure semantics:
   - `VERIFY_FAILED`: emit event and return; no automatic reopen in `session_loop`.
   - `SESSION_ERROR`: emitted by `session_loop`; runner catches and reopens issue to `open`.
9. Overflow semantics: create `[FIX]` issue, link with relation `related`, set original issue to `closed`, emit `OVERFLOW_FIX_CREATED`.

## Policy Delta Note

- Policy target (`ORCHESTRATION_OPENCODE_NATIVE.md`) expects `open -> in_progress -> needs_review -> closed`.
- Current runtime here still performs direct `in_progress -> closed` on success and overflow.
- This file intentionally documents runtime behavior as-is; treat `needs_review` as a target-mode delta, not current runtime behavior.

Terminology guardrail: `needs_review` (issue status) and `needs-review` (PR label) are distinct.
