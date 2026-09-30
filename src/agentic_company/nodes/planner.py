"""Planner node — structured plan output."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agentic_company.llm import get_chat_model
from agentic_company.persistence import write_artifact
from agentic_company.prompts import PLANNER_SYSTEM
from agentic_company.roles.registry import describe_registry, normalize_hired
from agentic_company.schemas import PlanOutput


def planner_node(state: dict[str, Any]) -> dict[str, Any]:
    llm = get_chat_model("planner").with_structured_output(PlanOutput)

    memory_hits = state.get("memory_hits") or []
    memory_text = "\n\n".join(
        f"[{h.get('id')}]\n{h.get('text')}" for h in memory_hits
    ) or "(no prior memory)"

    human = f"""Brief:
{state.get('brief', '')}

Prior company memory:
{memory_text}

Available specialists:
{describe_registry()}
"""
    result: PlanOutput = llm.invoke(
        [SystemMessage(content=PLANNER_SYSTEM), HumanMessage(content=human)]
    )
    hired = normalize_hired(list(result.hired_specialists))
    payload = {
        "plan": result.plan,
        "acceptance_criteria": result.acceptance_criteria,
        "file_outline": result.file_outline,
        "hired_specialists": hired,
        "deliverable_kind": result.deliverable_kind,
        "status": "awaiting_human",
        # reset specialist notes on replan
        "specialist_notes": [],
    }
    thread_id = state.get("thread_id")
    if thread_id:
        write_artifact(
            thread_id,
            "plan.json",
            {
                "plan": result.plan,
                "acceptance_criteria": result.acceptance_criteria,
                "file_outline": result.file_outline,
                "hired_specialists": hired,
                "deliverable_kind": result.deliverable_kind,
            },
        )
    return payload
