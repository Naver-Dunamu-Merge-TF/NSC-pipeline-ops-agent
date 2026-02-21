# WSL Merge-Close Daemonization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** In WSL, make merge-close run reliably from a local daemon so merged PRs transition Sudocode issues from `needs_review` to `closed` using shared local state.

**Architecture:** Keep `merge_closer.apply_merge_close()` as the only close authority. Add a polling daemon that reads merged PR events via `gh`, parses exactly one canonical `Sudocode-Issue: i-xxxx` field, and dispatches close requests with checkpoint-based idempotency. Keep GitHub workflow as audit-only signal path while local daemon is primary executor.

**Tech Stack:** Python (`src/sudocode_orchestrator`), `gh` CLI, `sudocode` CLI, WSL2 + systemd, pytest, pre-commit.

---

## 1) Scope and Success Criteria

### Scope
- Add a WSL-friendly long-running merge-close daemon.
- Use existing parser/dispatch contracts from `scripts/sudocode_close_on_merge.py` without changing close policy semantics.
- Persist daemon checkpoint to survive restart and avoid duplicate transitions.
- Enforce single-instance daemon execution per workspace.
- Convert GitHub merge-close workflow to audit-only behavior while daemon is primary.
- Add WSL runbook covering startup, restart, health checks, and operator fallback.

### Out of Scope
- Building a new remote Sudocode backend service.
- Replacing orchestrator session-loop policy.
- Reworking GitHub label taxonomy or approval policy.

### Success Criteria
- Merged PR with canonical field closes target issue within 2 polling cycles.
- Missing/duplicate/malformed canonical field never triggers close.
- Duplicate merge signals do not create duplicate terminal transitions.
- Daemon restart resumes from checkpoint, replays safely, and does not re-close already processed merges.
- Out-of-order/paginated PR fetches do not drop close-eligible events.
- Runbook-only operation is possible for on-call in WSL.

## 2) Runtime Design

### 2.1 Primary Close Path
1. PR is merged on GitHub.
2. WSL daemon polls merged PRs with `gh`.
3. Daemon extracts `Sudocode-Issue` from PR body.
4. Daemon calls shared close dispatcher (`apply_merge_close`).
5. `merge_closer` writes merge evidence + close marker and updates issue status.

### 2.2 Idempotency Contract
- Checkpoint stores durable processed identities keyed by `merge_sha` (with `pr_number` metadata for diagnostics), not only the latest tuple.
- Polling uses deterministic query window and pagination so all merged PRs in range are visited.
- Checkpoint writes are atomic (`tmp file -> fsync -> rename`) with schema version.
- Replayed events are skipped before dispatch using processed identity set.
- If replay reaches `merge_closer`, existing idempotent markers still protect terminal state.
- If checkpoint is unreadable/corrupt, daemon enters safe mode (no mutation) and emits operator action guidance.

### 2.3 Fallback Contract
- If daemon is down or parser rejects payload, operator runs:
  - `.venv/bin/python scripts/sudocode_close_on_merge.py --issue-id ... --pr-url ... --merge-sha ... --merged-at ...`
- Fallback must route through same `merge_closer` path.

### 2.4 Assumptions and Constraints
- One daemon instance per workspace/state backend.
- Daemon host has valid `gh auth` session and `sudocode` CLI access.
- WSL systemd is enabled and service lifecycle is system-managed, not terminal-managed.

## 3) Implementation Tasks (Bite-Sized, TDD)

### Task 1: Extract reusable close-on-merge runtime module

**Files:**
- Add: `src/sudocode_orchestrator/close_on_merge_runtime.py`
- Modify: `scripts/sudocode_close_on_merge.py`
- Modify: `tests/unit/test_sudocode_close_on_merge.py`

**Step 1: Write failing tests**
- Move parser/dispatch-focused tests to target runtime module APIs.
- Keep fail cases for zero/multiple/malformed canonical field.

**Step 2: Run tests to verify failure**
- Run: `.venv/bin/python -m pytest tests/unit/test_sudocode_close_on_merge.py -x`
- Expected: import/path mismatch failures.

**Step 3: Write minimal implementation**
- Extract parser, payload builder, dispatch helpers into runtime module.
- Keep script as thin CLI wrapper.

**Step 4: Run tests to verify pass**
- Run: `.venv/bin/python -m pytest tests/unit/test_sudocode_close_on_merge.py -x`

**Step 5: Commit**
- Commit only Task 1 file set.

### Task 2: Implement WSL merge-close daemon with checkpoint

**Files:**
- Add: `src/sudocode_orchestrator/merge_close_daemon.py`
- Add: `scripts/sudocode_merge_close_daemon.py`
- Add: `tests/unit/test_merge_close_daemon.py`
- Add: `tests/fixtures/github_prs_merged.json`

**Step 1: Write failing tests**
- New merged PR is dispatched exactly once.
- Already checkpointed merge is skipped.
- Invalid canonical field is rejected without mutation.
- Successful dispatch advances checkpoint.
- `gh` command failure (non-zero exit) does not mutate state and retries with bounded backoff.
- Malformed PR JSON record is skipped without daemon crash.
- Restart replay test: batch A processed, restart, replay A+B -> only B dispatches.
- Partial checkpoint write/corrupt checkpoint enters safe mode.

**Step 2: Run tests to verify failure**
- Run: `.venv/bin/python -m pytest tests/unit/test_merge_close_daemon.py -x`

**Step 3: Write minimal implementation**
- Add `gh` polling adapter.
- Add JSON checkpoint load/save.
- Dispatch through runtime module from Task 1.
- Add lockfile/PID guard to prevent concurrent daemon instances.
- Add independent heartbeat timestamp update on every poll cycle (including no-merge cycles).

**Step 4: Run tests to verify pass**
- Run: `.venv/bin/python -m pytest tests/unit/test_merge_close_daemon.py -x`

**Step 5: Commit**
- Commit only Task 2 file set.

### Task 3: Add WSL systemd service and healthcheck

**Files:**
- Add: `ops/systemd/sudocode-merge-close-daemon.service`
- Add: `ops/systemd/sudocode-merge-close-daemon.env.example`
- Add: `scripts/healthcheck_merge_close_daemon.py`
- Add: `tests/unit/test_healthcheck_merge_close_daemon.py`

**Step 1: Write failing tests**
- Healthcheck fails when daemon heartbeat is stale beyond threshold.
- Healthcheck degrades when last N polls failed even if heartbeat is fresh.
- Healthcheck passes when heartbeat is fresh and poll status is healthy.

**Step 2: Run tests to verify failure**
- Run: `.venv/bin/python -m pytest tests/unit/test_healthcheck_merge_close_daemon.py -x`

**Step 3: Write minimal implementation**
- Service unit with explicit scope decision (`system` or `--user`), `Restart=always`, env file, working directory, and log identifiers.
- Add `ExecStartPre` checks (`gh auth status`, writable checkpoint path, required env vars).
- Healthcheck script validates heartbeat freshness and poll error budget.

**Step 4: Run tests to verify pass**
- Run: `.venv/bin/python -m pytest tests/unit/test_healthcheck_merge_close_daemon.py -x`

**Step 5: Commit**
- Commit only Task 3 file set.

### Task 4: Shift GitHub workflow to audit-only

**Files:**
- Modify: `.github/workflows/sudocode-close-on-merge.yml`
- Modify: `tests/unit/test_sudocode_close_on_merge.py`

**Step 1: Write failing tests**
- Add/adjust test ensuring audit mode does not perform status mutation.
- Add assertion that workflow path cannot call mutation dispatch when running merged PR event handling.

**Step 2: Run tests to verify failure**
- Run: `.venv/bin/python -m pytest tests/unit/test_sudocode_close_on_merge.py -x`

**Step 3: Write minimal implementation**
- Make workflow always run `--dry-run` on `pull_request.closed` merged events.
- Add explicit note that close authority is local daemon path.

**Step 4: Run tests to verify pass**
- Run: `.venv/bin/python -m pytest tests/unit/test_sudocode_close_on_merge.py -x`

**Step 5: Commit**
- Commit only Task 4 file set.

### Task 5: WSL runbook and operator procedure

**Files:**
- Add: `docs/runbooks/merge-close-daemon-wsl.md`
- Modify: `docs/runbooks/orchestrator-runbook.md`
- Modify: `ORCHESTRATION_OPENCODE_NATIVE.md`

**Step 1: Write doc checklist (as assertions)**
- Include bootstrap/start/stop/restart commands.
- Include operator fallback command examples.
- Re-state `needs_review` (issue status) vs `needs-review` (PR label).

**Step 2: Apply minimal doc edits**
- Add service installation and troubleshooting sequence.

**Step 3: Validate references and regressions**
- Run: `.venv/bin/python -m pytest tests/unit/ -x`
- Run: `.venv/bin/pre-commit run --all-files`

**Step 4: Commit**
- Commit only Task 5 file set.

## 4) Parallel Subagent Build Plan

### 4.1 Workstream Split
- Agent A: Task 1 (runtime module extraction)
- Agent B: Task 2 (daemon + checkpoint)
- Agent C: Task 3 (systemd + healthcheck)
- Agent D: Task 4 (workflow audit mode)
- Agent E: Task 5 (runbook/docs)

### 4.2 Dependency DAG
- A starts first.
- B depends on A runtime interface.
- C depends on B heartbeat/checkpoint contract.
- D depends on A parser/dispatch interface and must land before Primary Mode cutover.
- E can draft early, but finalization depends on B/C/D implementation details.
- Final integration after A+B+C+D+E.

### 4.3 Review Loop
- For each task: implementer -> spec reviewer -> quality reviewer.
- Retry caps: spec <= 3, quality <= 2.
- Overflow opens dedicated FIX issue; no forced close.

## 5) Verification Ladder

### L0
- `.venv/bin/python -m py_compile <changed_files>`

### L1
- `.venv/bin/python -m pytest tests/unit/ -x`

### L2
- Primary: `.venv/bin/python -m pytest tests/unit/ tests/integration/ --cov=src --cov-fail-under=80`
- Fallback if `tests/integration/` missing: `.venv/bin/python -m pytest tests/unit/ --cov=src --cov-fail-under=80` and record rationale.

### L3
- In WSL systemd environment, `systemctl enable --now` succeeds and service auto-recovers after `wsl --shutdown`.
- Replay the same merged event 3 times: exactly one `MERGE_CLOSE_APPLIED`, issue status changes to `closed` exactly once.
- Simulate temporary `gh` outage: no mutation during outage, missed merge is closed exactly once after recovery.
- One operator fallback execution succeeds and produces expected merge-evidence + close markers.

## 6) Rollout and Recovery

### Phase 1: Shadow Mode
- Run daemon in observe-only/log mode for one day.
- Validate polling, parsing, and checkpoint progression.

### Phase 2: Canary Mode
- Prerequisite: Task 4 audit-only workflow is deployed (prevents split-brain mutation).
- Enable real dispatch for selected issues.
- Confirm merge evidence and close markers are written.

### Phase 3: Primary Mode
- Keep daemon as primary close executor.
- Keep GitHub workflow audit-only.
- Keep single-instance guard enabled and alert on duplicate daemon startup attempts.

### Recovery Procedure
1. Restart service.
2. Validate heartbeat freshness and poll failure budget.
3. If checkpoint is corrupt, switch to safe mode and run checkpoint repair/rollback procedure.
4. Backfill missed merge window with operator fallback command.
5. Keep issue at `needs_review` if preconditions fail.

### Validation evidence (2026-02-22)
- Pagination/out-of-order regression coverage added in `tests/unit/test_merge_close_daemon.py`:
  - `test_gh_cli_poller_paginates_and_sorts_out_of_order_records`
  - `test_gh_cli_poller_does_not_drop_newer_records_on_later_pages`
- Operator fallback end-to-end coverage added in `tests/integration/test_sudocode_close_on_merge_operator_fallback.py` (real script path).
- Operational spot check against isolated canary DB (`/tmp/merge-close-canary.db`) validated both daemon-source and operator-source close markers for `i-5swp` tied to merged PR `#5`.
- WSL restart recovery proof:
  - after `wsl.exe --shutdown`, journal showed new boot marker and user service auto-start (`-- Boot ... --` then `Started sudocode-merge-close-daemon.service`).
  - post-restart healthcheck returned `{"status":"healthy","reason":"ok","exit_code":0,...}`.
- Runbook hardening for on-call-only execution:
  - added explicit worktree override steps for `WorkingDirectory` and `.runtime` paths in `docs/runbooks/merge-close-daemon-wsl.md`.
  - strengthened auth precondition checks with `gh api user --jq .login`.

## 7) Acceptance Checklist

- [x] Daemon survives WSL restart and auto-recovers
- [x] Merged PR closes issue only when canonical field is valid
- [x] Invalid canonical field never closes issue
- [x] Duplicate merge events remain idempotent
- [x] Out-of-order/paginated fetch cannot drop close-eligible events
- [x] WSL runbook alone is enough for on-call operations
- [x] CI workflow no longer acts as primary close authority
- [x] Split-brain mutation path (workflow + daemon both mutating) is impossible by config
- [x] Operator fallback is verified end-to-end
