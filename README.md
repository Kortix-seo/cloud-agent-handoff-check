# cloud-agent-handoff-check

An open-source, read-only check of what a cloud agent's work came back as: which merges landed on the default branch, who merged them, and whether the agent merged its own work.

`check_handoff.py` is one Python file. It needs Python 3 and the `git` binary and nothing else: no packages, no network, no writes to the repository it reads. Point it at a project that a cloud agent has been working in and it prints the landing record from that repository's own history. Run it on your own project, or on a vendor's before you let an agent work there.

Cloud agent comparisons usually list where the agent runs. What decides whether its work is usable is what comes back: a change someone else could refuse, or a diff you copy out of a vendor's pane. Run the check against the candidate.

## Run it

```bash
git clone https://github.com/Kortix-seo/cloud-agent-handoff-check.git
cd cloud-agent-handoff-check
python3 check_handoff.py --repo ../your-project
python3 check_handoff.py --repo ../your-project --since 14
```

The third command checks the repository you name; the fourth limits the report to the previous 14 days. With no arguments the script checks the repository in the current directory. Exit status is 0 when the check ran.

Other flags:

```bash
python3 check_handoff.py --repo ../your-project --json             # full report as JSON
python3 check_handoff.py --repo ../your-project --default-branch trunk
```

The trunk is detected from `origin/HEAD`, then `main`, `master`, `trunk` and `dev`, then the current branch. `--default-branch` skips that detection. To audit a repository you do not own, clone it first, with all branches, so the open ones are visible.

## The three questions

**What landed, and how?** The script lists every merge commit on the default branch in the window (`LANDED`), each with its merge sha, `commit(s) by` the authors whose work it brought in, and `merged by` the identity that committed the merge. The summary line counts `landings` and the `commits in them`.

**Did someone else land it?** For each merge, the script compares the committer email with the author emails of the commits the merge brought in. When they match, the branch prints the label `the author (self-merge)`; when a different email committed the merge, it prints `someone else`. The summary counts both as `self-merged` and `merged by someone else`.

**What is still open?** Branches whose tip has not reached the default branch (`OPEN`), with the number of commits each carries and `waiting Nd`, counted from the newest commit on that branch. The summary gives `open branches` and `oldest`.

## What it cannot see

- **Squash and rebase landings.** Neither leaves a merge commit, so neither appears under `LANDED`. An empty landing list is a finding about the history, not proof that no work landed.
- **The branch behind a squash merge.** A branch squash-merged into the trunk never becomes an ancestor of it, so it keeps showing up under `OPEN`. That branch is landed work, not a stalled handoff.
- **Approvals.** The script reads commit metadata. An approving click, a review comment and a CI result live in the forge, not in the clone, so none of them is visible here. `someone else` means a different email committed the merge. Whether that identity is a person with merge rights is a question for the team.
- **Renames and submodules.** The script counts commits and never reads file paths, so a rename carries no signal and a submodule's own history is not opened.
- **An empty merge.** A merge commit that brought in no commits of its own is listed with the note `merge brought in no commits of its own`, and its JSON field `reviewed_by_someone_else` is `null`.

## How to read the result

**A self-merge** means the identity that authored the work also committed it to the trunk, so the landing carries no second name. A review may still have happened in the forge; the history does not record it. Where one person and one agent work together, that can be deliberate. In a team it means the merge gate and the authorship are the same account.

**A merge by someone else** is the handoff you want to see: a second identity put the work on the trunk. Read the name on it. A consistent human name on every merge is a review process, while a bot name on every merge is automation that happens to use a different email, which is not the same thing.

**An open branch older than a few days** is work the agent finished and nobody landed. The count grows with every session, and the old branches are the ones whose context has moved farthest.

**A history of only fast-forwards** answers nothing: no merge commits means no landing record, so the check returns zero landings. Ask that team how changes reach their trunk and where the record of who approved them lives.

For the longer version of that handoff, the Cloud Agents Guide has a page on [agents that open a pull request](https://cloudagentsguide.com/cloud-agents-that-open-a-pr). It covers what a pull request from an agent should contain, and who is allowed to merge it.

The rest of the guide starts from the definitions: [what a cloud agent is](https://cloudagentsguide.com/what-is-a-cloud-agent), [cloud agent vs local agent](https://cloudagentsguide.com/cloud-agent-vs-local-agent), [self-hosted cloud agents](https://cloudagentsguide.com/self-hosted-cloud-agents), [what cloud agents cost](https://cloudagentsguide.com/cloud-agent-pricing) and [cloud agent alternatives](https://cloudagentsguide.com/cloud-agent-alternatives).

## Real output

Two runs on 2026-10-26. Header lines are trimmed; the rest is verbatim.

A repository with one merge of a two-commit branch, and one open branch:

```text
landings: 1    commits in them: 2    merged by someone else: 0    self-merged: 1
open branches: 1    oldest: 0d

LANDED
  380fefdacd24  2 commit(s) by Kortix Agent  |  merged by Kortix Agent — the author (self-merge)
      · merged by an identity that also authored the work (self-merge)

OPEN
  session-3  1 commit(s) by Kortix Agent  | waiting 0d
```

The same script on a repository where a different identity merged the branch:

```text
landings: 1    commits in them: 1    merged by someone else: 1    self-merged: 0

LANDED
  3e74911b8474  1 commit(s) by Kortix Agent  |  merged by Reviewer — someone else
```

Exit status was 0 on both.

## Kortix

This repo comes from [Kortix](https://kortix.com), the open-source AI Operating System: your agents, skills, memory, and connectors in one repo you own. A Kortix session works on its own branch and opens a change request that a person with the `project.gitops.merge` permission reviews and merges ([Kortix docs](https://kortix.com/docs)), which is the handoff this script audits, whichever system produced it.

## Contributing

Issues and pull requests are welcome. The script stays standard-library-only and read-only, so a change that adds a dependency, calls the network, or writes to the repository will be declined. Keep the output stable: people diff it between runs, and a new field is easier to justify than a renamed one.
