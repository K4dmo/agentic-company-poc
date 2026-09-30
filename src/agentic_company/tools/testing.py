"""Sandboxed test runner tool."""

from __future__ import annotations

import subprocess
from pathlib import Path

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from agentic_company.config import get_settings
from agentic_company.tools.filesystem import PathError, resolve_in_workspace


def make_testing_tools(workspace_root: str) -> list[StructuredTool]:
    root = Path(workspace_root).resolve()
    timeout = get_settings().test_timeout_seconds

    class RunArgs(BaseModel):
        command: str = Field(
            default="python -m pytest -q",
            description="Shell command to run with cwd=workspace (no cd outside)",
        )

    def run_tests(command: str = "python -m pytest -q") -> str:
        # Reject obvious escapes
        if ".." in command.split() or command.strip().startswith("cd "):
            return "Rejected command: path traversal or cd not allowed"
        try:
            resolve_in_workspace(root, ".")
        except PathError as exc:
            return str(exc)
        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return f"Timed out after {timeout}s: {command}"
        out = (proc.stdout or "") + (proc.stderr or "")
        if len(out) > 20_000:
            out = out[:20_000] + "\n...[truncated]..."
        return f"exit={proc.returncode}\n{out}"

    return [
        StructuredTool.from_function(
            run_tests,
            name="run_tests",
            description="Run a test/build command inside the workspace sandbox",
            args_schema=RunArgs,
        )
    ]
