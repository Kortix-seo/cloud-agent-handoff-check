# What the open-source handoff check sees

This check ships from Kortix, the open-source AI Operating System, and one run of `check_handoff.py` prints a short report on a repository or, with `--json`, the same data as a document. Everything in it comes from the commit graph, which makes the report exact about what git recorded and silent about everything else.

## How a run is built

The script resolves the trunk, then reads two things: the merge commits on it, and the branches that never reached it.

Trunk resolution tries `origin/HEAD` first, so a clone of a project whose default branch is `dev` gets `dev` rather than `main`. If that ref is absent it tries `main`, `master`, `trunk` and `dev` in that order, then falls back to the current branch. `--default-branch NAME` overrides all of it.

`--since N` keeps a merge only if the merge commit itself is newer than N days, and keeps an open branch only if its newest commit is. `--json` prints the report object; without it the script prints the lines a person reads.

## The three questions

### 1. What landed, and how?

A landing is a merge commit reachable from the default branch, read with `git log --merges --first-parent`. Each one becomes an entry under `LANDED` with:

| Field | What it holds |
| --- | --- |
| `merge_sha` | the merge commit, first 12 characters |
| `merged_at`, `merged_by` | merge date, and the committer name |
| `commits`, `authors` | count and names of the commits the merge brought in |

The commit count comes from `merge^1..merge^2`, which is the work the branch carried, not the trunk history around it. A merge that brought in nothing is still listed, with a note and a zero.

### 2. Did someone else land it?

For each landing the script compares the merge committer's email with the author emails of the commits it brought in. If the committer's email is not among them, `reviewed_by_someone_else` is `true` and the text output says `someone else`. If it is, the field is `false` and the entry carries the note `merged by an identity that also authored the work (self-merge)`. A merge that brought in no commits gets `null`.

The summary line counts these as `merged by someone else` and `self-merged`, alongside `landings` and `commits in them`.

### 3. What is still open?

The script reads `refs/heads` and `refs/remotes`, strips the `origin/` prefix, then drops HEAD aliases and the default branch. Duplicate names collapse to one. A branch whose tip is already an ancestor of the default branch is skipped, and so is a branch with no commits ahead of it. What remains is listed under `OPEN`:

| Field | What it holds |
| --- | --- |
| `branch` | branch name without the remote prefix |
| `commits`, `authors` | commits ahead of the default branch, and their authors |
| `last_commit`, `days_open` | newest author date, and whole days since it |

`days_open` measures the newest commit on the branch, not the branch's creation date, so a branch opened three weeks ago and committed to yesterday reads as one day. Branches are sorted oldest first, and the summary reports `open branches` and `oldest_open_days`.

## What git records

A git commit stores two identities and two timestamps. The author is whoever wrote the change. The committer is whoever created that commit object. On a merge, the committer is the identity that ran the merge, and the author field is inherited from the merge machinery rather than written by a reviewer.

That gives the check exactly one review-shaped signal: whether the merging identity differs from the authors it merged. That signal is real, and it is the only review evidence inside a clone. Approvals, review comments, required checks and branch protection rules live in the forge's database, and none of them is copied into the repository.

## What it cannot see

**Squash and rebase landings leave no merge commit.** GitHub's squash and rebase buttons, and `git rebase` followed by a fast-forward, all rewrite the branch as ordinary commits on the trunk. There is no second parent to read, so nothing appears under `LANDED` and the summary reports zero landings. Read that as a fact about the history, not as proof that nothing happened.

**A squash-merged branch stays open.** Its commits never become ancestors of the trunk, so the original branch keeps appearing under `OPEN` after its work has landed. See a familiar branch name there and check the trunk's log before you call it stalled.

**Approvals are invisible.** The script cannot tell a person's merge from a bot's merge beyond the name and email on the commit, and a shared bot account erases even that difference. It also cannot see who approved a change request, whether CI passed, or how many reviewers were required.

**Renames and submodules are out of scope.** The script counts commits and never looks at file paths, so following a rename adds nothing it could report. A submodule's history lives in another repository and is not opened.

**History that was rewritten or deleted is gone.** Force-pushed branches, deleted branches and work that landed in a different repository are not recoverable from a clone, and the check reports only what the clone contains.

**Only the default branch is a landing target.** Merges into `release`, `staging` or a long-lived feature branch are not counted. If a team lands work somewhere else and promotes it later, the promotion is the landing this script sees.
