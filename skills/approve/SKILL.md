---
name: approve
description: "Use when the user types /approve to fast-path approve completed work. Commits pending tracked changes and policy-eligible untracked files, merges the current feature branch into dev, removes the worktree, deletes the feature branch, and closes the associated Sudocode issue. Non-interactive."
---

# approve

Execute all steps below immediately and in sequence. Non-interactive — do not pause for confirmation between steps.

## Step 1: Detect state

Get current branch (BRANCH), main repo path (MAIN_REPO = first path in `git worktree list`), and current directory (CWD).

Cases:
- **Case A**: already on `dev` — skip merge
- **Case B**: feature branch, not in a worktree
- **Case C**: feature branch, inside a worktree ← normal state after an agent session

## Step 2: Stage and commit changes

Run `git status --short`, then apply this staging policy without asking the user:

- **Common**: stage tracked modifications with `git add -u`.
- **Case A** (`dev`): do not stage untracked files.
- **Case B** (feature branch, non-worktree): stage only untracked files created/edited by this agent in the current session context.
- **Case C** (feature branch, worktree): stage only issue-scope untracked files for the current task/worktree.

Safety rules:

- Never stage potential secrets: `.env`, `.env.*`, `*.pem`, `*.key`, `*.p12`, `*credentials*.json`, `secrets.*`.
- Verify staged files with `git diff --cached --name-only`.
- If nothing is staged and the working tree is clean, skip commit.
- If nothing is staged but the working tree is not clean, stop before merge/cleanup and report the remaining files (no merge, no worktree removal).

If files are staged, create one commit.

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

Summarize in Korean:

- commit created or skipped (and why)
- number of staged tracked/untracked files
- files excluded by safety denylist
- branch merged/deleted status
- worktree removed status (if applicable)
- issue closed status

All user-facing messages must be written in Korean.
