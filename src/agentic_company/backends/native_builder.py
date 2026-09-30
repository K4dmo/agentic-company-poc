"""Native LangGraph ReAct builder backend."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from agentic_company.config import get_settings
from agentic_company.llm import get_chat_model
from agentic_company.prompts import BUILDER_SYSTEM
from agentic_company.tools.builder_toolkit import detect_deliverable_kind, make_builder_tools


class SignalDoneArgs(BaseModel):
    summary: str = Field(description="What was implemented")
    files_touched: list[str] = Field(default_factory=list, description="Relative paths written/edited")


def _signal_done_tool() -> StructuredTool:
    def signal_done(summary: str, files_touched: list[str] | None = None) -> str:
        return "DONE"

    return StructuredTool.from_function(
        signal_done,
        name="signal_done",
        description="Call when implementation is complete",
        args_schema=SignalDoneArgs,
    )


def _build_user_prompt(state: dict[str, Any], kind: str) -> str:
    notes = state.get("specialist_notes") or []
    note_text = "\n".join(
        f"- [{n.get('role')}]: {n.get('notes')}" for n in notes
    ) or "(none)"
    revisions = state.get("revision_notes") or []
    rev_text = "\n".join(f"- {r}" for r in revisions) or "(none)"
    criteria = state.get("acceptance_criteria") or []
    crit_text = "\n".join(f"- {c}" for c in criteria)
    outline = state.get("file_outline") or []
    outline_text = "\n".join(f"- {p}" for p in outline)

    domain_hint = ""
    if kind == "github_issue":
        domain_hint = """
GitHub issue mode:
1) Call load_issue_context
2) Explore with repo_tree / read_file (prefer paths under repo/)
3) Implement the fix with write_file/edit_file
4) Add/update tests, then run_tests (pytest must pass)
5) Use git_status/git_diff
6) Call write_issue_notes then signal_done
(After human ship approval: automated verify_tests → create_pr → linkedin_announce → linkedin_gate → linkedin_publish)
"""
    elif kind == "instagram_posts":
        domain_hint = """
Instagram mode:
1) Prefer write_instagram_post for each post (creates validated package files)
2) Call write_campaign_readme for posts/README.md
3) Use list_instagram_posts to verify
4) Call signal_done
"""
    elif kind == "linkedin_posts":
        domain_hint = """
LinkedIn mode:
1) Prefer write_linkedin_post for each post (creates validated package files)
2) Call write_linkedin_campaign_readme for linkedin_posts/README.md
3) Use list_linkedin_posts to verify
4) Call signal_done
"""
    elif kind == "mixed":
        domain_hint = (
            "Mixed mode: use GitHub tools and/or write_instagram_post / "
            "write_linkedin_post as the plan requires.\n"
        )

    return f"""Brief:
{state.get('brief', '')}

Deliverable kind: {kind}
{domain_hint}
Plan:
{state.get('plan', '')}

Acceptance criteria:
{crit_text}

File outline:
{outline_text}

Specialist notes:
{note_text}

Revision notes from critic/human:
{rev_text}

Workspace root: {state.get('workspace_root')}
Implement now. Use tools. Call signal_done when finished.
"""


def run_native_builder(state: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    workspace = state["workspace_root"]
    kind = detect_deliverable_kind(state)
    tools = make_builder_tools(
        workspace,
        kind,
        thread_id=state.get("thread_id"),
        signal_done_tool=_signal_done_tool(),
    )
    tool_map = {t.name: t for t in tools}

    llm = get_chat_model("builder").bind_tools(tools)
    messages: list[Any] = [
        SystemMessage(content=BUILDER_SYSTEM),
        HumanMessage(content=_build_user_prompt(state, kind)),
    ]

    files_touched: list[str] = []
    summary = ""
    transcript: list[dict[str, Any]] = []
    done = False

    for _ in range(settings.builder_max_turns):
        response: AIMessage = llm.invoke(messages)
        messages.append(response)
        transcript.append({"role": "assistant", "content": str(response.content)})

        if not response.tool_calls:
            summary = summary or str(response.content)[:2000]
            break

        for call in response.tool_calls:
            name = call["name"]
            args = call.get("args") or {}
            tool = tool_map.get(name)
            if tool is None:
                result = f"Unknown tool: {name}"
            else:
                try:
                    result = tool.invoke(args)
                except Exception as exc:  # noqa: BLE001
                    result = f"Tool error: {exc}"

            if name in {"write_file", "edit_file"} and "path" in args:
                path = args["path"]
                if path not in files_touched:
                    files_touched.append(path)
            if name == "write_instagram_post" and args.get("id"):
                path = f"posts/{args['id']}/post.json"
                if path not in files_touched:
                    files_touched.append(path)
            if name == "write_campaign_readme":
                if "posts/README.md" not in files_touched:
                    files_touched.append("posts/README.md")
            if name == "write_linkedin_post" and args.get("id"):
                path = f"linkedin_posts/{args['id']}/post.json"
                if path not in files_touched:
                    files_touched.append(path)
            if name == "write_linkedin_campaign_readme":
                if "linkedin_posts/README.md" not in files_touched:
                    files_touched.append("linkedin_posts/README.md")
            if name == "write_issue_notes":
                if "ISSUE_NOTES.md" not in files_touched:
                    files_touched.append("ISSUE_NOTES.md")
            if name == "signal_done":
                summary = args.get("summary") or summary
                for path in args.get("files_touched") or []:
                    if path not in files_touched:
                        files_touched.append(path)
                done = True
                result = "acknowledged"

            messages.append(
                ToolMessage(content=str(result), tool_call_id=call["id"])
            )
            transcript.append({"role": "tool", "name": name, "content": str(result)[:4000]})

        if done:
            break

    return {
        "builder_messages": transcript[-30:],
        "files_touched": files_touched,
        "builder_summary": summary or "Builder finished without explicit summary",
        "deliverable_kind": kind,
        "status": "review",
    }
