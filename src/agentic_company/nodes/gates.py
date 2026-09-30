"""Human-in-the-loop gate nodes."""

from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from agentic_company.config import get_settings


def _auto_decision(kind: str) -> dict[str, Any]:
    if kind == "plan":
        return {"action": "approve"}
    return {"action": "approve"}


def plan_gate_node(state: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    payload = {
        "type": "plan_approval",
        "brief": state.get("brief"),
        "plan": state.get("plan"),
        "acceptance_criteria": state.get("acceptance_criteria"),
        "file_outline": state.get("file_outline"),
        "hired_specialists": state.get("hired_specialists"),
        "thread_id": state.get("thread_id"),
    }
    if settings.eval_mode:
        decision = _auto_decision("plan")
    else:
        decision = interrupt(payload)

    action = (decision or {}).get("action", "approve")
    if action == "abort":
        return {"abort": True, "status": "aborted", "human_feedback": decision}
    if action == "revise":
        brief = (decision or {}).get("brief") or state.get("brief")
        return {
            "brief": brief,
            "abort": False,
            "status": "planning",
            "human_feedback": decision,
        }
    # Clear revise flag so later routers do not loop
    return {
        "abort": False,
        "status": "building",
        "human_feedback": {"action": "approve"},
    }


def ship_gate_node(state: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    payload = {
        "type": "ship_approval",
        "brief": state.get("brief"),
        "files_touched": state.get("files_touched"),
        "builder_summary": state.get("builder_summary"),
        "critique": state.get("critique"),
        "thread_id": state.get("thread_id"),
    }
    if settings.eval_mode:
        decision = _auto_decision("ship")
    else:
        decision = interrupt(payload)

    action = (decision or {}).get("action", "approve")
    if action == "abort":
        return {"abort": True, "status": "aborted", "human_feedback": decision}
    if action == "revise":
        notes = (decision or {}).get("revision_notes") or "Human requested changes"
        existing = list(state.get("revision_notes") or [])
        existing.append(str(notes))
        return {
            "revision_notes": existing,
            "status": "building",
            "human_feedback": decision,
            "verdict": "fail",  # route back to builder via ship router
        }
    return {
        "status": "shipped",
        "human_feedback": decision,
    }
