"""Tests for GitHub PR helpers and ship routing (no network)."""

from __future__ import annotations

from agentic_company.github_pr import build_pr_body, slugify_branch
from agentic_company.graph import route_after_builder, route_after_ship_gate, route_after_verify_tests


def test_slugify_branch() -> None:
    assert slugify_branch("Fix Login Crash!!!", 12).startswith("agentic/issue-12-")


def test_build_pr_body_includes_closes() -> None:
    body = build_pr_body(
        issue_url="https://github.com/acme/app/issues/3",
        issue_number=3,
        summary="Fixed null deref",
        test_output="3 passed",
        files_touched=["repo/app.py"],
    )
    assert "Closes #3" in body
    assert "3 passed" in body
    assert "repo/app.py" in body


def test_ship_routes_github_to_verify() -> None:
    assert (
        route_after_ship_gate(
            {"status": "shipped", "deliverable_kind": "github_issue", "abort": False}
        )
        == "verify_tests"
    )
    assert (
        route_after_ship_gate(
            {"status": "shipped", "deliverable_kind": "linkedin_posts", "abort": False}
        )
        == "linkedin_gate"
    )


def test_verify_routes_fix_loop_to_builder() -> None:
    assert (
        route_after_verify_tests(
            {
                "tests_passed": False,
                "test_retries": 1,
                "pipeline_phase": "fix_loop",
                "status": "building",
            }
        )
        == "builder"
    )
    assert route_after_builder({"pipeline_phase": "fix_loop"}) == "verify_tests"
    assert route_after_builder({}) == "critic"


from agentic_company.nodes.ship_pipeline import build_linkedin_announce_messages


def test_first_issue_linkedin_prompt_covers_project() -> None:
    system, human = build_linkedin_announce_messages(
        meta={"title": "Bootstrap CI", "url": "https://github.com/acme/app/issues/1", "number": 1},
        notes="Added CI",
        pr_url="https://github.com/acme/app/pull/2",
        tests_passed=True,
        builder_summary="CI works",
        first_issue=True,
        project={
            "full_name": "acme/app",
            "description": "Tiny task runner",
            "homepage": "",
            "language": "Python",
            "topics": ["automation"],
            "html_url": "https://github.com/acme/app",
            "readme_excerpt": "# App\nRuns tasks.",
        },
    )
    assert "FIRST shipped issue" in system or "PROJECT" in system
    assert "Tiny task runner" in human
    assert "cover the project AND the issue" in human


def test_regular_issue_linkedin_prompt_is_fix_focused() -> None:
    system, human = build_linkedin_announce_messages(
        meta={"title": "Fix nil panic", "url": "https://github.com/acme/app/issues/9"},
        notes="Fixed",
        pr_url="https://github.com/acme/app/pull/10",
        tests_passed=True,
        builder_summary="ok",
        first_issue=False,
        project={},
    )
    assert "shipped engineering fix" in system
    assert "cover the project AND the issue" not in human
