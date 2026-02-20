# AGENTS.md

## Project Overview
Spec-driven delivery workflow: humans define intent and approvals, while agents execute implementation and verification under Sudocode orchestration.

## File Structure
- `.specs/` - Intent SSOT (domain rules, contracts, design rationale). Human-authored.
- `.roadmap/` - Gate -> Epic -> Task execution plan and dependencies.
- `.sudocode/` - Sudocode-managed state (`issues/`, `specs/`) used as operational SSOT.
- `docs/adr/` - Architecture Decision Records for unresolved or design-level decisions.
- `docs/generated/` - Auto-generated fact docs from code. Read-only.
- `docs/reports/` - Weekly operational reports and progress metrics.
- `docs/upstream/` - Upstream reference docs. Read-only mirror/reference.
- `scripts/` - Automation scripts (reporting, checks, utilities).
- `skills/` - Prompt templates and operational instructions for agent tasks.
- `.github/workflows/` - CI/CD workflows (test, security, drift, automerge, reports).

## Agent Behavior Rules

### Non-negotiable
- Never use `--no-verify`.
- Never commit `.env` files.
- Never commit real secrets or credentials.
- Use `PLACEHOLDER` values in docs/examples/tests when secret-like values are needed.
- Run test commands in the project virtual environment (`.venv`) by default.
- Before creating a PR, run local review agent Momus and include `Reviewed-by: Momus (Local)` in PR body.
- If the same test fails 5 consecutive attempts, stop retry loop and record unresolved items.

### Scope and execution
- Keep changes task-scoped: `1 Task = 1 Issue`.
- Do not expand scope beyond the active Sudocode issue.
- Prefer minimal and surgical changes over speculative abstractions.
- If `.specs/` or `docs/adr/` is changed, require manual approval and do not rely on auto-merge.

### Sudocode orchestration rules
- Treat Sudocode as execution-state SSOT (`.sudocode/issues/`, `.sudocode/specs/`); GitHub labels are mirrors for CI/rules.
- Do not use GitHub Issues as primary execution tracker for this workflow.
- Keep Roadmap -> Sudocode Issue DAG sync active; rely on Sudocode readiness/blocked state to decide execution order.
- Start implementation from the active Sudocode issue context and keep status/checklist aligned through Sudocode MCP.
- Ensure PR body includes the solved Sudocode Issue ID, document impact, unresolved points, and local review signature.
- Respect `approval:auto` safeguards: any `.specs/` or `docs/adr/` change forces manual review path.

### Decision discipline (CLAUDE.md-aligned, expanded)

Tradeoff: these guidelines bias toward caution over speed. For trivial tasks, use judgment.

#### 1. Think before coding

Do not assume. Do not hide confusion. Surface tradeoffs.

Before implementing:
- State assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them. Do not pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what is confusing and ask.

#### 2. Simplicity first

Write the minimum code that solves the problem. Nothing speculative.

- No features beyond what was asked.
- No abstractions for single-use code.
- No flexibility/configurability that was not requested.
- No error handling for impossible scenarios.
- If 200 lines can be 50, rewrite it.

Ask yourself: "Would a senior engineer call this overcomplicated?" If yes, simplify.

#### 3. Surgical changes

Touch only what you must. Clean up only your own mess.

When editing existing code:
- Do not improve adjacent code/comments/formatting unless required by the task.
- Do not refactor unrelated areas.
- Match existing style, even if you would choose differently.
- If you notice unrelated dead code, note it. Do not delete it unless asked.

When your own changes create orphans:
- Remove imports/variables/functions made unused by your change.
- Do not remove pre-existing dead code unless explicitly asked.

Every changed line should trace directly to the user request.

#### 4. Goal-driven execution

Define success criteria, then loop until verified.

- "Add validation" -> write tests for invalid inputs, then make them pass.
- "Fix the bug" -> write a reproducing test, then make it pass.
- "Refactor X" -> verify tests pass before and after.

For multi-step tasks, use a brief verifiable plan:

```text
1. [Step] -> verify: [check]
2. [Step] -> verify: [check]
3. [Step] -> verify: [check]
```

Strong criteria reduce ambiguity. Weak criteria ("make it work") create rework.

These guidelines are working if: fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

## Review guidelines
- Spec alignment: implementation matches `.specs/` intent and constraints.
- Convention alignment: naming, structure, and style follow existing repository patterns.
- Security hygiene: no secrets, tokens, keys, or private credentials are introduced.
- PR body completeness:
  - Includes solved Sudocode Issue ID.
  - Includes document impact analysis (`.specs/`, `docs/adr/`, related docs).
  - Includes unresolved/ambiguous points and ADR references when needed.
  - Includes `Reviewed-by: Momus (Local)` signature.
- Approval policy:
  - `approval:auto` is allowed only when CI/rules pass and no protected-risk file changes are present.
  - Any `.specs/` or `docs/adr/` change is manually reviewed.

## Verification Ladder

| Level | When | Command | Pass Criteria |
|---|---|---|---|
| L0 | Per edit (local) | `.venv/bin/python -m py_compile <target>` | No syntax errors |
| L1 | Pre-commit (local) | `.venv/bin/python -m pytest tests/unit/ -x` | Unit tests pass |
| L2 | Pre-PR / CI | `.venv/bin/python -m pytest tests/unit/ tests/integration/ --cov=src --cov-fail-under=80` | Tests pass and coverage >= 80% |
| L3 | Pre-merge / CI gate | Databricks Dev E2E suite | End-to-end and idempotency verified |

## Coverage Strategy Placement
- Put domain-level test intent and threshold rationale in `.specs/` (and `docs/adr/` when the threshold/policy itself is a design decision).
- Put task-level verification targets in `.roadmap/` (`verify:L2`/`verify:L3` and DoD checklists).
- Put agent execution behavior (what to run locally and when) in this `AGENTS.md` Verification Ladder.
- Put hard merge gates in `.github/workflows/` (CI enforcement such as `--cov-fail-under=80`).
- Keep numbers synchronized: when coverage threshold changes, update `.specs/`, `AGENTS.md`, and CI together.

## PR Body Minimum Contract
- `## Change Summary`
- `## Document Impact`
- `## Unresolved / Ambiguities`
- `## Session Notes` (loop count, failures, intervention if any)
- `## Local Review Signature` with `Reviewed-by: Momus (Local)`

## Operational Notes (Spec-based recommendations)
- Sudocode issue state is SSOT for execution tracking; GitHub labels mirror operational metadata only.
- Keep intent/fact separation strict:
  - Intent in `.specs/`
  - Fact in `docs/generated/`
- If implementation exposes a design ambiguity:
  - Open/extend ADR when architectural decision is needed.
  - Add a spec-update task when domain intent must change.
- Keep lifecycle alignment explicit: Roadmap updates should flow to Sudocode issues, and merged PRs should reflect closed Sudocode issue states.
