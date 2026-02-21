# Parallel Agent Orchestration Plan (Sudocode)

> Execution model: Sudocode is the execution-state SSOT, orchestrator performs runtime execution, and Web UI is an always-synced observability surface.

## 1) Scope and Success Criteria

### Scope
- Build a production-ready orchestrator that:
  - Polls `sudocode-mcp_ready`
  - Claims ready issues and runs one issue per single session
  - Executes role loop in fixed order: implementer -> spec reviewer -> quality reviewer
  - Applies retry caps and overflow behavior
  - Writes structured feedback snapshots for dashboard/analytics

### Out of Scope
- Changing Sudocode core internals
- Replacing Sudocode Web UI workflow
- Changing prompt wording in `docs/prompts/prompt_template.md`

### Success Criteria
- Multiple independent ready issues execute concurrently via worker pool
- Each issue session preserves strict review order and retry policy
- Overflow creates `[FIX]` issue and moves original issue to `needs_review`
- Every stage produces valid snapshot JSON (`schema_version=loop_snapshot.v1`)
- Dashboard can reconstruct timeline from snapshots without reading raw logs

## 2) Ground Rules and Invariants

### SSOT and State Rules
- Sudocode issue state is SSOT for coarse status: `open -> in_progress -> needs_review -> closed`
- Session-stage state is not issue status; it is feedback snapshot data
- One issue session remains serial internally, parallelism happens across issues
- `closed` is merge-gated; all issues must pass `needs_review` before `closed`
- Terminology is strict: issue status `needs_review` (underscore) vs PR label `needs-review` (hyphen)

### Prompt Rules
- Runtime template source: `docs/prompts/prompt_template.md`
- Allowed mutation at render time:
  - Placeholder replacement only (`{{manifest_id}}`, `{{task_id}}`, `{{gate_id}}`, `{{epic_id}}`, `{{title}}`, `{{depends_on}}`, `{{dod_checklist_full}}`)
  - Newline normalization only
- Any unresolved placeholder is a hard failure

### Loop Rules
- Quality review cannot start before spec pass
- `SPEC_REVIEW` max attempts: 3
- `QUALITY_REVIEW` max attempts: 2
- Overflow behavior:
  - Create `[FIX] {task_id}: {title}` issue
  - Link original -> fix issue
  - Set original issue to `needs_review` (no direct close)
- Completion gate:
  - Latest verification exit code must be `0`
  - Verification timestamp must be >= latest code-change timestamp in current session

## 3) Target Runtime Architecture

## 3.1 Components
- `SudocodeGateway` (MCP wrapper)
  - Abstracts all MCP calls and idempotent error handling
- `ReadyPoller`
  - Pulls ready issues on interval with jitter
- `ClaimManager`
  - Performs claim transition and emits `SESSION_START` snapshot
- `WorkerPoolDispatcher`
  - Schedules independent issues across worker slots
- `IssueSessionRunner`
  - Executes single-session loop for one issue
- `RoleAgentAdapter`
  - Executes implementer/spec/quality role prompts and parses outputs
- `SnapshotEmitter`
  - Validates and writes `loop_snapshot.v1`
- `FixIssueFactory`
  - Builds FIX issue body from overflow context

## 3.2 File Layout (Planned)
- `src/sudocode_orchestrator/gateway.py` (new)
- `src/sudocode_orchestrator/runner.py` (new)
- `src/sudocode_orchestrator/claim.py` (new)
- `src/sudocode_orchestrator/snapshot.py` (new)
- `src/sudocode_orchestrator/agent_roles.py` (new)
- `src/sudocode_orchestrator/session_loop.py` (extend existing)
- `src/sudocode_orchestrator/prompt_renderer.py` (reuse existing)
- `tests/unit/test_gateway.py` (new)
- `tests/unit/test_runner.py` (new)
- `tests/unit/test_snapshot.py` (new)
- `tests/unit/test_agent_roles.py` (new)

## 4) Runtime Execution Flow

1. Poll ready queue via `sudocode-mcp_ready`
2. Select up to `max_workers` independent issues
3. Claim issue:
   - `upsert_issue(issue_id, status=in_progress)`
   - Write `SESSION_START` snapshot with `session_id`, `orchestrator_id`
4. Load issue details (`show_issue`) and render prompt from `docs/prompts/prompt_template.md`
5. Run `SingleSessionOrchestrator.run_issue(...)`
6. On `DONE`: set issue to `needs_review`, write final success snapshot
7. On `OVERFLOW`: create FIX issue, link issues, set original to `needs_review`, write overflow snapshot
8. On `VERIFY_FAILED`: keep `in_progress` or mark policy status (recommended: keep `in_progress` + failure snapshot)
9. Repeat loop

Pseudo-flow:

```python
while True:
    ready = gateway.get_ready_issues()
    candidates = scheduler.pick_independent(ready, limit=max_workers)
    for issue in candidates:
        worker_pool.submit(run_single_issue_session, issue)
    sleep(poll_interval_with_jitter)
```

## 5) Parallelism Strategy

### 5.1 Where Parallelism Exists
- Yes: across issues (`issue A`, `issue B`, `issue C`) in separate workers
- No: within one issue session stage ordering stays strict

### 5.2 Worker Scheduling Policy
- `max_workers` configurable (start with `4`)
- Candidate ordering:
  1) priority asc (0 highest)
  2) oldest ready first
  3) deterministic tie-break by issue id
- Optional conflict avoidance:
  - Skip concurrent issues when `affected_files` overlap (if metadata exists)

### 5.3 Claim Safety
- Primary mode: single orchestrator process with internal worker pool
- If multi-orchestrator is required later:
  - Add explicit claim token in issue feedback
  - Re-read issue after claim and reject duplicate ownership

## 6) Auto Review + Fix Loop (During Development)

This section defines how to implement this orchestrator using parallel agents with automatic review/fix loops.

### 6.1 Workstream Split for Parallel Agents
- Agent A: `gateway.py` + `test_gateway.py`
- Agent B: `snapshot.py` + `test_snapshot.py`
- Agent C: `runner.py` + `claim.py` + `test_runner.py`
- Agent D: `agent_roles.py` + `test_agent_roles.py`
- Agent E: integrate `session_loop.py` updates + end-to-end unit scenarios

Dependency DAG:
- A and B can start immediately
- C can start with stubs, final integration depends on A/B
- D can start immediately
- E starts after A/B/D are merged, then integrates with C

### 6.2 Per-Agent Execution Contract
- TDD only:
  1) write failing test
  2) run failing test
  3) implement minimal code
  4) run passing test
- Scope lock: agent edits only assigned files
- Output contract:
  - root cause summary
  - files changed
  - verification command and result

### 6.3 Automated Review/Fix Loop for Agent Output
- For each agent output, run two reviewers in order:
  1) spec reviewer (checks against this document and loop invariants)
  2) code quality reviewer (readability/safety/maintainability)
- If reviewer fails:
  - Generate fix list
  - Return fix list to same agent
  - Re-run review
- Retry caps for development review loop:
  - spec review: max 3
  - quality review: max 2
- On overflow:
  - stop normal loop for that workstream
  - open follow-up FIX task in implementation board

## 7) Snapshot Schema (Fixed)

Schema id: `loop_snapshot.v1`

Required fields:
- `schema_version`: `"loop_snapshot.v1"`
- `session_id`: string (uuid-like)
- `orchestrator_id`: string
- `issue_id`: string
- `task_id`: string
- `event_type`: enum
- `stage`: enum
- `status`: `"START" | "PASS" | "FAIL" | "FIX_CREATED" | "VERIFY_FAILED" | "NEEDS_REVIEW"`
- `attempts`: object
- `failed_items`: string[]
- `fix_list`: string[]
- `verify`: object|null
- `timestamp`: ISO-8601 UTC

`event_type` enum (v1):
- `SESSION_START`
- `IMPLEMENT_DONE`
- `SPEC_REVIEW_PASS`
- `SPEC_REVIEW_FAIL`
- `SPEC_FIX_APPLIED`
- `QUALITY_REVIEW_PASS`
- `QUALITY_REVIEW_FAIL`
- `QUALITY_FIX_APPLIED`
- `OVERFLOW_FIX_CREATED`
- `VERIFY_FAILED`
- `SESSION_DONE`
- `SESSION_ERROR`

`stage` enum (v1):
- `RUNNING`
- `SPEC_REVIEW`
- `SPEC_FIX`
- `QUALITY_REVIEW`
- `QUALITY_FIX`
- `VERIFICATION`
- `OVERFLOW`
- `REVIEW_GATE`
- `DONE`

`verify` object:
- `command`: string
- `exit_code`: int
- `produced_at`: ISO-8601 UTC
- `output_ref`: string (optional pointer)

Example:

```json
{
  "schema_version": "loop_snapshot.v1",
  "session_id": "sess-20260221-001",
  "orchestrator_id": "orch-main",
  "issue_id": "i-abc1",
  "task_id": "DEV-001",
  "event_type": "SPEC_REVIEW_FAIL",
  "stage": "SPEC_REVIEW",
  "status": "FAIL",
  "attempts": { "spec": 1, "quality": 0 },
  "failed_items": ["DoD #2"],
  "fix_list": ["Add edge-case test for DoD #2"],
  "verify": {
    "command": "python -m pytest tests/unit/ -x",
    "exit_code": 0,
    "produced_at": "2026-02-21T10:13:00Z",
    "output_ref": "feedback:12345"
  },
  "timestamp": "2026-02-21T10:13:05Z"
}
```

## 8) SudocodeGateway MCP Mapping

Gateway method mapping:
- `get_ready_issues()` -> `sudocode-mcp_ready`
- `show_issue(issue_id)` -> `sudocode-mcp_show_issue`
- `set_issue_status(issue_id, status)` -> `sudocode-mcp_upsert_issue`
- `add_feedback(issue_id, snapshot_json)` -> `sudocode-mcp_add_feedback`
- `create_fix_issue(title, body)` -> `sudocode-mcp_upsert_issue`
- `link_issues(from_id, to_id, type)` -> `sudocode-mcp_link`

Error handling rules:
- MCP transient failure: retry with exponential backoff (max 3)
- Permanent failure: emit `SESSION_ERROR` snapshot and stop processing that issue
- Idempotency:
  - `SESSION_START` contains deterministic `session_id`
  - duplicate snapshot writes must be tolerated by analytics

## 9) Verification Plan

### Unit Level
- `tests/unit/test_gateway.py`
- `tests/unit/test_runner.py`
- `tests/unit/test_snapshot.py`
- `tests/unit/test_agent_roles.py`
- Existing:
  - `tests/unit/test_prompt_renderer.py`
  - `tests/unit/test_session_loop.py`

### Command Ladder
- L0: `python -m py_compile <changed_files>`
- L1: `python -m pytest tests/unit/ -x`
- L2 sanity before PR: `python -m pytest tests/unit/ tests/integration/ --cov=src --cov-fail-under=80` (if integration paths exist)

### Acceptance Checklist
- [ ] Parallel dispatch executes at least 2 ready issues concurrently
- [ ] Per-issue stage order never violates spec-before-quality
- [ ] Overflow creates FIX issue and moves original to `needs_review`
- [ ] All closes happen only after `needs_review` via merge-confirmed close path
- [ ] Snapshot payloads all validate as `loop_snapshot.v1`
- [ ] Dashboard timeline reconstructs from feedback only

## 10) Rollout Plan

### Phase 1 (MVP)
- Single orchestrator process
- Worker pool size `4`
- Snapshot schema `v1`
- Manual start/stop

### Phase 2 (Hardening)
- Retry/jitter tuning
- richer analytics extraction from snapshots
- optional multi-orchestrator support with claim token

### Phase 3 (Ops)
- periodic health summary and stalled-session alerts
- operational runbook and on-call checklist

## 11) Immediate Remaining Tasks (Actionable)

1. Implement `SudocodeGateway` MCP wrapper and tests
2. Add `snapshot.py` validator + schema tests
3. Add `runner.py` polling/dispatch loop + tests
4. Add `agent_roles.py` adapters + tests
5. Integrate runner with existing `SingleSessionOrchestrator`
6. Add dry-run command for local simulation against mocked gateway
7. Run verification ladder and fix findings
