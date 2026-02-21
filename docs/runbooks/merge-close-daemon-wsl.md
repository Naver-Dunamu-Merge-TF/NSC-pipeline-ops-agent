# WSL Merge-Close Daemon Runbook

## Purpose

Operate the WSL merge-close daemon so merged PRs move Sudocode issues from `needs_review` to `closed` through one primary close path.

## Scope

- WSL host using systemd.
- Local daemon runtime and health checks.
- Operator fallback when daemon path is unavailable.
- Incident triage for common failure modes.

## Guardrails

- Issue status is `needs_review` (Sudocode field), PR fallback label is `needs-review` (GitHub label).
- These signals are related but not interchangeable.
- Split-brain avoidance: daemon is the primary close authority; CI merge-close workflow stays audit-only.

## Preconditions

1. WSL2 is installed and your distro supports systemd.
2. `/etc/wsl.conf` enables systemd:

```ini
[boot]
systemd=true
```

3. WSL restarted after config change (`wsl.exe --shutdown` from Windows).
4. Repo checkout exists at one of:
   - `%h/dev/NSC-pipeline-ops-agent` (default unit `WorkingDirectory`), or
   - an active worktree path such as `%h/dev/NSC-pipeline-ops-agent/.worktrees/<name>`.
5. `gh auth status` succeeds in the same Linux user context that runs the service.
6. Sudocode CLI is available in that same user context.

Quick checks:

```bash
ps -p 1 -o comm=
systemctl is-system-running
gh auth status
gh api user --jq .login
```

Expected:

- PID 1 process is `systemd`.
- system state is `running` or `degraded` (if degraded, continue only if unrelated).
- GitHub auth is valid and API calls succeed.

## Service Install and Enable

This runbook assumes Task 3 artifacts exist:

- `ops/systemd/sudocode-merge-close-daemon.service`
- `ops/systemd/sudocode-merge-close-daemon.env.example`

Install sequence (user scope):

```bash
mkdir -p ~/.config/systemd/user ~/.config/sudocode
cp ops/systemd/sudocode-merge-close-daemon.service ~/.config/systemd/user/
cp ops/systemd/sudocode-merge-close-daemon.env.example ~/.config/sudocode/sudocode-merge-close-daemon.env
sed -i "s|/home/PLACEHOLDER|$HOME|g" ~/.config/sudocode/sudocode-merge-close-daemon.env
systemctl --user daemon-reload
systemctl --user enable --now sudocode-merge-close-daemon.service
```

If you are operating from a worktree, override service/env paths before `daemon-reload`:

```bash
WORKTREE_DIR="$HOME/dev/NSC-pipeline-ops-agent/.worktrees/<name>"
sed -i "s|^WorkingDirectory=.*|WorkingDirectory=$WORKTREE_DIR|" ~/.config/systemd/user/sudocode-merge-close-daemon.service
sed -i "s|$HOME/dev/NSC-pipeline-ops-agent/.runtime|$WORKTREE_DIR/.runtime|g" ~/.config/sudocode/sudocode-merge-close-daemon.env
```

Verify:

```bash
systemctl --user status sudocode-merge-close-daemon.service --no-pager
journalctl --user -u sudocode-merge-close-daemon.service -n 100 --no-pager
```

## Service Operations

```bash
systemctl --user start sudocode-merge-close-daemon.service
systemctl --user stop sudocode-merge-close-daemon.service
systemctl --user restart sudocode-merge-close-daemon.service
systemctl --user reload-or-restart sudocode-merge-close-daemon.service
systemctl --user is-active sudocode-merge-close-daemon.service
```

Use `reload-or-restart` after env changes when service supports reload; otherwise restart is used.

## Healthcheck Usage

Primary health check command:

```bash
.venv/bin/python scripts/healthcheck_merge_close_daemon.py
```

Operational usage:

- Run after every start/restart.
- Run before and after WSL reboot validation.
- Run during incidents to distinguish runtime crash vs upstream API/auth failures.

If healthcheck fails, inspect:

```bash
systemctl --user status sudocode-merge-close-daemon.service --no-pager
journalctl --user -u sudocode-merge-close-daemon.service -n 200 --no-pager
```

## One-Cycle Smoke Command

Run one daemon poll cycle with local artifact outputs:

```bash
.venv/bin/python scripts/sudocode_merge_close_daemon.py --once --checkpoint .runtime/merge-close-checkpoint.smoke.json --lock-file .runtime/merge-close-daemon.smoke.lock --heartbeat .runtime/merge-close-heartbeat.smoke.json
```

## Canary Prove-Out

Use one canary issue/PR pair before broad rollout.

1. Ensure daemon service is active:

```bash
systemctl --user status sudocode-merge-close-daemon.service --no-pager
```

2. Merge a canary PR with exactly one canonical line in PR body:

```text
Sudocode-Issue: i-xxxx
```

3. Validate close evidence:

```bash
sudocode --json issue show i-xxxx
journalctl --user -u sudocode-merge-close-daemon.service --since "15 min ago" --no-pager
```

Expected:

- issue status transitions from `needs_review` to `closed`
- feedback contains merge evidence and `MERGE_CLOSE_APPLIED`

### Canary rollback (wrong issue closed)

If a non-target issue is closed:

1. Reopen immediately:

```bash
sudocode issue update i-xxxx --status needs_review
```

2. Add incident feedback with PR URL and merge SHA.
3. Pause daemon (`systemctl --user stop ...`) until root cause is identified.
4. Resume daemon only after corrective patch or explicit operator mitigation.

## Operator Fallback Command

Use fallback only when daemon is unavailable or intentionally paused.

```bash
.venv/bin/python scripts/sudocode_close_on_merge.py \
  --issue-id i-PLACEHOLDER \
  --pr-url https://github.com/ORG/REPO/pull/PLACEHOLDER \
  --merge-sha PLACEHOLDER \
  --merged-at 2026-01-01T00:00:00Z \
  --source operator
```

Fallback rules:

- Use real values from the merged PR event.
- Run once per merge event identity.
- Do not use fallback concurrently with an active daemon processing the same window.

## Incident Triage

### 1) Service does not start

- Check `ExecStartPre` failures, especially `gh auth status`.
- Validate env file path and required variables.
- Confirm checkpoint directory exists and is writable by service user.

### 2) Service running but no issues close

- Confirm PR body contains exactly one canonical `Sudocode-Issue: i-xxxx` field.
- Confirm merged PR is within daemon polling window.
- Confirm issue currently sits in `needs_review` (close from other statuses is rejected).

### 3) Healthcheck stale or degraded

- Restart service once and re-run healthcheck.
- Check for repeated `gh` API errors or auth expiration.
- If stale persists, pause daemon and execute targeted fallback for missed merges.

### 4) Suspected split-brain behavior

- Confirm CI workflow is running in audit-only mode.
- Confirm only one daemon instance is active for this workspace/state backend.
- Stop duplicate daemon instance immediately and keep one close authority.

## Recovery Procedure

1. `systemctl --user restart sudocode-merge-close-daemon.service`
2. Run healthcheck and review logs.
3. Backfill missed merges with fallback command when needed.
4. Verify affected issues transition from `needs_review` to `closed` exactly once.
5. Record incident notes (time window, issue IDs, root cause, mitigation).

## Escalation Data

When escalating, include:

- service status output
- last 200 journal lines
- healthcheck output
- affected issue IDs and PR URLs
- fallback commands executed (if any)
