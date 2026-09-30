"""Create branches, commits, and pull requests for GitHub issue runs."""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from agentic_company.github_issues import IssueRef, _github_headers


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def slugify_branch(title: str, issue_number: int) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", title.lower()).strip("-")[:40] or "fix"
    return f"agentic/issue-{issue_number}-{slug}"


def load_issue_meta(thread_id: str) -> dict[str, Any] | None:
    from agentic_company.config import get_settings

    path = get_settings().artifacts_dir(thread_id) / "github_issue.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def default_base_branch(repo: Path) -> str:
    for name in ("main", "master"):
        proc = _run_git(repo, "rev-parse", "--verify", f"origin/{name}")
        if proc.returncode == 0:
            return name
    proc = _run_git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    return (proc.stdout or "main").strip() or "main"


def ensure_git_identity(repo: Path) -> None:
    name = os.getenv("GIT_AUTHOR_NAME", "agentic-company")
    email = os.getenv("GIT_AUTHOR_EMAIL", "agentic-company@users.noreply.github.com")
    _run_git(repo, "config", "user.name", name)
    _run_git(repo, "config", "user.email", email)


def commit_all_changes(repo: Path, message: str) -> dict[str, Any]:
    ensure_git_identity(repo)
    _run_git(repo, "add", "-A")
    status = _run_git(repo, "status", "--porcelain")
    if not (status.stdout or "").strip():
        return {"committed": False, "reason": "no changes to commit"}
    commit = _run_git(repo, "commit", "-m", message)
    if commit.returncode != 0:
        return {
            "committed": False,
            "reason": (commit.stderr or commit.stdout or "commit failed").strip(),
        }
    return {"committed": True, "message": message}


def create_pull_request(
    *,
    repo_path: Path,
    ref: IssueRef,
    title: str,
    body: str,
    branch: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    token = token or os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or ""
    if not token:
        return {
            "ok": False,
            "error": "GITHUB_TOKEN required to push branch and open a PR",
        }
    if not repo_path.is_dir():
        return {"ok": False, "error": "workspace/repo missing; re-run with --clone"}

    branch = branch or slugify_branch(title, ref.number)
    base = default_base_branch(repo_path)

    checkout = _run_git(repo_path, "checkout", "-B", branch)
    if checkout.returncode != 0:
        return {
            "ok": False,
            "error": f"checkout failed: {(checkout.stderr or checkout.stdout).strip()}",
        }

    commit_result = commit_all_changes(
        repo_path,
        f"Fix: {title} (#{ref.number})\n\nImplemented by agentic-company.",
    )

    # Ensure remote uses token for push
    remote = (
        f"https://x-access-token:{urllib.parse.quote(token)}"
        f"@github.com/{ref.owner}/{ref.repo}.git"
    )
    _run_git(repo_path, "remote", "set-url", "origin", remote)
    push = _run_git(repo_path, "push", "-u", "origin", "HEAD")
    if push.returncode != 0:
        return {
            "ok": False,
            "error": f"git push failed: {(push.stderr or push.stdout).strip()}",
            "commit": commit_result,
            "branch": branch,
        }

    payload = {
        "title": f"Fix #{ref.number}: {title}",
        "head": branch,
        "base": base,
        "body": body,
    }
    api = f"https://api.github.com/repos/{ref.owner}/{ref.repo}/pulls"
    req = urllib.request.Request(
        api,
        data=json.dumps(payload).encode("utf-8"),
        headers={**_github_headers(token), "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        return {
            "ok": False,
            "error": f"GitHub PR API {exc.code}: {err[:800]}",
            "commit": commit_result,
            "branch": branch,
        }

    return {
        "ok": True,
        "pr_url": data.get("html_url"),
        "pr_number": data.get("number"),
        "branch": branch,
        "base": base,
        "commit": commit_result,
        "raw": {
            "number": data.get("number"),
            "html_url": data.get("html_url"),
            "state": data.get("state"),
        },
    }


def build_pr_body(
    *,
    issue_url: str,
    issue_number: int,
    summary: str,
    test_output: str,
    files_touched: list[str],
) -> str:
    files = "\n".join(f"- `{p}`" for p in files_touched) or "- (see commit)"
    return f"""## Summary
{summary.strip() or '(see ISSUE_NOTES.md)'}

Closes #{issue_number}
Issue: {issue_url}

## Tests
```
{(test_output or '(not run)')[:4000]}
```

## Files
{files}

---
Opened automatically by agentic-company.
"""
