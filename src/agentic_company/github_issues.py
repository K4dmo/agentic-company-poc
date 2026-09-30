"""Fetch GitHub issues and turn them into company briefs."""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ISSUE_URL_RE = re.compile(
    r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/#]+)/issues/(?P<number>\d+)",
    re.IGNORECASE,
)
SHORTHAND_RE = re.compile(
    r"^(?P<owner>[^/\s]+)/(?P<repo>[^/#\s]+)#(?P<number>\d+)$"
)


@dataclass(frozen=True)
class IssueRef:
    owner: str
    repo: str
    number: int

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"

    @property
    def url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repo}/issues/{self.number}"


@dataclass
class GitHubIssue:
    ref: IssueRef
    title: str
    body: str
    state: str
    labels: list[str]
    author: str
    comments: list[dict[str, str]]
    raw: dict[str, Any]

    def to_brief(self) -> str:
        labels = ", ".join(self.labels) if self.labels else "(none)"
        comment_blocks = []
        for i, c in enumerate(self.comments[:10], start=1):
            comment_blocks.append(
                f"### Comment {i} (@{c.get('author', 'unknown')})\n{c.get('body', '').strip()}"
            )
        comments_text = "\n\n".join(comment_blocks) if comment_blocks else "(no comments)"
        return f"""Implement this GitHub issue end-to-end in the workspace.

Repository: {self.ref.full_name}
Issue: #{self.ref.number}
URL: {self.ref.url}
State: {self.state}
Labels: {labels}
Author: @{self.author}

## Title
{self.title}

## Description
{self.body.strip() or '(empty body)'}

## Comments
{comments_text}

## Implementation rules
- Stay scoped to this issue; do not invent unrelated features.
- ALWAYS add or update automated tests for the change.
- Run tests with the run_tests tool (pytest) before finishing.
- If the workspace already contains a cloned repository under repo/, implement inside it.
- Write ISSUE_NOTES.md summarizing what you changed and how to verify.
- After human ship approval, the company will open a PR and draft a LinkedIn post automatically.
""".strip()


def parse_issue_ref(
    issue: str | None = None,
    *,
    repo: str | None = None,
    number: int | None = None,
) -> IssueRef:
    if repo and number is not None:
        if "/" not in repo:
            raise ValueError("repo must be owner/name")
        owner, name = repo.split("/", 1)
        return IssueRef(owner=owner, repo=name.removesuffix(".git"), number=int(number))

    if not issue:
        raise ValueError("Provide an issue URL, owner/repo#n, or --repo with --number")

    text = issue.strip()
    m = ISSUE_URL_RE.search(text)
    if m:
        return IssueRef(
            owner=m.group("owner"),
            repo=m.group("repo").removesuffix(".git"),
            number=int(m.group("number")),
        )
    m = SHORTHAND_RE.match(text)
    if m:
        return IssueRef(
            owner=m.group("owner"),
            repo=m.group("repo").removesuffix(".git"),
            number=int(m.group("number")),
        )
    raise ValueError(
        f"Unrecognized issue reference: {issue!r}. "
        "Use https://github.com/owner/repo/issues/123 or owner/repo#123"
    )


def _github_headers(token: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "agentic-company",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = token or os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or ""
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _get_json(url: str, token: str | None = None) -> Any:
    req = urllib.request.Request(url, headers=_github_headers(token), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {exc.code} for {url}: {body[:500]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GitHub API network error: {exc}") from exc


def fetch_repo_profile(ref: IssueRef, *, token: str | None = None) -> dict[str, Any]:
    """Fetch repository description, topics, and README excerpt for announcements."""
    api = f"https://api.github.com/repos/{ref.owner}/{ref.repo}"
    data = _get_json(api, token=token)
    readme_text = ""
    try:
        readme = _get_json(f"{api}/readme", token=token)
        encoded = readme.get("content") or ""
        if encoded:
            readme_text = base64.b64decode(encoded).decode("utf-8", errors="replace")[:4000]
    except Exception:  # noqa: BLE001
        # Fall back to local clone README if API readme fails
        readme_text = ""

    return {
        "full_name": data.get("full_name") or ref.full_name,
        "description": data.get("description") or "",
        "homepage": data.get("homepage") or "",
        "html_url": data.get("html_url") or f"https://github.com/{ref.full_name}",
        "topics": list(data.get("topics") or []),
        "stars": data.get("stargazers_count"),
        "language": data.get("language"),
        "readme_excerpt": readme_text,
    }


def load_local_readme(workspace: Path) -> str:
    for rel in ("repo/README.md", "repo/Readme.md", "README.md"):
        path = workspace / rel
        if path.is_file():
            try:
                return path.read_text(encoding="utf-8")[:4000]
            except OSError:
                continue
    return ""


def is_first_issue(ref: IssueRef, *, token: str | None = None) -> bool:
    """True when this issue is the earliest non-PR issue in the repository.

    Falls back to issue number == 1 if the listing API fails.
    """
    if ref.number == 1:
        return True
    try:
        # Created ascending; include open+closed. Filter out PRs client-side.
        url = (
            f"https://api.github.com/repos/{ref.owner}/{ref.repo}/issues"
            f"?state=all&sort=created&direction=asc&per_page=30"
        )
        items = _get_json(url, token=token)
        if not isinstance(items, list):
            return ref.number == 1
        for item in items:
            if "pull_request" in item:
                continue
            first_number = int(item.get("number") or 0)
            return first_number == ref.number
    except Exception:  # noqa: BLE001
        return ref.number == 1
    return ref.number == 1


def fetch_issue(ref: IssueRef, *, token: str | None = None, include_comments: bool = True) -> GitHubIssue:
    api = f"https://api.github.com/repos/{ref.owner}/{ref.repo}/issues/{ref.number}"
    data = _get_json(api, token=token)
    if "pull_request" in data:
        raise RuntimeError(
            f"{ref.url} is a pull request, not an issue. Pass a GitHub Issues URL."
        )

    comments: list[dict[str, str]] = []
    if include_comments and int(data.get("comments") or 0) > 0:
        comments_url = data.get("comments_url") or f"{api}/comments"
        raw_comments = _get_json(comments_url, token=token)
        if isinstance(raw_comments, list):
            for item in raw_comments[:15]:
                comments.append(
                    {
                        "author": (item.get("user") or {}).get("login") or "unknown",
                        "body": item.get("body") or "",
                    }
                )

    labels = []
    for label in data.get("labels") or []:
        if isinstance(label, dict) and label.get("name"):
            labels.append(str(label["name"]))
        elif isinstance(label, str):
            labels.append(label)

    return GitHubIssue(
        ref=ref,
        title=str(data.get("title") or ""),
        body=str(data.get("body") or ""),
        state=str(data.get("state") or "open"),
        labels=labels,
        author=(data.get("user") or {}).get("login") or "unknown",
        comments=comments,
        raw=data,
    )


def issue_artifact_payload(issue: GitHubIssue, *, token: str | None = None) -> dict[str, Any]:
    first = False
    try:
        first = is_first_issue(issue.ref, token=token)
    except Exception:  # noqa: BLE001
        first = issue.ref.number == 1
    return {
        "url": issue.ref.url,
        "repo": issue.ref.full_name,
        "number": issue.ref.number,
        "title": issue.title,
        "state": issue.state,
        "labels": issue.labels,
        "author": issue.author,
        "body": issue.body,
        "comments": issue.comments,
        "is_first_issue": first,
    }


def clone_repo_into_workspace(
    ref: IssueRef,
    workspace: Path,
    *,
    token: str | None = None,
    depth: int = 1,
) -> Path:
    """Shallow-clone the issue's repository into workspace/repo."""
    dest = workspace / "repo"
    if dest.exists():
        return dest

    token = token or os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or ""
    if token:
        # x-access-token works for HTTPS clones with PATs
        remote = (
            f"https://x-access-token:{urllib.parse.quote(token)}"
            f"@github.com/{ref.owner}/{ref.repo}.git"
        )
    else:
        remote = f"https://github.com/{ref.owner}/{ref.repo}.git"

    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["git", "clone", f"--depth={depth}", remote, str(dest)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError("git is required to clone the repository") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"git clone failed: {exc.stderr or exc.stdout or exc}"
        ) from exc
    return dest
