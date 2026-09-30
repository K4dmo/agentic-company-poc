"""Optional DeepAgents builder backend."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentic_company.llm import get_chat_model
from agentic_company.prompts import BUILDER_SYSTEM
from agentic_company.tools.builder_toolkit import detect_deliverable_kind, make_builder_tools
from agentic_company.tools.filesystem import snapshot_workspace


def run_deepagents_builder(state: dict[str, Any]) -> dict[str, Any]:
    """Run DeepAgents against the same sandbox workspace.

    Falls back to native builder with an explanatory note if deepagents is unavailable.
    """
    try:
        from deepagents import create_deep_agent
        from deepagents.backends import FilesystemBackend
    except Exception as import_exc:  # noqa: BLE001
        from agentic_company.backends.native_builder import run_native_builder

        result = run_native_builder(state)
        result["builder_summary"] = (
            f"[deepagents unavailable: {import_exc}] fell back to native. "
            + result.get("builder_summary", "")
        )
        return result

    workspace = Path(state["workspace_root"]).resolve()
    kind = detect_deliverable_kind(state)
    before = {p.relative_to(workspace).as_posix() for p in workspace.rglob("*") if p.is_file()}

    notes = state.get("specialist_notes") or []
    note_text = "\n".join(f"- [{n.get('role')}]: {n.get('notes')}" for n in notes) or "(none)"
    revisions = state.get("revision_notes") or []
    rev_text = "\n".join(f"- {r}" for r in revisions) or "(none)"

    domain_hint = ""
    if kind == "github_issue":
        domain_hint = (
            "Use load_issue_context, repo_tree, git_status/git_diff, implement under repo/, "
            "then write_issue_notes."
        )
    elif kind == "instagram_posts":
        domain_hint = (
            "Use write_instagram_post for each post and write_campaign_readme for posts/README.md."
        )
    elif kind == "linkedin_posts":
        domain_hint = (
            "Use write_linkedin_post for each post and write_linkedin_campaign_readme "
            "for linkedin_posts/README.md."
        )

    prompt = f"""Implement the approved plan inside the workspace.

Brief:
{state.get('brief', '')}

Deliverable kind: {kind}
{domain_hint}

Plan:
{state.get('plan', '')}

Acceptance criteria:
{chr(10).join('- ' + c for c in (state.get('acceptance_criteria') or []))}

File outline:
{chr(10).join('- ' + p for p in (state.get('file_outline') or []))}

Specialist notes:
{note_text}

Revision notes:
{rev_text}

Create the files from the outline. Prefer tests for software; for Instagram use write_instagram_post; for LinkedIn use write_linkedin_post; for GitHub issues prefer repo/. When done, summarize what you built.
"""

    domain_tools = make_builder_tools(
        str(workspace),
        kind,
        thread_id=state.get("thread_id"),
    )
    # DeepAgents already has FS tools; keep domain-specific extras only
    extra_names = {
        "load_issue_context",
        "repo_tree",
        "git_status",
        "git_diff",
        "write_issue_notes",
        "write_instagram_post",
        "write_campaign_readme",
        "list_instagram_posts",
        "write_linkedin_post",
        "write_linkedin_campaign_readme",
        "list_linkedin_posts",
        "run_tests",
    }
    extras = [t for t in domain_tools if t.name in extra_names]

    try:
        agent = create_deep_agent(
            model=get_chat_model("builder"),
            system_prompt=BUILDER_SYSTEM,
            tools=extras or None,
            backend=FilesystemBackend(root_dir=str(workspace), virtual_mode=True),
        )
        result = agent.invoke({"messages": [{"role": "user", "content": prompt}]})
    except Exception as run_exc:  # noqa: BLE001
        from agentic_company.backends.native_builder import run_native_builder

        fallback = run_native_builder(state)
        fallback["builder_summary"] = (
            f"[deepagents run failed: {run_exc}] fell back to native. "
            + fallback.get("builder_summary", "")
        )
        return fallback

    after = {p.relative_to(workspace).as_posix() for p in workspace.rglob("*") if p.is_file()}
    touched = sorted(after - before) or sorted(after)

    summary = ""
    if isinstance(result, dict):
        messages = result.get("messages") or []
        if messages:
            last = messages[-1]
            summary = getattr(last, "content", None) or str(last)
        else:
            summary = str(result)[:4000]
    else:
        summary = str(result)[:4000]

    return {
        "builder_messages": [
            {"role": "system", "content": f"deepagents kind={kind}"},
            {"role": "assistant", "content": str(summary)[:4000]},
        ],
        "files_touched": touched,
        "builder_summary": str(summary)[:4000]
        or f"DeepAgents finished. Snapshot:\n{snapshot_workspace(workspace)}",
        "deliverable_kind": kind,
        "status": "review",
    }
