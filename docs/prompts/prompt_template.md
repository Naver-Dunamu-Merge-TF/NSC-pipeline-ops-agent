## VK Task Execution Prompt

You are executing a dispatcher-generated task.

### Task Metadata
- manifest_id: {{manifest_id}}
- task_id: {{task_id}}
- gate_id: {{gate_id}}
- epic_id: {{epic_id}}
- title: {{title}}
- depends_on: {{depends_on}}

### Scope
- Implement only this task.
- Keep changes minimal and aligned to task intent.

### Acceptance Checklist (Full DoD Injection)
The section below is the source of truth for acceptance and must be reviewed line by line.

{{dod_checklist_full}}

### Ordered Workflow (Do Not Reorder)
1) implementer
- Implement the task and provide verification evidence.

2) spec reviewer
- Review against every injected DoD line item.
- If any item fails, return a fix list to implementer.

3) code quality reviewer
- Start only after spec reviewer reports PASS.
- Validate code quality, safety, and maintainability.
- If quality fails, return a fix list to implementer.

### Review Loop Policy
- Quality review cannot begin before spec PASS.
- Spec review/fix loop limit: max 3 attempts total.
- Quality review/fix loop limit: max 2 attempts total.
- If a reviewer fails at its final allowed attempt, stop normal loop and trigger overflow handling.

### Overflow Handling (Retry Limit Exceeded)
If SPEC_REVIEW fails at attempt 3/3 or QUALITY_REVIEW fails at attempt 2/2, create and start a FIX task via:
- POST /api/task-attempts/create-and-start

FIX prompt requirements:
- title: [FIX] {task_id}: {title}
- body must include all of:
  - original task id
  - overflow reason
  - failed acceptance items
  - latest verification evidence/output
  - full original DoD

### Verification Before Completion
- Do not mark DONE without fresh verification evidence from the current attempt.
- Verification evidence must be concrete command output or equivalent runtime proof.
- If verification is stale, missing, or from a prior attempt, task is NOT DONE.
