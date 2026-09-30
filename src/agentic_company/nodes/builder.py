"""Builder dispatch node."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from agentic_company.backends.deepagents_builder import run_deepagents_builder
from agentic_company.backends.native_builder import run_native_builder
from agentic_company.config import ensure_run_dirs, get_settings
from agentic_company.tools.builder_toolkit import detect_deliverable_kind


def _hydrate_workspace(state: dict[str, Any], workspace: Path) -> dict[str, Any]:
    """Copy issue brief into workspace and normalize deliverable_kind before building."""
    thread_id = state.get("thread_id")
    updates: dict[str, Any] = {}
    kind = detect_deliverable_kind(state)
    updates["deliverable_kind"] = kind

    if thread_id:
        artifacts = get_settings().artifacts_dir(thread_id)
        issue_md = artifacts / "github_issue.md"
        if issue_md.is_file():
            target = workspace / "ISSUE.md"
            if not target.exists():
                shutil.copyfile(issue_md, target)
            updates["deliverable_kind"] = "github_issue"
            kind = "github_issue"
    return {**state, **updates, "deliverable_kind": kind}


def builder_node(state: dict[str, Any]) -> dict[str, Any]:
    thread_id = state["thread_id"]
    workspace, _ = ensure_run_dirs(thread_id)
    backend = (state.get("builder_backend") or get_settings().builder_backend).lower()
    enriched = _hydrate_workspace(
        {
            **state,
            "workspace_root": str(workspace),
            "builder_backend": backend,
            "status": "building",
        },
        workspace,
    )
    if backend == "deepagents":
        result = run_deepagents_builder(enriched)
    else:
        result = run_native_builder(enriched)
    result["workspace_root"] = str(workspace)
    result["builder_backend"] = backend
    if "deliverable_kind" not in result:
        result["deliverable_kind"] = enriched.get("deliverable_kind")
    return result
