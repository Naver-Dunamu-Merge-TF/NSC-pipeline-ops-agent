---
name: approve
description: "Use when the user types /approve to fast-path approve completed work. Commits all pending changes, merges the current feature branch into dev, removes the worktree, deletes the feature branch, and closes the associated Sudocode issue. Non-interactive."
---

# approve

Execute all steps below immediately and in sequence. Non-interactive — do not pause for confirmation between steps.

Say "approve 시작합니다." then proceed without waiting.

## Step 1: Detect state

Get current branch (BRANCH), main repo path (MAIN_REPO = first path in `git worktree list`), and current directory (CWD).

Cases:
- **Case A**: already on `dev` — skip merge
- **Case B**: feature branch, not in a worktree
- **Case C**: feature branch, inside a worktree ← normal state after an agent session

## Step 2: Commit pending changes

Inspect what changed, then commit all tracked modifications. Skip if working tree is already clean. Do not stage untracked files.

## Step 3: Merge and clean up

**Case A**: nothing to merge. Proceed to Step 4.

**Case B**: checkout `dev`, merge BRANCH with `--no-ff`, delete BRANCH.

**Case C**: `git checkout` is unavailable (dev is checked out in the main repo). Use the main repo context (`git -C MAIN_REPO`) for all operations: merge, remove worktree, delete branch.

Order for Case C matters: remove worktree before deleting the branch (cannot delete a branch while it is checked out in a worktree).

## Step 4: Close Sudocode issue

Determine the issue ID:
1. Look in the current session context — the agent announces the issue ID it worked on.
2. If not found, ask the user: "어떤 이슈 ID를 닫을까요?"

Do not search logs or files. Context or user answer only.

Once the ID is known, use `sudocode-mcp` to set its status to `closed`.

## Step 5: Report

Summarize: commit made, branch merged and deleted, worktree removed (if applicable), issue closed.

All user-facing messages must be written in Korean.
