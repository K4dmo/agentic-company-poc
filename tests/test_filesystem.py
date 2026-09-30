"""Path-jail unit tests without API key."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentic_company.tools.filesystem import PathError, make_filesystem_tools, resolve_in_workspace


def test_resolve_allows_nested(tmp_path: Path) -> None:
    target = resolve_in_workspace(tmp_path, "src/app.py")
    assert target == (tmp_path / "src" / "app.py").resolve()


def test_resolve_blocks_escape(tmp_path: Path) -> None:
    with pytest.raises(PathError):
        resolve_in_workspace(tmp_path, "../outside.txt")


def test_write_and_read_roundtrip(tmp_path: Path) -> None:
    tools = {t.name: t for t in make_filesystem_tools(str(tmp_path))}
    assert "Wrote" in tools["write_file"].invoke({"path": "a.txt", "content": "hi"})
    assert tools["read_file"].invoke({"path": "a.txt"}) == "hi"
    listing = tools["list_dir"].invoke({"path": "."})
    assert "a.txt" in listing


def test_edit_file(tmp_path: Path) -> None:
    tools = {t.name: t for t in make_filesystem_tools(str(tmp_path))}
    tools["write_file"].invoke({"path": "b.txt", "content": "hello world"})
    tools["edit_file"].invoke({"path": "b.txt", "old": "world", "new": "there"})
    assert tools["read_file"].invoke({"path": "b.txt"}) == "hello there"


def test_write_blocks_escape(tmp_path: Path) -> None:
    tools = {t.name: t for t in make_filesystem_tools(str(tmp_path))}
    with pytest.raises(Exception):
        tools["write_file"].invoke({"path": "../escape.txt", "content": "nope"})
