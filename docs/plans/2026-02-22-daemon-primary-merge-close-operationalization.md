# Daemon-Primary Merge Close Operationalization Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Keep merge-close mutation authority in the local WSL daemon path so merged PRs close Sudocode issues reliably even when CI cannot access the same Sudocode backend.

**Architecture:** `merge_closer.apply_merge_close()` remains the only status-mutation authority. The daemon polls merged PR events, parses exactly one canonical `Sudocode-Issue: i-xxxx` field, and dispatches close via shared runtime helpers. GitHub Actions stays audit-only (`--dry-run`) and must fail if mutation mode is enabled.

**Tech Stack:** Python (`src/sudocode_orchestrator`), `gh` CLI, `sudocode` CLI, WSL2 user `systemd`, pytest, pre-commit.

---

## 1) Scope and Success Criteria

### Scope
- Keep daemon as the primary merge-close executor.
- Keep CI as non-mutating signal/audit observer.
- Harden daemon runtime safety (locking, checkpoint/replay, heartbeat, retry).
- Add operational guardrails and canary validation runbook.

### Out of Scope
- Introducing CI-side close mutation.
- Replacing `merge_closer` contract.
- Migrating to a remote Sudocode backend in this phase.

### Success Criteria
- A merged PR with valid canonical issue field is closed by daemon path (`needs_review -> closed`).
- CI run proves signal parsing path but performs zero status mutation.
- Duplicate/replayed merged events do not produce duplicate close transitions.
- Service restart does not lose close-eligible events.
- On-call can recover from daemon outage with operator fallback using the same `merge_closer` path.

## 2) Non-Negotiable Invariants

1. Close mutation must originate from `merge_closer` only.
2. Daemon is the single mutation actor in normal operations.
3. CI merged-PR workflow must run in dry-run mode only.
4. `needs_review` remains required precondition for any close transition.

## 3) Implementation Tasks (Bite-Sized, TDD)

### Task 1: Freeze authority policy in docs and workflow contract

**Files:**
- Modify: `docs/runbooks/orchestrator-runbook.md`
- Modify: `docs/runbooks/merge-close-daemon-wsl.md`
- Modify: `ORCHESTRATION_OPENCODE_NATIVE.md`
- Modify: `.github/workflows/sudocode-close-on-merge.yml`
- Test: `tests/unit/test_sudocode_close_on_merge.py`

**Step 1: Write failing test for audit-only workflow policy**
- Add assertion that merged PR workflow command contains `--dry-run` and does not use operator args.
- Add assertion that workflow fails fast when any mutation mode is requested from CI path.

**Step 2: Run test to verify failure**
- Run: `.venv/bin/python -m pytest tests/unit/test_sudocode_close_on_merge.py -x`
- Expected: workflow-command assertion fails before docs/command alignment.

**Step 3: Apply minimal implementation/docs**
- Update workflow command to explicit dry-run only path.
- Document daemon-primary and CI-audit-only authority split.
- Document split-brain prevention: no CI mutation path.

**Step 4: Run test to verify pass**
- Run: `.venv/bin/python -m pytest tests/unit/test_sudocode_close_on_merge.py -x`

**Step 5: Commit**
- Commit only Task 1 file set.

### Task 2: Harden daemon runtime safety and race handling

**Files:**
- Modify: `src/sudocode_orchestrator/merge_close_daemon.py`
- Modify: `scripts/sudocode_merge_close_daemon.py`
- Modify: `tests/unit/test_merge_close_daemon.py`
- Modify: `tests/fixtures/github_prs_merged.json` (if needed)

**Step 1: Write failing tests**
- Add test: concurrent/stale lock handling (`already running` vs stale lock takeover).
- Add test: replay after restart processes only new merge identities.
- Add test: malformed records are skipped safely.
- Add test: poll failure retries remain bounded and do not mutate state.
- Add test: PR body with zero/multiple `Sudocode-Issue:` fields is rejected with no close mutation.
- Add test: close dispatch is skipped when target issue status is not `needs_review`.

**Step 2: Run tests to verify failure**
- Run: `.venv/bin/python -m pytest tests/unit/test_merge_close_daemon.py -x`

**Step 3: Write minimal implementation**
- Ensure lock guard enforces single-instance semantics.
- Ensure checkpoint write is atomic and replay-safe.
- Ensure heartbeat emits mode/health state each cycle.
- Persist deterministic merge identity key (`repo + pr_number + merge_sha`) for replay idempotency.

**Step 4: Run tests to verify pass**
- Run: `.venv/bin/python -m pytest tests/unit/test_merge_close_daemon.py -x`

**Step 5: Commit**
- Commit only Task 2 file set.

### Task 3: Add systemd operational preflight and health guarantees

**Files:**
- Modify: `ops/systemd/sudocode-merge-close-daemon.service`
- Modify: `ops/systemd/sudocode-merge-close-daemon.env.example`
- Modify: `scripts/healthcheck_merge_close_daemon.py`
- Modify: `tests/unit/test_healthcheck_merge_close_daemon.py`

**Step 1: Write failing tests**
- Add test: stale heartbeat fails healthcheck.
- Add test: excessive poll failure count fails healthcheck.
- Add test: healthy heartbeat + poll budget passes.

**Step 2: Run tests to verify failure**
- Run: `.venv/bin/python -m pytest tests/unit/test_healthcheck_merge_close_daemon.py -x`

**Step 3: Write minimal implementation**
- Add `ExecStartPre` checks for gh auth, required env vars, writable paths.
- Keep `Restart=always` and user-systemd semantics.
- Emit clear operator guidance when health is degraded.

**Step 4: Run tests to verify pass**
- Run: `.venv/bin/python -m pytest tests/unit/test_healthcheck_merge_close_daemon.py -x`

**Step 5: Commit**
- Commit only Task 3 file set.

### Task 4: Add daemon service smoke validation

**Files:**
- Add: `tests/integration/test_merge_close_daemon_service_smoke.py`
- Modify: `docs/runbooks/merge-close-daemon-wsl.md`

**Step 1: Write failing integration smoke test**
- Add scenario: daemon process starts with test env, runs one poll cycle, writes heartbeat/checkpoint artifacts.

**Step 2: Run test to verify failure**
- Run: `.venv/bin/python -m pytest tests/integration/test_merge_close_daemon_service_smoke.py -x`

**Step 3: Write minimal implementation**
- Add any missing startup flags/hooks needed for one-cycle smoke mode.
- Document corresponding operator command in runbook.

**Step 4: Run test to verify pass**
- Run: `.venv/bin/python -m pytest tests/integration/test_merge_close_daemon_service_smoke.py -x`

**Step 5: Commit**
- Commit only Task 4 file set.

### Task 5: Real canary prove-out and operational handoff

**Files:**
- Modify: `docs/runbooks/merge-close-daemon-wsl.md`
- Modify: `docs/runbooks/orchestrator-runbook.md`

**Step 1: Define canary procedure in docs**
- Use one canary PR with canonical field and one `needs_review` canary issue.
- Add explicit rollback flow if wrong issue is closed.

**Step 2: Execute canary**
- Start daemon: `systemctl --user enable --now sudocode-merge-close-daemon.service`
- Merge canary PR and capture daemon log evidence.

**Step 3: Verify closure evidence**
- Verify issue status is `closed` via: `sudocode --json issue show <issue_id>`.
- Verify daemon logs contain close path evidence via: `journalctl --user -u sudocode-merge-close-daemon.service --since "15 min ago"`.
- Verify feedback contains merge evidence + close marker.

**Step 4: Record fallback validation**
- Stop daemon and validate operator fallback command once.
- Re-enable daemon and confirm healthy status.

**Step 5: Commit**
- Commit only Task 5 doc evidence/update set.

## 4) Verification Ladder

### L0
- `.venv/bin/python -m py_compile <changed_files>`

### L1
- `.venv/bin/python -m pytest tests/unit/ -x`

### L2
- `.venv/bin/python -m pytest tests/unit/ tests/integration/ --cov=src --cov-fail-under=80`
- If `tests/integration/` is unavailable, run fallback only as temporary local check and record unresolved risk (does not replace required L2/L3 evidence):
  - `.venv/bin/python -m pytest tests/unit/ --cov=src --cov-fail-under=80`

### L3
- Databricks Dev E2E suite.
- Pass criteria: end-to-end close flow and idempotency verified.

### Operational checks
- `systemctl --user status sudocode-merge-close-daemon.service`
- `journalctl --user -u sudocode-merge-close-daemon.service --since "15 min ago"`
- `sudocode --json issue show <issue_id>`

## 5) Rollout and Recovery

### Phase 1: Shadow
- Keep daemon running, observe poll/heartbeat/retry signals.

### Phase 2: Canary
- Run one canary merge and verify close markers.

### Phase 3: Full
- Treat daemon as default close executor for merged PR events.

### Recovery
1. Service down: restart service and confirm heartbeat.
2. Event missed: run operator fallback command.
3. Wrong close: reopen issue, add audit feedback, capture root cause.

### Validation evidence (2026-02-22)
- Verified merged PR canonical payload from live GitHub data:
  - `gh pr view 5 --json number,url,mergedAt,mergeCommit,body`
  - canonical field present: `Sudocode-Issue: i-5swp`
- Built isolated canary Sudocode DB (`/tmp/merge-close-canary.db`) with `i-5swp` in `needs_review` and a valid review-gate feedback marker.
- Daemon close canary prove-out:
  - command: `python3 scripts/sudocode_merge_close_daemon.py --once --db-path /tmp/merge-close-canary.db --checkpoint /tmp/merge-close-canary-checkpoint.json --heartbeat /tmp/merge-close-canary-heartbeat.json --lock-file /tmp/merge-close-canary.lock --gh-limit 50`
  - result: `sudocode --db /tmp/merge-close-canary.db --json issue show i-5swp` returned `"status": "closed"` and feedback markers `MERGE_EVIDENCE_RECORDED`, `MERGE_CLOSE_APPLIED` with `"source": "daemon"`.
- Operator fallback prove-out against the same canary DB after reopen + fresh review-gate marker:
  - command: `python3 scripts/sudocode_close_on_merge.py --issue-id i-5swp --pr-url https://github.com/Naver-Dunamu-Merge-TF/NSC-pipeline-ops-agent/pull/5 --merge-sha e7a50c476a17668d6e6eb988767e47f436a08ca4 --merged-at 2026-02-21T16:20:37Z --source operator --db-path /tmp/merge-close-canary.db`
  - result: `invoked=true`, `result.applied=true`; subsequent `issue show` confirmed `"status": "closed"` with operator-source merge markers.

## 6) Acceptance Checklist

- [x] CI merged-PR workflow remains dry-run only.
- [x] Daemon closes canary issue from `needs_review` after merge event.
- [x] Duplicate merge events stay idempotent.
- [x] Single-instance lock behavior is tested.
- [x] Healthcheck reflects heartbeat and poll-failure budget.
- [x] Operator fallback uses same merge closer path and works once end-to-end.
