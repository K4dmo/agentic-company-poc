"""GitHub issue parsing / brief tests (no network)."""

from __future__ import annotations

import pytest

from agentic_company.github_issues import GitHubIssue, IssueRef, parse_issue_ref


def test_parse_issue_url() -> None:
    ref = parse_issue_ref("https://github.com/K4dmo/agentic-company-poc/issues/42")
    assert ref.owner == "K4dmo"
    assert ref.repo == "agentic-company-poc"
    assert ref.number == 42


def test_parse_shorthand() -> None:
    ref = parse_issue_ref("acme/widgets#7")
    assert ref == IssueRef(owner="acme", repo="widgets", number=7)


def test_parse_repo_number() -> None:
    ref = parse_issue_ref(None, repo="acme/widgets", number=9)
    assert ref.number == 9


def test_parse_invalid() -> None:
    with pytest.raises(ValueError):
        parse_issue_ref("not-an-issue")


def test_issue_brief_contains_rules() -> None:
    issue = GitHubIssue(
        ref=IssueRef("acme", "widgets", 1),
        title="Fix login crash",
        body="Steps to reproduce...",
        state="open",
        labels=["bug"],
        author="alice",
        comments=[{"author": "bob", "body": "Confirmed on main"}],
        raw={},
    )
    brief = issue.to_brief()
    assert "Fix login crash" in brief
    assert "acme/widgets" in brief
    assert "ISSUE_NOTES.md" in brief
    assert "Confirmed on main" in brief


def test_is_first_issue_number_one() -> None:
    from agentic_company.github_issues import is_first_issue

    assert is_first_issue(IssueRef("acme", "widgets", 1)) is True


def test_issue_artifact_marks_first() -> None:
    from agentic_company.github_issues import issue_artifact_payload

    issue = GitHubIssue(
        ref=IssueRef("acme", "widgets", 1),
        title="Bootstrap",
        body="First issue",
        state="open",
        labels=[],
        author="alice",
        comments=[],
        raw={},
    )
    payload = issue_artifact_payload(issue)
    assert payload["is_first_issue"] is True
