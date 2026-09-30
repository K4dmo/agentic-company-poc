"""Memory write helpers for completed runs."""

from __future__ import annotations

from typing import Any

from agentic_company.memory.store import get_memory_store


def write_run_memory(state: dict[str, Any]) -> None:
    thread_id = state.get("thread_id") or "unknown"
    brief = state.get("brief") or ""
    plan = state.get("plan") or ""
    verdict = state.get("verdict") or state.get("status") or ""
    critique = state.get("critique") or {}
    summary = critique.get("summary") if isinstance(critique, dict) else str(critique)
    text = (
        f"Brief: {brief}\n"
        f"Plan: {plan}\n"
        f"Verdict: {verdict}\n"
        f"Critique: {summary}\n"
        f"Status: {state.get('status')}"
    )
    get_memory_store().upsert(
        doc_id=thread_id,
        text=text,
        metadata={
            "thread_id": thread_id,
            "verdict": str(verdict),
            "status": str(state.get("status") or ""),
            "brief": brief[:500],
        },
    )
