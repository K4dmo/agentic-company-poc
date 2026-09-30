"""Tests for domain Builder tools."""

from __future__ import annotations

import json
from pathlib import Path

from agentic_company.tools.builder_toolkit import detect_deliverable_kind, make_builder_tools
from agentic_company.tools.github_builder import make_github_builder_tools
from agentic_company.tools.instagram_builder import make_instagram_builder_tools
from agentic_company.tools.linkedin_builder import make_linkedin_builder_tools


def test_instagram_write_post_package(tmp_path: Path) -> None:
    tools = {t.name: t for t in make_instagram_builder_tools(str(tmp_path))}
    result = tools["write_instagram_post"].invoke(
        {
            "id": "post-01-hook",
            "format": "single",
            "hook": "Stop the 3pm crash",
            "caption": "Cold brew that lasts.\n\nLink in bio.",
            "cta": "Link in bio",
            "hashtags": ["#coldbrew"],
            "alt_text": "Coffee on a desk",
            "image_prompts": ["Mug on laptop desk, soft daylight, 4:5"],
        }
    )
    assert "Wrote Instagram package" in result
    post_json = tmp_path / "posts" / "post-01-hook" / "post.json"
    assert post_json.is_file()
    data = json.loads(post_json.read_text(encoding="utf-8"))
    assert data["hook"] == "Stop the 3pm crash"
    assert (tmp_path / "posts" / "post-01-hook" / "caption.txt").is_file()

    tools["write_campaign_readme"].invoke(
        {"title": "Launch", "brand": "Bean", "goal": "awareness", "posting_order": ["post-01-hook"]}
    )
    assert (tmp_path / "posts" / "README.md").is_file()
    listing = tools["list_instagram_posts"].invoke({})
    assert "post-01-hook" in listing


def test_linkedin_write_post_package(tmp_path: Path) -> None:
    tools = {t.name: t for t in make_linkedin_builder_tools(str(tmp_path))}
    result = tools["write_linkedin_post"].invoke(
        {
            "id": "post-01-leadership",
            "format": "text",
            "hook": "Most teams ship features. Few ship outcomes.",
            "body": "Most teams ship features. Few ship outcomes.\n\nHere is what changed...",
            "cta": "What would you delete this quarter?",
            "hashtags": ["#leadership"],
            "tone": "direct",
            "audience": "EMs",
            "goal": "engagement",
        }
    )
    assert "Wrote LinkedIn package" in result
    post_json = tmp_path / "linkedin_posts" / "post-01-leadership" / "post.json"
    assert post_json.is_file()
    data = json.loads(post_json.read_text(encoding="utf-8"))
    assert data["platform"] == "linkedin"
    assert (tmp_path / "linkedin_posts" / "post-01-leadership" / "body.txt").is_file()

    tools["write_linkedin_campaign_readme"].invoke(
        {
            "title": "SaaS launch",
            "brand": "Acme",
            "goal": "pipeline",
            "posting_order": ["post-01-leadership"],
        }
    )
    assert (tmp_path / "linkedin_posts" / "README.md").is_file()
    listing = tools["list_linkedin_posts"].invoke({})
    assert "post-01-leadership" in listing


def test_github_issue_notes_and_context(tmp_path: Path) -> None:
    (tmp_path / "ISSUE.md").write_text("# Bug\nFix login", encoding="utf-8")
    tools = {t.name: t for t in make_github_builder_tools(str(tmp_path), thread_id=None)}
    ctx = tools["load_issue_context"].invoke({})
    assert "Fix login" in ctx
    note = tools["write_issue_notes"].invoke(
        {
            "summary": "Fixed null check",
            "verification": "pytest -q",
            "files_changed": ["repo/app.py"],
        }
    )
    assert "ISSUE_NOTES.md" in note
    assert (tmp_path / "ISSUE_NOTES.md").is_file()


def test_builder_toolkit_selects_domain_tools(tmp_path: Path) -> None:
    ig_tools = {t.name for t in make_builder_tools(str(tmp_path), "instagram_posts")}
    assert "write_instagram_post" in ig_tools
    assert "load_issue_context" not in ig_tools
    assert "write_linkedin_post" not in ig_tools

    li_tools = {t.name for t in make_builder_tools(str(tmp_path), "linkedin_posts")}
    assert "write_linkedin_post" in li_tools
    assert "write_instagram_post" not in li_tools

    gh_tools = {t.name for t in make_builder_tools(str(tmp_path), "github_issue")}
    assert "load_issue_context" in gh_tools
    assert "write_instagram_post" not in gh_tools


def test_detect_deliverable_kind() -> None:
    assert detect_deliverable_kind({"deliverable_kind": "instagram_posts"}) == "instagram_posts"
    assert detect_deliverable_kind({"brief": "Write 3 LinkedIn posts for a SaaS launch"}) == "linkedin_posts"
    assert (
        detect_deliverable_kind(
            {"brief": "See https://github.com/acme/app/issues/12 and fix it"}
        )
        == "github_issue"
    )
