# Orchestrator On-Call Checklist

Use this checklist for handoff, active incidents, and post-incident closure.

## Preflight (Start of Shift)

- [ ] Confirm branch/environment and deployment target.
- [ ] Run dry-run health check:
  - `PYTHONPATH=src python -m sudocode_orchestrator.runner --dry-run`
- [ ] Confirm `last_event_type` is `SESSION_DONE`.
- [ ] Confirm prompt template exists: `docs/prompts/prompt_template.md`.
- [ ] Confirm no unresolved critical failures from previous shift.

## Active Monitoring

- [ ] Ready issues are being consumed at expected rate.
- [ ] Active sessions produce feedback snapshots.
- [ ] Stage ordering remains valid (`SPEC_REVIEW` before `QUALITY_REVIEW`).
- [ ] Attempt caps are respected (spec <= 3, quality <= 2).
- [ ] Terminal events appear (`SESSION_DONE`, `VERIFY_FAILED`, `OVERFLOW_FIX_CREATED`, or `SESSION_ERROR`).

## Incident Triage

### A) Dispatch stalled

- [ ] Inspect ready payload shape and required fields (`issue_id`, `priority`, `ready_at`).
- [ ] Confirm worker capacity is available.
- [ ] Check for malformed issue records causing candidate parsing failures.

### B) Issue stuck `in_progress`

- [ ] Inspect latest feedback event.
- [ ] If no terminal event after runtime failure, reopen issue to `open`.
- [ ] Re-run one issue manually to verify recovery.

### C) Overflow spike

- [ ] Inspect `failed_items` and `fix_list` in overflow snapshots.
- [ ] Verify prompt template and spec assumptions are unchanged.
- [ ] Escalate if overflow repeats for same pattern.

### D) Snapshot schema failures

- [ ] Validate timestamp format and UTC offset.
- [ ] Validate `attempts` and `verify` object fields.
- [ ] Confirm payload aligns with `loop_snapshot.v1` constraints.

## Recovery Actions

- [ ] Pause dispatcher host.
- [ ] Drain or terminate in-flight workers cleanly.
- [ ] Requeue impacted issues (`open`) after evidence capture.
- [ ] Resume dispatcher.
- [ ] Validate first recovered issue reaches expected terminal event.

## Escalation Trigger

Escalate immediately if any condition is true:

- [ ] Same issue hits repeated `SESSION_ERROR` after one retry cycle.
- [ ] Snapshot validation errors appear across multiple issues.
- [ ] Overflow/FIX generation volume exceeds normal baseline significantly.

## Handoff Notes

- [ ] Record issue ids impacted during shift.
- [ ] Record latest event type and timestamp per impacted issue.
- [ ] Record manual status transitions performed.
- [ ] Record unresolved risks and recommended next action.
