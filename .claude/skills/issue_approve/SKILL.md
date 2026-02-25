---
name: issue_approve
description: "Use when the user types /issue_approve to fast-path approve completed work. Commits pending tracked changes and policy-eligible untracked files, merges the current feature branch into dev, removes the worktree, deletes the feature branch, and closes the associated Sudocode issue. Non-interactive except when the active worktree cannot be determined automatically or issue ID is unknown."
---

# issue_approve

Execute all steps below immediately and in sequence. Do not pause for confirmation unless explicitly instructed.

## Step 1: Detect state

Collect:
- CWD = current working directory (`pwd`)
- MAIN_REPO = first path in `git worktree list`
- BRANCH = `git branch --show-current` at CWD

**Important:** The agent session's CWD is always the main repo root, so BRANCH will typically be `dev` regardless of what the previous agent worked on. The canonical way to find the active feature branch is via `git worktree list`.

From `git worktree list`, collect all entries where branch ≠ `dev` and path ≠ MAIN_REPO and branch ≠ `(detached HEAD)`. For each candidate, verify the path exists on disk; skip stale entries.

- None remain → **stop** and report that no approvable feature branch was found
- Exactly one remains → set BRANCH = that branch, WORKTREE_PATH = that path
- Multiple remain → auto-select using the priority order below:
  1. **Session context** — match candidates against the issue ID announced in the current conversation (e.g., run-one declared "DEV-054"). Select the candidate whose branch name encodes that ID.
  2. **Most recent commit** — run `git -C PATH log -1 --format=%ct` for each candidate; select the one with the highest (most recent) timestamp.
  3. **Ask the user** — only if neither signal yields a single clear winner; list the candidates and ask the user to choose

  Record AUTO_SELECTED = true and SELECTION_REASON = (reason used) for use in Step 5.

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
   - If merge **succeeds** → continue to step 2.
   - If merge **fails with conflicts** →
     a. Run `git -C MAIN_REPO merge --abort` to restore a clean state.
     b. Collect the list of conflicting files from `git -C MAIN_REPO status`.
     c. **Stop** and report the merge conflict to the user, including the full list of conflicting files
     d. Do **not** proceed to worktree removal, branch deletion, or issue closing.
2. Remove WORKTREE_PATH — must happen before deleting the branch
3. Delete BRANCH — last, because it cannot be deleted while checked out in a worktree

## Step 4: Close Sudocode issue

Determine the issue ID using these signals in order:
1. Current session context — the agent announces the issue ID it worked on.
2. BRANCH name — branch names encode the issue ID by convention (e.g., `i-81e1-dev-054` → `DEV-054`, `i-3mms-adr-0007` → `ADR-0007`).
3. If neither yields an ID, ask the user for the issue ID

Once the ID is known, use `sudocode-mcp` to set its status to `closed`.

## Step 5: Report

Summarize all actions taken in Korean. If AUTO_SELECTED = true, include the selection reason in the summary.
