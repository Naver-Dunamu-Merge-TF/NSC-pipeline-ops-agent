---
name: run-one
description: "Use when the user runs `/run-one` to execute exactly one Sudocode issue from `open` to `needs_review`."
---

# run-one

Role: You are the execution agent for exactly one Sudocode issue.
Purpose: Select one ready issue and drive it from `open` to `needs_review` with scoped implementation and review/fix loops.

## Ambiguity Handling

- During implementation, if a decision is needed or requirements are ambiguous, triage by severity:
  - Definition: a `decision-bearing implementation change` is any implementation-time choice not explicitly fixed by existing spec/policy, including low-impact defaults and user-directed choices after high-impact escalation.
  - High-impact or irreversible (for example: scope change, security/compliance risk, data-loss risk, policy conflict): pause and call the user for direction before continuing.
  - Low-impact and reversible: proceed with the best default, then record the decision and rationale in an ADR under `docs/adr/`, and create a follow-up issue linked to the current issue as a `decision-bearing implementation change`.

## State

`open -> in_progress -> needs_review`

## Task Order

1. Issue selection:
   - Run `sudocode-mcp_ready`.
   - From `ready.issues`, parse title prefix/number (`ADR-001`, `DEV-001`).
   - Pick by prefix priority first: `ADR` before `DEV`.
   - Within the same prefix, pick the smallest number.
2. Run `sudocode-mcp_show_issue` for the selected issue and use the task context (`id`, `title`, `description`) internally for implementation.
3. Set selected issue status to `in_progress`.
4. Create a dedicated git worktree for the selected issue, then do all following work in that worktree.
5. Implement the issue scope.
6. Run review/self-fix loop:
   - Review changes.
   - Apply fixes.
   - Re-run verification for changed scope.
   - Repeat until blocking findings are cleared.
7. Before `needs_review`, if any `decision-bearing implementation change` occurred, confirm ADR and linked follow-up issue were both created.
8. On success, set issue status to `needs_review`.
   - If the selected issue is `ADR-###`, set the linked ADR document `Status` to `Confirmed`.
9. Self-retrospective: verify each Task Order step was executed as written. If any was skipped or deviated from, note it to the user.

## Non-Negotiable Rules

- One run handles one issue only.
- Keep changes strictly inside the selected issue scope.
- ALL IMPLEMENTATION, REVIEW, AND FIXES MUST BE EXECUTED THROUGH SUBAGENTS.
- `needs_review` is an issue status (different from PR label `needs-review`).
- All user-facing messages must be written in Korean.
