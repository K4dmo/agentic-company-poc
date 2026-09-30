"""Checkpoints and on-disk artifact helpers."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver

from agentic_company.config import ensure_run_dirs, get_settings

_checkpointer: SqliteSaver | None = None
_conn: sqlite3.Connection | None = None


def get_checkpointer() -> SqliteSaver:
    global _checkpointer, _conn
    if _checkpointer is not None:
        return _checkpointer
    settings = get_settings()
    settings.runs_dir.mkdir(parents=True, exist_ok=True)
    _conn = sqlite3.connect(str(settings.checkpoints_db), check_same_thread=False)
    _checkpointer = SqliteSaver(_conn)
    if hasattr(_checkpointer, "setup"):
        _checkpointer.setup()
    return _checkpointer


def write_artifact(thread_id: str, name: str, payload: Any) -> Path:
    _, artifacts = ensure_run_dirs(thread_id)
    path = artifacts / name
    if isinstance(payload, (dict, list)):
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        path.write_text(str(payload), encoding="utf-8")
    return path


def list_runs() -> list[dict[str, Any]]:
    settings = get_settings()
    if not settings.runs_dir.exists():
        return []
    runs: list[dict[str, Any]] = []
    for path in sorted(settings.runs_dir.iterdir(), reverse=True):
        if not path.is_dir() or path.name in {"memory"}:
            continue
        if path.name.endswith(".db"):
            continue
        meta_path = path / "artifacts" / "summary.json"
        meta: dict[str, Any] = {"thread_id": path.name}
        if meta_path.exists():
            try:
                meta.update(json.loads(meta_path.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                pass
        runs.append(meta)
    return runs


def load_run_summary(thread_id: str) -> dict[str, Any]:
    settings = get_settings()
    artifacts = settings.artifacts_dir(thread_id)
    summary: dict[str, Any] = {"thread_id": thread_id}
    for name in ("summary.json", "plan.json", "critique.json"):
        path = artifacts / name
        if path.exists():
            try:
                summary[name.replace(".json", "")] = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                summary[name.replace(".json", "")] = path.read_text(encoding="utf-8")
    workspace = settings.workspace_dir(thread_id)
    if workspace.exists():
        summary["files"] = [
            p.relative_to(workspace).as_posix()
            for p in sorted(workspace.rglob("*"))
            if p.is_file()
        ]
    return summary
