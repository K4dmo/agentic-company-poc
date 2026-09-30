"""Builder tools specialized for GitHub issue implementation."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from agentic_company.config import get_settings
from agentic_company.tools.filesystem import resolve_in_workspace


def _repo_root(workspace_root: str | Path) -> Path | None:
    root = Path(workspace_root).resolve()
    candidate = root / "repo"
    return candidate if candidate.is_dir() else None


def make_github_builder_tools(workspace_root: str, thread_id: str | None = None) -> list[StructuredTool]:
    root = Path(workspace_root).resolve()
    settings = get_settings()

    class Empty(BaseModel):
        pass

    class RelPath(BaseModel):
        path: str = Field(
            default=".",
            description="Path relative to workspace/repo/ when cloned, else workspace",
        )

    class NotesArgs(BaseModel):
        summary: str = Field(description="What changed")
        verification: str = Field(description="How to verify the fix")
        files_changed: list[str] = Field(default_factory=list)

    def load_issue_context() -> str:
        parts: list[str] = []
        if thread_id:
            artifacts = settings.artifacts_dir(thread_id)
            for name in ("github_issue.md", "github_issue.json"):
                path = artifacts / name
                if not path.is_file():
                    continue
                text = path.read_text(encoding="utf-8")
                if name.endswith(".json"):
                    try:
                        text = json.dumps(json.loads(text), indent=2)[:12_000]
                    except json.JSONDecodeError:
                        pass
                parts.append(f"## {name}\n{text[:12_000]}")
        workspace_issue = root / "ISSUE.md"
        if workspace_issue.is_file():
            parts.append(f"## ISSUE.md\n{workspace_issue.read_text(encoding='utf-8')[:8_000]}")
        return "\n\n".join(parts) if parts else "No GitHub issue artifacts found for this run."

    def repo_tree(path: str = ".") -> str:
        repo = _repo_root(root)
        base = repo if repo else root
        rel = path if path not in {"", "."} else "."
        # Expose as workspace-relative for resolve when under repo/
        if repo:
            ws_rel = "repo" if rel == "." else f"repo/{rel.lstrip('./')}"
            target = resolve_in_workspace(root, ws_rel)
        else:
            target = resolve_in_workspace(root, rel)
        if not target.exists():
            return f"Not found: {path}"
        if target.is_file():
            return f"File: {path}"
        lines: list[str] = []
        for entry in sorted(target.rglob("*")):
            if not entry.is_file():
                continue
            if ".git" in entry.parts:
                continue
            lines.append(entry.relative_to(base).as_posix())
            if len(lines) >= 200:
                lines.append("... truncated ...")
                break
        return "\n".join(lines) if lines else "(empty)"

    def git_status() -> str:
        repo = _repo_root(root)
        if not repo:
            return "No repo/ clone in workspace. Re-run with --clone or implement at workspace root."
        try:
            proc = subprocess.run(
                ["git", "status", "--short"],
                cwd=str(repo),
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            out = (proc.stdout or "") + (proc.stderr or "")
            return out.strip() or "(clean)"
        except Exception as exc:  # noqa: BLE001
            return f"git status failed: {exc}"

    def git_diff() -> str:
        repo = _repo_root(root)
        if not repo:
            return "No repo/ clone in workspace."
        try:
            proc = subprocess.run(
                ["git", "diff", "--", "."],
                cwd=str(repo),
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            out = proc.stdout or ""
            if len(out) > 30_000:
                out = out[:30_000] + "\n...[truncated]..."
            return out.strip() or "(no unstaged diff)"
        except Exception as exc:  # noqa: BLE001
            return f"git diff failed: {exc}"

    def write_issue_notes(summary: str, verification: str, files_changed: list[str] | None = None) -> str:
        files_changed = files_changed or []
        body = (
            f"# Issue implementation notes\n\n"
            f"## Summary\n{summary.strip()}\n\n"
            f"## Verification\n{verification.strip()}\n\n"
            f"## Files changed\n"
            + ("\n".join(f"- {p}" for p in files_changed) if files_changed else "- (none listed)")
            + "\n"
        )
        targets = [root / "ISSUE_NOTES.md"]
        repo = _repo_root(root)
        if repo:
            targets.append(repo / "ISSUE_NOTES.md")
        for path in targets:
            path.write_text(body, encoding="utf-8")
        return f"Wrote ISSUE_NOTES.md ({len(targets)} location(s))"

    return [
        StructuredTool.from_function(
            load_issue_context,
            name="load_issue_context",
            description="Load the GitHub issue title/body/comments for this run",
            args_schema=Empty,
        ),
        StructuredTool.from_function(
            repo_tree,
            name="repo_tree",
            description="List source files under workspace/repo/ (or workspace if no clone)",
            args_schema=RelPath,
        ),
        StructuredTool.from_function(
            git_status,
            name="git_status",
            description="Show git status inside workspace/repo/",
            args_schema=Empty,
        ),
        StructuredTool.from_function(
            git_diff,
            name="git_diff",
            description="Show git diff inside workspace/repo/",
            args_schema=Empty,
        ),
        StructuredTool.from_function(
            write_issue_notes,
            name="write_issue_notes",
            description="Write ISSUE_NOTES.md with summary and verification steps",
            args_schema=NotesArgs,
        ),
    ]
