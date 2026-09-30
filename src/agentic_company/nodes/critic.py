"""Critic node — structured review of workspace."""

from __future__ import annotations

from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage

from agentic_company.config import get_settings
from agentic_company.persistence import write_artifact
from agentic_company.prompts import CRITIC_SYSTEM
from agentic_company.schemas import CritiqueOutput
from agentic_company.tools.filesystem import read_workspace_bundle, snapshot_workspace


def critic_node(state: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    llm = init_chat_model(settings.critic_model).with_structured_output(CritiqueOutput)
    workspace = state.get("workspace_root") or ""
    listing = snapshot_workspace(workspace)
    bundle = read_workspace_bundle(workspace)

    criteria = state.get("acceptance_criteria") or []
    human = f"""Brief:
{state.get('brief', '')}

Plan:
{state.get('plan', '')}

Acceptance criteria:
{chr(10).join('- ' + c for c in criteria)}

Builder summary:
{state.get('builder_summary', '')}

Files touched:
{state.get('files_touched', [])}

Workspace listing:
{listing}

Workspace contents:
{bundle}
"""
    result: CritiqueOutput = llm.invoke(
        [SystemMessage(content=CRITIC_SYSTEM), HumanMessage(content=human)]
    )
    critique = result.model_dump()
    retries = int(state.get("retries") or 0)
    if result.verdict == "fail":
        retries += 1

    thread_id = state.get("thread_id")
    if thread_id:
        write_artifact(thread_id, "critique.json", critique)

    status = "awaiting_human" if result.verdict == "pass" else "review"
    if result.verdict == "fail" and retries >= settings.max_builder_retries:
        status = "failed"

    return {
        "critique": critique,
        "verdict": result.verdict,
        "revision_notes": result.revision_notes,
        "retries": retries,
        "status": status,
        "critique_history": [critique],
    }
