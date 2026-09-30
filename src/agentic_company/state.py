"""LangGraph shared company state."""

from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict


Status = Literal[
    "planning",
    "building",
    "review",
    "awaiting_human",
    "shipped",
    "failed",
    "aborted",
]


class CompanyState(TypedDict, total=False):
    brief: str
    thread_id: str
    memory_hits: list[dict[str, Any]]
    plan: str
    acceptance_criteria: list[str]
    file_outline: list[str]
    hired_specialists: list[str]
    deliverable_kind: str
    specialist_notes: list[dict[str, Any]]
    workspace_root: str
    builder_backend: str
    builder_messages: list[dict[str, Any]]
    files_touched: list[str]
    critique: dict[str, Any]
    verdict: Literal["pass", "fail"]
    revision_notes: list[str]
    retries: int
    status: Status
    human_feedback: dict[str, Any]
    abort: bool
    builder_summary: str
    critique_history: Annotated[list[dict[str, Any]], operator.add]
    pipeline_phase: str
    tests_passed: bool
    test_output: str
    test_retries: int
    pr_url: str
    pr_number: int
    pr_result: dict[str, Any]
    linkedin_announce: dict[str, Any]
    linkedin_publish_decision: dict[str, Any]
    linkedin_publish_result: dict[str, Any]
