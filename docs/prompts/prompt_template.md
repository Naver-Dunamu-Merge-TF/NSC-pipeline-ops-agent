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
Treat the injected checklist below as the source of truth and review it line by line.

{{dod_checklist_full}}

### Ordered Workflow (Do Not Reorder)
1) implementer
- Implement the task and provide current-attempt verification evidence.

2) spec reviewer
- Start after implementer output.
- Review against every injected DoD line item.
- If any item fails, return a fix list to implementer.

3) code quality reviewer
- Start only after spec reviewer reports PASS.
- Validate code quality, safety, and maintainability.
- If quality fails, return a fix list to implementer.

### Sub-Agent Delegation Policy (All Roles)
- implementer, spec reviewer, and code quality reviewer MAY delegate independent subtasks to sub-agents, including parallel execution.
- Delegation MUST preserve the Ordered Workflow and review gates.
- Each role remains accountable for its final step output (evidence or PASS/FAIL with fix list).
- Delegation MUST remain within this task scope and MUST NOT bypass retry/overflow policies.
- If sub-agent outputs conflict or touch shared mutable state/files, resolve and integrate sequentially before completing the role step.

### Review Loop Policy
- Spec review/fix loop limit: max 3 attempts total.
- Quality review/fix loop limit: max 2 attempts total.
- If a reviewer fails at its final allowed attempt, stop normal loop and trigger overflow handling.

### Overflow Handling (Retry Limit Exceeded)
If SPEC_REVIEW fails at attempt 3/3 or QUALITY_REVIEW fails at attempt 2/2, create and start a FIX task via:
- POST /api/task-attempts/create-and-start

FIX prompt requirements:
- title: [FIX] {task_id}: {title}
- body must include all of: original task id, overflow reason, failed acceptance items, latest verification evidence/output, full original DoD.

### Verification Before Completion
- Do not mark DONE without fresh verification evidence from the current attempt.
- Verification evidence must be concrete command output or equivalent runtime proof.
- If verification is stale, missing, or from a prior attempt, task is NOT DONE.
