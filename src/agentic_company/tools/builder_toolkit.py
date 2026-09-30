"""Assemble Builder toolkits by deliverable kind."""

from __future__ import annotations

from pathlib import Path

from langchain_core.tools import BaseTool

from agentic_company.tools.filesystem import make_filesystem_tools
from agentic_company.tools.github_builder import make_github_builder_tools
from agentic_company.tools.instagram_builder import make_instagram_builder_tools
from agentic_company.tools.linkedin_builder import make_linkedin_builder_tools
from agentic_company.tools.testing import make_testing_tools

KNOWN_KINDS = {
    "software",
    "instagram_posts",
    "linkedin_posts",
    "github_issue",
    "mixed",
}


def detect_deliverable_kind(state: dict) -> str:
    kind = (state.get("deliverable_kind") or "").strip().lower()
    if kind in KNOWN_KINDS:
        return kind
    brief = (state.get("brief") or "").lower()
    if "github.com/" in brief and "/issues/" in brief:
        return "github_issue"
    has_ig = "instagram" in brief or "reel script" in brief
    has_li = "linkedin" in brief
    if has_ig and has_li:
        return "mixed"
    if has_li:
        return "linkedin_posts"
    if has_ig or ("carousel" in brief and "linkedin" not in brief):
        return "instagram_posts"
    workspace = Path(state.get("workspace_root") or ".")
    if (workspace / "repo").is_dir():
        return "github_issue"
    if (workspace / "linkedin_posts").is_dir():
        return "linkedin_posts"
    if (workspace / "posts").is_dir():
        return "instagram_posts"
    return "software"


def make_builder_tools(
    workspace_root: str,
    deliverable_kind: str,
    *,
    thread_id: str | None = None,
    signal_done_tool: BaseTool | None = None,
) -> list[BaseTool]:
    tools: list[BaseTool] = []
    tools.extend(make_filesystem_tools(workspace_root))
    tools.extend(make_testing_tools(workspace_root))

    kind = deliverable_kind.lower()
    if kind in {"github_issue", "mixed", "software"}:
        if kind == "github_issue" or (Path(workspace_root) / "repo").is_dir() or kind == "mixed":
            tools.extend(make_github_builder_tools(workspace_root, thread_id=thread_id))
    if kind in {"instagram_posts", "mixed"}:
        tools.extend(make_instagram_builder_tools(workspace_root))
    if kind in {"linkedin_posts", "mixed"}:
        tools.extend(make_linkedin_builder_tools(workspace_root))

    if kind == "software" and thread_id:
        from agentic_company.config import get_settings

        if (get_settings().artifacts_dir(thread_id) / "github_issue.md").exists():
            tools.extend(make_github_builder_tools(workspace_root, thread_id=thread_id))

    if signal_done_tool is not None:
        tools.append(signal_done_tool)
    return tools
