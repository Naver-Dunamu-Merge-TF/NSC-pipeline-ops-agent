# Sudocode Orchestrator Runbook

## Purpose

This runbook explains how to operate the Sudocode orchestrator components in this repository.
It covers local validation, runtime wiring, operational checks, and incident handling.

## Scope and Current Runtime Shape

- Orchestrator components live in `src/sudocode_orchestrator/`.
- `python -m sudocode_orchestrator.runner --dry-run` is a local simulation entrypoint.
- There is no packaged long-running orchestrator service command yet in `scripts/`.
- Merge-confirmed close handling is operated by a separate user-scope systemd unit: `ops/systemd/sudocode-merge-close-daemon.service`.
- Worker parallelism default is `4` in `WorkerPoolDispatcher`.

Relevant modules:

- `src/sudocode_orchestrator/runner.py`
- `src/sudocode_orchestrator/session_loop.py`
- `src/sudocode_orchestrator/gateway.py`
- `src/sudocode_orchestrator/snapshot.py`

## Preconditions

- Python environment is available (`python`).
- Repository dependencies are installed for tests.
- Sudocode MCP callables are available to the process host.
- Prompt template exists at `docs/prompts/prompt_template.md`.

## Quick Health Check (Dry Run)

Run:

```bash
PYTHONPATH=src .venv/bin/python -m sudocode_orchestrator.runner --dry-run
```

Expected result:

- JSON output with `"processed_issue": "i-dry1"`
- `"last_event_type": "SESSION_DONE"`
- Non-zero `snapshot_count`

Example:

```json
{
  "last_event_type": "SESSION_DONE",
  "processed_issue": "i-dry1",
  "snapshot_count": 5,
  "status_updates": [["i-dry1", "in_progress"], ["i-dry1", "in_progress"], ["i-dry1", "needs_review"]]
}
```

Note: seeing two `in_progress` updates is expected in the current flow (claim step and session loop both set status).

## Runtime Wiring

Use `SudocodeGateway` to wrap MCP functions and `IssueSessionRunner` to execute issue sessions.

### Minimal Serial Poll Loop

```python
from __future__ import annotations

import time
from pathlib import Path

from sudocode_orchestrator.agent_roles import RoleAgentAdapter
from sudocode_orchestrator.gateway import SudocodeGateway
from sudocode_orchestrator.runner import IssueSessionRunner
from sudocode_orchestrator.session_loop import SingleSessionOrchestrator


def build_gateway(mcp_client) -> SudocodeGateway:
    return SudocodeGateway(
        mcp_ready=mcp_client.ready,
        mcp_show_issue=mcp_client.show_issue,
        mcp_upsert_issue=mcp_client.upsert_issue,
        mcp_add_feedback=mcp_client.add_feedback,
        mcp_link=mcp_client.link,
    )


def main(mcp_client, role_transport) -> None:
    template = Path("docs/prompts/prompt_template.md").read_text(encoding="utf-8")
    gateway = build_gateway(mcp_client)
    role_adapter = RoleAgentAdapter(transport=role_transport)
    orchestrator = SingleSessionOrchestrator(gateway=gateway)

    runner = IssueSessionRunner(
        gateway=gateway,
        orchestrator=orchestrator,
        orchestrator_id="orch-main",
        prompt_template=template,
        implementer=role_adapter.implementer,
        spec_reviewer=role_adapter.spec_reviewer,
        quality_reviewer=role_adapter.quality_reviewer,
    )

    while True:
        runner.poll_ready_and_run_once()
        time.sleep(5)
```

### Parallel Dispatch Host

`WorkerPoolDispatcher` is a generic dispatch primitive.
For parallel runtime, host code must provide `claim_issue(issue_id)` and `run_issue_session(issue_id)` callables.

Defaults and policy:

- Default `max_workers=4`
- Sorting priority: `priority` ascending, then oldest `ready_at`, then `issue_id`
- Per-issue ordering is preserved by `SingleSessionOrchestrator`

## Session Lifecycle and Signals

Snapshots use `loop_snapshot.v1` and are written via issue feedback.

Primary event types:

- `SESSION_START`
- `IMPLEMENT_DONE`
- `SPEC_REVIEW_PASS` / `SPEC_REVIEW_FAIL`
- `SPEC_FIX_APPLIED`
- `QUALITY_REVIEW_PASS` / `QUALITY_REVIEW_FAIL`
- `QUALITY_FIX_APPLIED`
- `VERIFY_FAILED`
- `OVERFLOW_FIX_CREATED`
- `SESSION_DONE`
- `SESSION_ERROR`

Expected terminal outcomes:

- Success: `SESSION_DONE` and issue status set to `needs_review` (close is merge-gated)
- Verify failure: `VERIFY_FAILED` and issue remains not closed
- Overflow: `[FIX]` issue created, original issue linked and moved to `needs_review`
- Runtime exception after claim: `SESSION_ERROR` and issue reopened (`open`) by runner safeguard

Policy note:

- All issues must pass `needs_review` before `closed`.
- `needs_review` (issue status) is not the same as `needs-review` (PR label used for manual-review fallback signaling).
- Split-brain guardrail: merge-close daemon is the primary close authority; `.github/workflows/sudocode-close-on-merge.yml` remains audit-only (`--dry-run`).
- Before broad rollout, run one canary merge-close prove-out following `docs/runbooks/merge-close-daemon-wsl.md` and record journal + issue evidence.

## Operational Checks

### Every deployment or restart

1. Run dry-run command.
2. Confirm `docs/prompts/prompt_template.md` is present.
3. Confirm unit tests are green:

```bash
.venv/bin/python -m pytest tests/unit/ -x
```

### During operation

Check for each active issue:

- feedback snapshot stream is advancing
- stage transitions are ordered (`SPEC` before `QUALITY`)
- attempts do not exceed caps (spec <= 3, quality <= 2)
- terminal events appear for completed sessions

## Troubleshooting

### Symptom: no work is dispatched

- Check `get_ready_issues()` payload shape contains issue mappings.
- Confirm each issue has valid `issue_id`, `priority` in `0..4`, and `ready_at` datetime.
- Verify candidate selection is not saturated by active workers.

### Symptom: issue stuck at `in_progress`

- Inspect latest feedback event for `SESSION_ERROR` or missing terminal event.
- If session failed after claim, confirm runner reopened issue to `open`.
- Requeue by setting issue status to `open` through MCP if needed.

### Symptom: repeated overflow (`OVERFLOW_FIX_CREATED`)

- Inspect reviewer failed items and generated fix list in snapshot payload.
- Validate spec constraints in `ORCHESTRATION.md` and prompt template consistency.
- Address systemic reviewer mismatch before rerunning the same issue family.

### Symptom: snapshot validation errors

- Validate payload against `src/sudocode_orchestrator/snapshot.py` rules.
- Confirm timestamps are UTC ISO-8601 and attempts fields are non-negative ints.

## Recovery Procedure

1. Pause dispatcher host process.
2. Confirm no in-flight worker threads remain.
3. For each impacted issue, inspect feedback and set status to `open` if rerun is required.
4. Restart host loop.
5. Verify first processed issue reaches a valid terminal event.

## Escalation

Escalate when any of these persists after one recovery cycle:

- same issue fails with `SESSION_ERROR` repeatedly
- overflow rate exceeds normal baseline
- snapshot schema errors affect multiple issues

Attach:

- issue ids
- last 3 snapshot events per issue
- verification command/output from implementer evidence

## Related Docs

- `ORCHESTRATION.md`
- `docs/runbooks/merge-close-daemon-wsl.md`
- `AGENTS.md`
- `docs/prompts/prompt_template.md`
- `docs/runbooks/oncall-checklist.md`
