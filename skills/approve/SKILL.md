---
name: approve
description: "Use when the user types /approve to fast-path approve completed work. Commits pending tracked changes and policy-eligible untracked files, merges the current feature branch into dev, removes the worktree, deletes the feature branch, and closes the associated Sudocode issue. Non-interactive except when multiple worktrees are active or issue ID is unknown."
---

# approve

Execute all steps below immediately and in sequence. Do not pause for confirmation unless explicitly instructed.

## Step 1: Detect state

Collect:
- CWD = current working directory (`pwd`)
- MAIN_REPO = first path in `git worktree list`
- BRANCH = `git branch --show-current` at CWD

**Important:** The agent session's CWD is always the main repo root, so BRANCH will typically be `dev` regardless of what the previous agent worked on. The canonical way to find the active feature branch is via `git worktree list`.

From `git worktree list`, collect all entries where branch ≠ `dev` and path ≠ MAIN_REPO and branch ≠ `(detached HEAD)`. For each candidate, verify the path exists on disk; skip stale entries.

- None remain → **stop**: "승인할 피처 브랜치가 없습니다. 활성 워크트리를 확인하세요."
- Exactly one remains → set BRANCH = that branch, WORKTREE_PATH = that path
- Multiple remain → list them and ask the user: "어떤 워크트리를 승인할까요?" → set BRANCH and WORKTREE_PATH from the answer

## Step 2: Stage and commit changes

All git commands in this step must use `git -C WORKTREE_PATH`.

Check the working tree, then stage without asking the user:
- Stage tracked modifications.
- Stage untracked files under WORKTREE_PATH that belong to the current issue scope.
- Never stage standard secret/credential files.

Verify the staged file list before committing. If nothing is staged and the tree is clean, skip the commit. If unstaged changes remain, stop and ask the user how to proceed before continuing.

If files are staged, create one commit.

## Step 3: Merge and clean up

`git checkout` is unavailable (dev is checked out in the main repo). Use `git -C MAIN_REPO` for all operations below.

Order matters:
1. Merge BRANCH into dev with `--no-ff` — merge first while the branch is still valid
2. Remove WORKTREE_PATH — must happen before deleting the branch
3. Delete BRANCH — last, because it cannot be deleted while checked out in a worktree

## Step 4: Close Sudocode issue

Determine the issue ID using these signals in order:
1. Current session context — the agent announces the issue ID it worked on.
2. BRANCH name — branch names encode the issue ID by convention (e.g., `i-81e1-dev-054` → `DEV-054`, `i-3mms-adr-0007` → `ADR-0007`).
3. If neither yields an ID, ask the user: "어떤 이슈 ID를 닫을까요?"

Once the ID is known, use `sudocode-mcp` to set its status to `closed`.

## Step 5: Report

Summarize all actions taken in Korean.
