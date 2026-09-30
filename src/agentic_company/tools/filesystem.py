"""Sandboxed filesystem tools — all paths must stay under workspace_root."""

from __future__ import annotations

from pathlib import Path

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field


class PathError(ValueError):
    pass


def resolve_in_workspace(workspace_root: str | Path, relative: str) -> Path:
    root = Path(workspace_root).resolve()
    target = (root / (relative or ".")).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise PathError(f"Path escapes workspace: {relative!r}") from exc
    return target


def make_filesystem_tools(workspace_root: str) -> list[StructuredTool]:
    root = Path(workspace_root).resolve()

    class RelPath(BaseModel):
        path: str = Field(default=".", description="Relative path inside the workspace")

    class ReadArgs(BaseModel):
        path: str = Field(description="Relative file path to read")

    class WriteArgs(BaseModel):
        path: str = Field(description="Relative file path to write")
        content: str = Field(description="Full file contents")

    class EditArgs(BaseModel):
        path: str = Field(description="Relative file path to edit")
        old: str = Field(description="Exact text to replace")
        new: str = Field(description="Replacement text")

    def list_dir(path: str = ".") -> str:
        target = resolve_in_workspace(root, path)
        if not target.exists():
            return f"Not found: {path}"
        if target.is_file():
            return f"File: {path}"
        entries = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        lines = []
        for entry in entries:
            rel = entry.relative_to(root).as_posix()
            suffix = "/" if entry.is_dir() else ""
            lines.append(f"{rel}{suffix}")
        return "\n".join(lines) if lines else "(empty)"

    def read_file(path: str) -> str:
        target = resolve_in_workspace(root, path)
        if not target.is_file():
            return f"Not a file: {path}"
        text = target.read_text(encoding="utf-8")
        if len(text) > 80_000:
            return text[:80_000] + "\n...[truncated]..."
        return text

    def write_file(path: str, content: str) -> str:
        target = resolve_in_workspace(root, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Wrote {path} ({len(content)} bytes)"

    def edit_file(path: str, old: str, new: str) -> str:
        target = resolve_in_workspace(root, path)
        if not target.is_file():
            return f"Not a file: {path}"
        text = target.read_text(encoding="utf-8")
        if old not in text:
            return f"old text not found in {path}"
        count = text.count(old)
        target.write_text(text.replace(old, new, 1), encoding="utf-8")
        return f"Edited {path} (1 of {count} occurrence(s))"

    return [
        StructuredTool.from_function(
            list_dir,
            name="list_dir",
            description="List files and directories under a relative workspace path",
            args_schema=RelPath,
        ),
        StructuredTool.from_function(
            read_file,
            name="read_file",
            description="Read a text file from the workspace",
            args_schema=ReadArgs,
        ),
        StructuredTool.from_function(
            write_file,
            name="write_file",
            description="Create or overwrite a text file in the workspace",
            args_schema=WriteArgs,
        ),
        StructuredTool.from_function(
            edit_file,
            name="edit_file",
            description="Replace the first occurrence of old with new in a file",
            args_schema=EditArgs,
        ),
    ]


def snapshot_workspace(workspace_root: str | Path, limit: int = 40) -> str:
    root = Path(workspace_root).resolve()
    if not root.exists():
        return "(workspace missing)"
    files = [p for p in root.rglob("*") if p.is_file()]
    files.sort()
    lines = []
    for path in files[:limit]:
        rel = path.relative_to(root).as_posix()
        try:
            size = path.stat().st_size
        except OSError:
            size = -1
        lines.append(f"{rel} ({size} bytes)")
    if len(files) > limit:
        lines.append(f"... and {len(files) - limit} more")
    return "\n".join(lines) if lines else "(empty workspace)"


def read_workspace_bundle(workspace_root: str | Path, max_files: int = 20, max_chars: int = 60_000) -> str:
    root = Path(workspace_root).resolve()
    if not root.exists():
        return "(workspace missing)"
    parts: list[str] = []
    used = 0
    files = [p for p in root.rglob("*") if p.is_file()]
    files.sort()
    for path in files[:max_files]:
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            parts.append(f"## {rel}\n(unreadable: {exc})")
            continue
        chunk = f"## {rel}\n{text}"
        if used + len(chunk) > max_chars:
            parts.append(f"## {rel}\n(truncated; size limit)")
            break
        parts.append(chunk)
        used += len(chunk)
    return "\n\n".join(parts) if parts else "(empty workspace)"
