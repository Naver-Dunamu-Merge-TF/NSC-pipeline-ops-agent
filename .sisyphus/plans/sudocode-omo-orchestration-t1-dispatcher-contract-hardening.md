# T1. Dispatcher Contract Hardening

## Objective
Harden dispatcher execution and status transitions so no-op or partial runs cannot be misclassified as success.

## Scope
- In Scope: `scripts/sudocode_opencode_dispatcher.py` command normalization, success classification, state transition, run artifact persistence.
- Out of Scope: supervisor loop, monitoring layout, intervention commands.

## Dependencies
- depends_on: none
- unblocks: T2

## Task Dependency Graph
- upstream: none
- downstream: T2

## Parallel Execution Graph
- serial with: T2, T3, T6
- parallel eligible with: none

## Implementation Context
- Primary file: `scripts/sudocode_opencode_dispatcher.py`
- Artifacts: `.sudocode/logs/*.log`, `.sudocode/logs/*.json`

## Tasks
- Task 1: Command normalization and success/failure contract hardening.
  - Category: unspecified-low
  - Skills: `find-skills`

## TODO List
- [x] Confirm no-op command path cannot be marked successful.
- [x] Confirm deterministic status transition on both success and failure.
- [x] Confirm run artifacts are written for every execution.

## Work Plan
1. Normalize command input for slash/non-slash forms.
2. Enforce deterministic status contract (`open -> in_progress -> needs_review|open`).
3. Treat empty-output execution as failure.
4. Ensure logs/metadata are persisted under `.sudocode/logs/`.

## Acceptance Criteria (Executable)
- [x] Command: `python3 -m py_compile scripts/sudocode_opencode_dispatcher.py`
  - Assert: exit code is 0.
  - Evidence: terminal output.
- [x] Command: `python3 scripts/sudocode_opencode_dispatcher.py --help`
  - Assert: help shows `--command`, `--on-success`, `--on-failure`.
  - Evidence: help output.
- [x] Command: `python3 scripts/sudocode_opencode_dispatcher.py --issue-id i-rxxt --command /ulw-loop --dry-run`
  - Assert: selected command path is resolved and execution does not fail.
  - Evidence: JSON dry-run output.

## Evidence Paths
- `.sudocode/logs/*_*.log`
- `.sudocode/logs/*_*.json`

## ADR and PR Contract
- ADR trigger: if dispatcher contract changes status semantics or risk policy, create `docs/adr/NNNN-dispatcher-contract.md`.
- PR requirement: implementation PR must include issue id, validation evidence, and `Reviewed-by: Momus (Local)`.

## Momus Post-Review
- Verdict: [OKAY]
- Evidence: session `ses_383fd8cb9ffeTrMCOV5a4BX31r`
