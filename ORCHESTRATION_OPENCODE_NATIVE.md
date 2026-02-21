# OpenCode Native Orchestration Policy (Minimal)

This document aligns OpenCode-native runtime policy with `ORCHESTRATION.md`.

## Required Issue Lifecycle

- All issues must follow `open -> in_progress -> needs_review -> closed`.
- Direct `in_progress -> closed` transitions are forbidden.
- Session success and overflow both stop at `needs_review`.
- `closed` is allowed only after merge-confirmed close handling.

## Terminology Guardrail

- `needs_review` is a Sudocode issue status value.
- `needs-review` is a GitHub PR label used for manual-review fallback.
- They are related signals but not interchangeable fields.

## Fallback Rule

- If auto-merge conditions fail, disable auto-merge and attach PR label `needs-review`.
- This fallback does not close issues; issue status remains `needs_review` until merge-confirmed close.
