"""Memory recall / write graph nodes."""

from __future__ import annotations

from typing import Any

from agentic_company.memory.recall import recall_for_brief
from agentic_company.memory.write import write_run_memory
from agentic_company.persistence import write_artifact


def memory_recall_node(state: dict[str, Any]) -> dict[str, Any]:
    hits = recall_for_brief(state.get("brief") or "")
    return {"memory_hits": hits, "status": "planning"}


def memory_write_node(state: dict[str, Any]) -> dict[str, Any]:
    write_run_memory(state)
    thread_id = state.get("thread_id")
    if thread_id:
        write_artifact(
            thread_id,
            "summary.json",
            {
                "thread_id": thread_id,
                "brief": state.get("brief"),
                "status": state.get("status"),
                "verdict": state.get("verdict"),
                "plan": state.get("plan"),
                "files_touched": state.get("files_touched"),
                "builder_summary": state.get("builder_summary"),
                "critique": state.get("critique"),
                "retries": state.get("retries"),
                "builder_backend": state.get("builder_backend"),
            },
        )
    return {}
