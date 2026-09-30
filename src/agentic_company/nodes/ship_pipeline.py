"""Post-ship nodes for GitHub issue runs: test → PR → LinkedIn announce."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agentic_company.config import get_settings
from agentic_company.github_issues import (
    IssueRef,
    fetch_repo_profile,
    is_first_issue,
    load_local_readme,
)
from agentic_company.github_pr import (
    build_pr_body,
    create_pull_request,
    load_issue_meta,
)
from agentic_company.llm import get_chat_model
from agentic_company.persistence import write_artifact
from agentic_company.tools.linkedin_builder import make_linkedin_builder_tools


class LinkedInAnnounceDraft(BaseModel):
    hook: str
    body: str
    cta: str = "What would you have prioritized instead?"
    hashtags: list[str] = Field(default_factory=lambda: ["#engineering", "#opensource", "#buildinpublic"])
    tone: str = "professional, concise"
    audience: str = "engineers and technical leaders"


def build_linkedin_announce_messages(
    *,
    meta: dict[str, Any],
    notes: str,
    pr_url: Any,
    tests_passed: Any,
    builder_summary: Any,
    first_issue: bool,
    project: dict[str, Any],
) -> tuple[str, str]:
    if first_issue:
        system = (
            "You write LinkedIn posts for the FIRST shipped issue of a repository. "
            "The post must introduce the PROJECT (what it is, who it is for, why it matters) "
            "AND mention this first issue/milestone as the starting point. "
            "Be concrete, avoid hype, no fake metrics. Strong hook + short paragraphs."
        )
        human = (
            f"This is the first issue of the repository — cover the project AND the issue.\n\n"
            f"Project: {project.get('full_name')}\n"
            f"Description: {project.get('description')}\n"
            f"Homepage: {project.get('homepage')}\n"
            f"Language: {project.get('language')}\n"
            f"Topics: {', '.join(project.get('topics') or []) or '(none)'}\n"
            f"Repo URL: {project.get('html_url')}\n"
            f"README excerpt:\n{str(project.get('readme_excerpt') or '')[:2500]}\n\n"
            f"First issue title: {meta.get('title')}\n"
            f"Issue URL: {meta.get('url')}\n"
            f"PR URL: {pr_url}\n"
            f"Tests passed: {tests_passed}\n"
            f"Builder summary: {builder_summary}\n"
            f"Issue notes:\n{notes[:3000]}\n"
        )
    else:
        system = (
            "You write concise LinkedIn posts announcing a shipped engineering fix. "
            "Be concrete, avoid hype, no fake metrics. Include a hook and short body."
        )
        human = (
            f"Issue title: {meta.get('title')}\n"
            f"Issue URL: {meta.get('url')}\n"
            f"PR URL: {pr_url}\n"
            f"Tests passed: {tests_passed}\n"
            f"Builder summary: {builder_summary}\n"
            f"Notes:\n{notes[:4000]}\n"
        )
    return system, human


def verify_tests_node(state: dict[str, Any]) -> dict[str, Any]:
    workspace = Path(state.get("workspace_root") or ".")
    repo = workspace / "repo"
    cwd = repo if repo.is_dir() else workspace
    settings = get_settings()
    commands = [
        ["python", "-m", "pytest", "-q"],
        ["pytest", "-q"],
    ]
    output = ""
    passed = False
    used = None
    for cmd in commands:
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=settings.test_timeout_seconds,
                check=False,
            )
        except FileNotFoundError:
            continue
        except subprocess.TimeoutExpired:
            output = f"Timed out: {' '.join(cmd)}"
            used = " ".join(cmd)
            break
        used = " ".join(cmd)
        output = ((proc.stdout or "") + (proc.stderr or ""))[-8000:]
        # No tests collected is not a hard fail for empty suites, but treat exit 0 as pass
        if proc.returncode == 0:
            passed = True
            break
        # pytest exit code 5 = no tests collected
        if proc.returncode == 5:
            passed = False
            output = (output + "\n(no tests collected)").strip()
            break

    if used is None:
        output = "pytest not available in environment"
        passed = False

    retries = int(state.get("test_retries") or 0)
    if not passed:
        retries += 1

    thread_id = state.get("thread_id")
    if thread_id:
        write_artifact(
            thread_id,
            "test_results.json",
            {"command": used, "passed": passed, "output": output, "retries": retries},
        )

    updates: dict[str, Any] = {
        "tests_passed": passed,
        "test_output": output,
        "test_retries": retries,
        "status": "review" if not passed else "shipped",
    }
    if not passed and retries <= 2:
        notes = list(state.get("revision_notes") or [])
        notes.append(
            "Automated test run failed or found no passing tests. "
            "Add/fix tests under repo/ and ensure `pytest -q` passes.\n"
            f"Output:\n{output[:1500]}"
        )
        updates["revision_notes"] = notes
        updates["verdict"] = "fail"
        updates["status"] = "building"
        updates["pipeline_phase"] = "fix_loop"
    else:
        updates["pipeline_phase"] = "pr"
    return updates


def create_pr_node(state: dict[str, Any]) -> dict[str, Any]:
    thread_id = state.get("thread_id") or ""
    workspace = Path(state.get("workspace_root") or ".")
    repo = workspace / "repo"
    meta = load_issue_meta(thread_id) or {}
    owner = meta.get("repo", "").split("/")[0] if meta.get("repo") else ""
    name = meta.get("repo", "").split("/")[-1] if meta.get("repo") else ""
    number = int(meta.get("number") or 0)
    title = str(meta.get("title") or "Issue fix")
    issue_url = str(meta.get("url") or "")

    notes_path = workspace / "ISSUE_NOTES.md"
    if not notes_path.is_file() and (repo / "ISSUE_NOTES.md").is_file():
        notes_path = repo / "ISSUE_NOTES.md"
    summary = notes_path.read_text(encoding="utf-8") if notes_path.is_file() else (
        state.get("builder_summary") or ""
    )

    if not owner or not name or not number:
        result = {
            "ok": False,
            "error": "Missing github_issue.json metadata (owner/repo/number)",
        }
    else:
        ref = IssueRef(owner=owner, repo=name, number=number)
        body = build_pr_body(
            issue_url=issue_url or ref.url,
            issue_number=number,
            summary=summary,
            test_output=str(state.get("test_output") or ""),
            files_touched=list(state.get("files_touched") or []),
        )
        result = create_pull_request(
            repo_path=repo,
            ref=ref,
            title=title,
            body=body,
        )

    if thread_id:
        write_artifact(thread_id, "pull_request.json", result)

    return {
        "pr_url": result.get("pr_url"),
        "pr_number": result.get("pr_number"),
        "pr_result": result,
        "status": "shipped",
    }


def linkedin_announce_node(state: dict[str, Any]) -> dict[str, Any]:
    thread_id = state.get("thread_id") or ""
    workspace = Path(state.get("workspace_root") or ".")
    meta = load_issue_meta(thread_id) or {}
    notes_path = workspace / "ISSUE_NOTES.md"
    if not notes_path.is_file() and (workspace / "repo" / "ISSUE_NOTES.md").is_file():
        notes_path = workspace / "repo" / "ISSUE_NOTES.md"
    notes = notes_path.read_text(encoding="utf-8") if notes_path.is_file() else ""

    owner = ""
    name = ""
    if meta.get("repo") and "/" in str(meta["repo"]):
        owner, name = str(meta["repo"]).split("/", 1)
    number = int(meta.get("number") or 0)
    first_issue = bool(meta.get("is_first_issue"))
    project: dict[str, Any] = {}

    if owner and name and number:
        ref = IssueRef(owner=owner, repo=name, number=number)
        if "is_first_issue" not in meta:
            try:
                first_issue = is_first_issue(ref)
            except Exception:  # noqa: BLE001
                first_issue = number == 1
        if first_issue:
            try:
                project = fetch_repo_profile(ref)
            except Exception:  # noqa: BLE001
                project = {
                    "full_name": meta.get("repo"),
                    "description": "",
                    "html_url": f"https://github.com/{meta.get('repo')}",
                    "readme_excerpt": load_local_readme(workspace),
                    "topics": [],
                }
            if not project.get("readme_excerpt"):
                project["readme_excerpt"] = load_local_readme(workspace)

    system, human = build_linkedin_announce_messages(
        meta=meta,
        notes=notes,
        pr_url=state.get("pr_url"),
        tests_passed=state.get("tests_passed"),
        builder_summary=state.get("builder_summary"),
        first_issue=first_issue,
        project=project,
    )

    llm = get_chat_model("builder").with_structured_output(LinkedInAnnounceDraft)
    draft: LinkedInAnnounceDraft = llm.invoke(
        [SystemMessage(content=system), HumanMessage(content=human)]
    )

    tools = {t.name: t for t in make_linkedin_builder_tools(str(workspace))}
    suffix = "project-launch" if first_issue else "shipped"
    post_id = f"issue-{meta.get('number') or 'fix'}-{suffix}"
    body = draft.body
    if first_issue and project.get("html_url") and project["html_url"] not in body:
        body = f"{body.rstrip()}\n\nProject: {project['html_url']}"
    if state.get("pr_url"):
        body = f"{body.rstrip()}\n\nPR: {state.get('pr_url')}"
    write_result = tools["write_linkedin_post"].invoke(
        {
            "id": post_id,
            "format": "text",
            "hook": draft.hook,
            "body": body,
            "cta": draft.cta,
            "hashtags": draft.hashtags,
            "tone": draft.tone,
            "audience": draft.audience,
            "goal": (
                "introduce the project and first shipped milestone"
                if first_issue
                else "build-in-public announcement"
            ),
            "notes": (
                f"Auto-generated after first GitHub issue #{meta.get('number')}"
                if first_issue
                else f"Auto-generated after GitHub issue #{meta.get('number')}"
            ),
        }
    )
    tools["write_linkedin_campaign_readme"].invoke(
        {
            "title": (
                f"Launching {project.get('full_name') or meta.get('repo') or 'the project'}"
                if first_issue
                else f"Shipped: {meta.get('title') or 'issue fix'}"
            ),
            "brand": (meta.get("repo") or "").split("/")[0] if meta.get("repo") else "",
            "goal": "project + issue announcement" if first_issue else "announce engineering shipping",
            "audience": draft.audience,
            "posting_order": [post_id],
        }
    )

    package = {
        "post_id": post_id,
        "write_result": write_result,
        "hook": draft.hook,
        "pr_url": state.get("pr_url"),
        "issue_url": meta.get("url"),
        "is_first_issue": first_issue,
        "project": {
            "full_name": project.get("full_name"),
            "description": project.get("description"),
            "html_url": project.get("html_url"),
            "topics": project.get("topics"),
        }
        if project
        else {},
    }
    if thread_id:
        write_artifact(thread_id, "linkedin_announce.json", package)

    files = list(state.get("files_touched") or [])
    for path in (
        f"linkedin_posts/{post_id}/post.json",
        f"linkedin_posts/{post_id}/body.txt",
        "linkedin_posts/README.md",
    ):
        if path not in files:
            files.append(path)

    return {
        "linkedin_announce": package,
        "files_touched": files,
        "status": "shipped",
    }
