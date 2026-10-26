#!/usr/bin/env python3
"""check_handoff.py — what did the cloud agent hand back?

A read-only check you point at a git repository. It answers three questions about
the work an agent (or a person) produced there:

  1. What landed, and how?   every merge on the default branch in the window, the
                             commits it brought in, and the identity that merged it
  2. Did anyone review it?   whether the merging identity also authored the work
                             (a self-merge), or a different identity merged it
  3. What is still open?     branches that have not reached the default branch,
                             and how long they have been waiting

It never writes to the repository, never talks to a network and needs only the
`git` binary. Run it against your own repository, or against a project you are
evaluating before you let an agent work in it.

What it cannot see, by design: a squash or a rebase landing leaves no merge
commit, so it leaves no record here. That absence is the finding, not a bug —
say what your git history actually records.

Usage
    python3 check_handoff.py                    # the repository in the current directory
    python3 check_handoff.py --repo ../project  # another repository
    python3 check_handoff.py --since 14         # only the last 14 days
    python3 check_handoff.py --json             # machine-readable

Exit status is 0 when the check ran.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from typing import List, Optional

FMT = "%H%x1f%an%x1f%ae%x1f%at%x1f%cn%x1f%ce%x1f%s"


def git(repo: str, *args: str, check: bool = True) -> str:
    """Run one git command in `repo` and return stdout."""
    proc = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=False)
    if check and proc.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def git_ok(repo: str, *args: str) -> bool:
    return subprocess.run(["git", "-C", repo, *args], capture_output=True).returncode == 0


def default_branch(repo: str) -> str:
    """The branch the project treats as trunk, without assuming it is called main."""
    out = git(repo, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD", check=False).strip()
    if out:
        return out.rsplit("/", 1)[-1]
    for name in ("main", "master", "trunk", "dev"):
        if git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{name}", check=False).strip():
            return name
    return git(repo, "rev-parse", "--abbrev-ref", "HEAD", check=False).strip() or "HEAD"


@dataclass
class Commit:
    sha: str
    author_name: str
    author_email: str
    authored_at: datetime
    committer_name: str
    committer_email: str
    subject: str


@dataclass
class Landing:
    merge_sha: str
    merge_subject: str
    merged_at: str
    merged_by: str
    merged_by_email: str
    commits: int
    authors: List[str]
    reviewed_by_someone_else: Optional[bool]
    notes: List[str] = field(default_factory=list)


@dataclass
class OpenBranch:
    branch: str
    commits: int
    authors: List[str]
    last_commit: str
    days_open: int


def parse_commits(raw: str) -> List[Commit]:
    commits: List[Commit] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("\x1f")
        if len(parts) < 7:
            continue
        sha, an, ae, at, cn, ce, subject = parts[:7]
        commits.append(
            Commit(
                sha=sha,
                author_name=an,
                author_email=ae,
                authored_at=datetime.fromtimestamp(int(at), tz=timezone.utc),
                committer_name=cn,
                committer_email=ce,
                subject=subject,
            )
        )
    return commits


def landings(repo: str, default: str, since: Optional[datetime]) -> List[Landing]:
    """Every merge on the default branch, with the work it brought in."""
    raw = git(repo, "log", "--merges", "--first-parent", "--format=" + FMT, default, check=False)
    out: List[Landing] = []
    for merge in parse_commits(raw):
        if since and merge.authored_at < since:
            continue
        brought = parse_commits(git(repo, "log", "--format=" + FMT, f"{merge.sha}^1..{merge.sha}^2", check=False))
        authors = sorted({c.author_name for c in brought})
        author_emails = {c.author_email for c in brought}
        reviewed = None
        notes: List[str] = []
        if brought:
            reviewed = merge.committer_email not in author_emails
            if not reviewed:
                notes.append("merged by an identity that also authored the work (self-merge)")
        else:
            notes.append("merge brought in no commits of its own")
        out.append(
            Landing(
                merge_sha=merge.sha[:12],
                merge_subject=merge.subject,
                merged_at=merge.authored_at.isoformat(),
                merged_by=merge.committer_name,
                merged_by_email=merge.committer_email,
                commits=len(brought),
                authors=authors,
                reviewed_by_someone_else=reviewed,
                notes=notes,
            )
        )
    return out


def open_branches(repo: str, default: str, since: Optional[datetime]) -> List[OpenBranch]:
    """Branches that never reached the default branch."""
    now = datetime.now(tz=timezone.utc)
    names: List[str] = []
    for ref in git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes").splitlines():
        name = ref.strip()
        if not name or name.endswith("/HEAD"):
            continue
        if name.startswith("origin/"):
            name = name.split("/", 1)[1]
        if name != default and name not in names:
            names.append(name)
    out: List[OpenBranch] = []
    for name in names:
        if not git_ok(repo, "rev-parse", "--verify", "--quiet", name):
            continue
        if git_ok(repo, "merge-base", "--is-ancestor", name, default):
            continue
        commits = parse_commits(git(repo, "log", "--format=" + FMT, f"{default}..{name}", check=False))
        if not commits:
            continue
        newest = commits[0].authored_at
        if since and newest < since:
            continue
        out.append(
            OpenBranch(
                branch=name,
                commits=len(commits),
                authors=sorted({c.author_name for c in commits}),
                last_commit=newest.isoformat(),
                days_open=(now - newest).days,
            )
        )
    out.sort(key=lambda b: b.days_open, reverse=True)
    return out


def inspect(repo: str, default: str, since_days: Optional[int]) -> dict:
    since = datetime.now(tz=timezone.utc) - timedelta(days=since_days) if since_days else None
    landed = landings(repo, default, since)
    opened = open_branches(repo, default, since)
    self_merged = sum(1 for item in landed if item.reviewed_by_someone_else is False)
    return {
        "repo": repo,
        "default_branch": default,
        "checked_at": datetime.now(tz=timezone.utc).isoformat(),
        "since_days": since_days,
        "landings": [asdict(item) for item in landed],
        "open_branches": [asdict(item) for item in opened],
        "summary": {
            "landings": len(landed),
            "commits_in_landings": sum(item.commits for item in landed),
            "merged_by_someone_else": sum(1 for item in landed if item.reviewed_by_someone_else),
            "self_merged": self_merged,
            "open_branches": len(opened),
            "oldest_open_days": max((b.days_open for b in opened), default=0),
        },
    }


def render(report: dict) -> str:
    s = report["summary"]
    lines = [
        f"Handoff check — {report['repo']} (default branch: {report['default_branch']})",
        f"checked {report['checked_at']}"
        + (f", last {report['since_days']} days" if report["since_days"] else ""),
        "",
        f"landings: {s['landings']}    commits in them: {s['commits_in_landings']}    "
        f"merged by someone else: {s['merged_by_someone_else']}    self-merged: {s['self_merged']}",
        f"open branches: {s['open_branches']}    oldest: {s['oldest_open_days']}d",
        "",
    ]
    if not report["landings"] and not report["open_branches"]:
        lines.append("Nothing landed and nothing is open in this window: no handoff to check.")
        return "\n".join(lines)
    if report["landings"]:
        lines.append("LANDED")
        for item in report["landings"]:
            if item["reviewed_by_someone_else"] is None:
                who = "no work commits in this merge"
            elif item["reviewed_by_someone_else"]:
                who = "someone else"
            else:
                who = "the author (self-merge)"
            lines.append(
                f"  {item['merge_sha']}  {item['commits']} commit(s) by "
                f"{', '.join(item['authors']) or 'nobody'}  |  merged by {item['merged_by']} — {who}"
            )
            for note in item["notes"]:
                lines.append(f"      · {note}")
        lines.append("")
    if report["open_branches"]:
        lines.append("OPEN")
        for item in report["open_branches"]:
            lines.append(
                f"  {item['branch']}  {item['commits']} commit(s) by {', '.join(item['authors'])}"
                f"  | waiting {item['days_open']}d"
            )
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=".", help="path to the git repository (default: .)")
    parser.add_argument("--default-branch", default=None, help="override trunk detection")
    parser.add_argument("--since", default=None, help="window in days, e.g. 14 or 30d")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)

    since_days = None
    if args.since:
        since_days = int(str(args.since).rstrip("d."))
    if git(args.repo, "rev-parse", "--is-inside-work-tree", check=False).strip() != "true":
        raise SystemExit(f"{args.repo} is not a git work tree")
    default = args.default_branch or default_branch(args.repo)
    report = inspect(args.repo, default, since_days)
    print(json.dumps(report, indent=2) if args.json else render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
