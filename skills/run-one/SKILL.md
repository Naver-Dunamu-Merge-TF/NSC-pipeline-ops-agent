---
name: run-one
description: "Sudocode single-issue orchestrator trigger skill. Use when the user runs `/run-one` (auto-select the lowest-numbered ready issue) or `/run-one i-xxxx` (explicit issue ID). Handles issue selection, precondition checks, and SESSION_START recording. Internal orchestrator loops (spec review, quality review, verify, PR creation) are handled by the downstream protocol."
---

# run-one

Entry protocol for the Sudocode orchestrator. This skill only fires the ignition.

## Usage

| Command | Behavior |
|---------|----------|
| `/run-one` | Auto-select the ready issue with the lowest DEV-NNN number |
| `/run-one i-xxxx` | Run directly with the specified issue ID |

## Step 1 — Issue Selection

**Auto mode** (`/run-one`):
1. Query ready issues via `sudocode-mcp` → `ready`
2. Extract `"task:DEV-NNN"` from each issue's `tags`, sort by NNN ascending
3. Pick the lowest number (issues without a `task:` tag go last)

**Explicit mode** (`/run-one i-xxxx`): Use the given ID directly, skip the query.

## Step 2 — Precondition Check

Call `show_issue(issue_id)` and verify:
- `status == "open"` (in_progress/closed → print reason and exit)
- feedback contains SESSION_START but no SESSION_DONE/SESSION_ERROR → another session is active, print reason and exit

## Step 3 — Session Start

1. `upsert_issue(status="in_progress")`
2. `add_feedback` — record SESSION_START snapshot:

```json
{
  "schema_version": "loop_snapshot.v1",
  "event_type": "SESSION_START",
  "issue_id": "<issue_id>",
  "task_id": "<DEV-NNN>",
  "session_id": "<uuid4>",
  "orchestrator_id": "run-one-skill",
  "timestamp": "<ISO8601>"
}
```

Skill exits after SESSION_START is recorded. The orchestrator protocol takes over from here.
