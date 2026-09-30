"""Builder dispatch node."""

from __future__ import annotations

from typing import Any

from agentic_company.backends.deepagents_builder import run_deepagents_builder
from agentic_company.backends.native_builder import run_native_builder
from agentic_company.config import ensure_run_dirs, get_settings


def builder_node(state: dict[str, Any]) -> dict[str, Any]:
    thread_id = state["thread_id"]
    workspace, _ = ensure_run_dirs(thread_id)
    backend = (state.get("builder_backend") or get_settings().builder_backend).lower()
    enriched = {
        **state,
        "workspace_root": str(workspace),
        "builder_backend": backend,
        "status": "building",
    }
    if backend == "deepagents":
        result = run_deepagents_builder(enriched)
    else:
        result = run_native_builder(enriched)
    result["workspace_root"] = str(workspace)
    result["builder_backend"] = backend
    return result
