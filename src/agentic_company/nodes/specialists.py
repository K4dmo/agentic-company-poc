"""Dynamic specialist hiring — allowlisted roles only."""

from __future__ import annotations

from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage

from agentic_company.config import get_settings
from agentic_company.prompts import SPECIALIST_WRAPPER
from agentic_company.roles.prompts import specialist_focus, specialist_title
from agentic_company.roles.registry import normalize_hired
from agentic_company.schemas import SpecialistOutput


def specialists_node(state: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    hired = normalize_hired(list(state.get("hired_specialists") or []))
    if not hired:
        return {"specialist_notes": []}

    llm = init_chat_model(settings.specialist_model).with_structured_output(SpecialistOutput)
    notes: list[dict[str, Any]] = []

    for role in hired:
        system = SPECIALIST_WRAPPER.format(role_title=specialist_title(role))
        system += f"\nFocus: {specialist_focus(role)}"
        human = f"""Brief:
{state.get('brief', '')}

Plan:
{state.get('plan', '')}

Acceptance criteria:
{state.get('acceptance_criteria', [])}

File outline:
{state.get('file_outline', [])}

Produce notes for role={role}.
"""
        result: SpecialistOutput = llm.invoke(
            [SystemMessage(content=system), HumanMessage(content=human)]
        )
        notes.append(result.model_dump())

    return {"specialist_notes": notes}
