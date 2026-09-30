"""Optional DeepAgents builder backend."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentic_company.config import get_settings
from agentic_company.prompts import BUILDER_SYSTEM
from agentic_company.tools.filesystem import snapshot_workspace


def run_deepagents_builder(state: dict[str, Any]) -> dict[str, Any]:
    """Run DeepAgents against the same sandbox workspace.

    Falls back to native builder with an explanatory note if deepagents is unavailable.
    """
    try:
        from deepagents import create_deep_agent
        from deepagents.backends import FilesystemBackend
    except Exception as import_exc:  # noqa: BLE001
        from agentic_company.backends.native_builder import run_native_builder

        result = run_native_builder(state)
        result["builder_summary"] = (
            f"[deepagents unavailable: {import_exc}] fell back to native. "
            + result.get("builder_summary", "")
        )
        return result

    settings = get_settings()
    workspace = Path(state["workspace_root"]).resolve()
    before = {p.relative_to(workspace).as_posix() for p in workspace.rglob("*") if p.is_file()}

    notes = state.get("specialist_notes") or []
    note_text = "\n".join(f"- [{n.get('role')}]: {n.get('notes')}" for n in notes) or "(none)"
    revisions = state.get("revision_notes") or []
    rev_text = "\n".join(f"- {r}" for r in revisions) or "(none)"

    prompt = f"""Implement the approved plan inside the workspace.

Brief:
{state.get('brief', '')}

Plan:
{state.get('plan', '')}

Acceptance criteria:
{chr(10).join('- ' + c for c in (state.get('acceptance_criteria') or []))}

File outline:
{chr(10).join('- ' + p for p in (state.get('file_outline') or []))}

Specialist notes:
{note_text}

Revision notes:
{rev_text}

Create the files from the outline. Prefer tests. When done, summarize what you built.
"""

    try:
        agent = create_deep_agent(
            model=settings.builder_model,
            system_prompt=BUILDER_SYSTEM,
            backend=FilesystemBackend(root_dir=str(workspace), virtual_mode=True),
        )
        result = agent.invoke({"messages": [{"role": "user", "content": prompt}]})
    except Exception as run_exc:  # noqa: BLE001
        from agentic_company.backends.native_builder import run_native_builder

        fallback = run_native_builder(state)
        fallback["builder_summary"] = (
            f"[deepagents run failed: {run_exc}] fell back to native. "
            + fallback.get("builder_summary", "")
        )
        return fallback

    after = {p.relative_to(workspace).as_posix() for p in workspace.rglob("*") if p.is_file()}
    touched = sorted(after - before) or sorted(after)

    summary = ""
    if isinstance(result, dict):
        messages = result.get("messages") or []
        if messages:
            last = messages[-1]
            summary = getattr(last, "content", None) or str(last)
        else:
            summary = str(result)[:4000]
    else:
        summary = str(result)[:4000]

    return {
        "builder_messages": [
            {"role": "system", "content": "deepagents FilesystemBackend"},
            {"role": "assistant", "content": str(summary)[:4000]},
        ],
        "files_touched": touched,
        "builder_summary": str(summary)[:4000]
        or f"DeepAgents finished. Snapshot:\n{snapshot_workspace(workspace)}",
        "status": "review",
    }
