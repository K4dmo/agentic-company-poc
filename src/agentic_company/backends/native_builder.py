"""Native LangGraph ReAct builder backend."""

from __future__ import annotations

from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from agentic_company.config import get_settings
from agentic_company.prompts import BUILDER_SYSTEM
from agentic_company.tools.filesystem import make_filesystem_tools
from agentic_company.tools.testing import make_testing_tools


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


def _build_user_prompt(state: dict[str, Any]) -> str:
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
    return f"""Brief:
{state.get('brief', '')}

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
    tools = make_filesystem_tools(workspace) + make_testing_tools(workspace) + [_signal_done_tool()]
    tool_map = {t.name: t for t in tools}

    llm = init_chat_model(settings.builder_model).bind_tools(tools)
    messages: list[Any] = [
        SystemMessage(content=BUILDER_SYSTEM),
        HumanMessage(content=_build_user_prompt(state)),
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
            # Model stopped without tools — treat content as summary if any files exist
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
        "status": "review",
    }
