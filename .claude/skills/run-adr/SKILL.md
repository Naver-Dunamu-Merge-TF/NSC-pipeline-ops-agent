---
name: run-adr
description: "Use when the user runs `/run-adr` to execute exactly one ADR-YYYYMMDD-HHMM issue from `open` to `needs_review`."
---

# run-adr

Role: You are the execution agent for exactly one ADR follow-up issue.
Purpose: Select one ready ADR-YYYYMMDD-HHMM issue, validate the architectural decision, then drive implementation from `open` to `needs_review`.

## State

`open -> in_progress -> needs_review`

## Task Order

1. Issue selection:
   - Run `sudocode-mcp_ready`.
   - From `ready.issues`, filter to `ADR-YYYYMMDD-HHMM` prefix only.
   - Pick the issue with the earliest timestamp (oldest decision first).
2. Run `sudocode-mcp_show_issue` for the selected issue and use the task context (`id`, `title`, `description`) internally.
3. Set selected issue status to `in_progress`.
4. ADR validity review (before any implementation):
   - Locate the linked ADR document under `docs/adr/` using the timestamp from the issue title.
   - Dispatch two subagents independently, each with a fresh context:
     - **Subagent A — External alignment**: Evaluate this decision against external project artifacts (specs, existing code, related configuration).
     - **Subagent B — Internal soundness**: Evaluate whether the ADR's own reasoning is complete (alternatives considered, rejection rationale adequate, no conflict with other recorded decisions).
   - Collect both verdicts. If either returns **INVALID**: set issue status to `closed`, report findings to the user, and stop. Do not proceed to implementation.
   - If both return **VALID**: continue to next step.
5. Create a dedicated git worktree for the selected issue, then do all following work in that worktree.
6. Implement the issue scope.
7. Run review/self-fix loop:
   - Review changes.
   - Apply fixes.
   - Re-run verification for changed scope.
   - Repeat until blocking findings are cleared.
8. Set issue status to `needs_review`.
9. Set the linked ADR document `Status` to `Confirmed`.
10. Self-retrospective: verify each Task Order step was executed as written. If any was skipped or deviated from, flag it internally before proceeding to Step 11.
11. Report to the user in Korean: describe in detail what was implemented, why each change was made, what decisions were made during implementation, and any deviations flagged in Step 10.

## Non-Negotiable Rules

- One run handles one issue only.
- Keep changes strictly inside the selected issue scope.
- ADR validity review (Step 4) and code review/fix loop (Step 7) must be executed through subagents.
- ADR validity review (Step 4) must complete before any worktree or implementation work begins.
- If validity review returns INVALID, execution stops immediately — no worktree, no code changes.
- `needs_review` is an issue status (different from PR label `needs-review`).
- All user-facing messages must be written in Korean.
