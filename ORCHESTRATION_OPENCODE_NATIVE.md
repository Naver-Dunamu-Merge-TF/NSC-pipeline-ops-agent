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

## Split-Brain Avoidance

- Merge-close daemon is the primary close authority.
- Runtime unit is user-scope systemd: `ops/systemd/sudocode-merge-close-daemon.service` -> `~/.config/systemd/user/sudocode-merge-close-daemon.service`.
- Unit env path is `~/.config/sudocode/sudocode-merge-close-daemon.env`.
- GitHub workflow handling merged PR events stays audit-only dry-run (`.github/workflows/sudocode-close-on-merge.yml` uses `--dry-run`).
- Never allow daemon and CI workflow to both mutate issue close state in the same window.
