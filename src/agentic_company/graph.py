"""Company StateGraph — org chart as executable workflow."""

from __future__ import annotations

from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from agentic_company.config import ensure_run_dirs, get_settings
from agentic_company.nodes.builder import builder_node
from agentic_company.nodes.critic import critic_node
from agentic_company.nodes.gates import plan_gate_node, ship_gate_node
from agentic_company.nodes.linkedin_publish import linkedin_gate_node, linkedin_publish_node
from agentic_company.nodes.memory_nodes import memory_recall_node, memory_write_node
from agentic_company.nodes.planner import planner_node
from agentic_company.nodes.ship_pipeline import (
    create_pr_node,
    linkedin_announce_node,
    verify_tests_node,
)
from agentic_company.nodes.specialists import specialists_node
from agentic_company.persistence import get_checkpointer
from agentic_company.state import CompanyState
from agentic_company.tools.builder_toolkit import detect_deliverable_kind

_compiled = None


def route_after_plan_gate(
    state: CompanyState,
) -> Literal["planner", "specialists", "builder", "memory_write"]:
    if state.get("abort"):
        return "memory_write"
    feedback = state.get("human_feedback") or {}
    if feedback.get("action") == "revise":
        return "planner"
    hired = state.get("hired_specialists") or []
    if hired:
        return "specialists"
    return "builder"


def route_after_critic(
    state: CompanyState,
) -> Literal["builder", "ship_gate", "memory_write"]:
    settings = get_settings()
    if state.get("verdict") == "pass":
        return "ship_gate"
    retries = int(state.get("retries") or 0)
    if retries < settings.max_builder_retries:
        return "builder"
    return "memory_write"


def route_after_builder(
    state: CompanyState,
) -> Literal["critic", "verify_tests"]:
    if state.get("pipeline_phase") == "fix_loop":
        return "verify_tests"
    return "critic"


def route_after_ship_gate(
    state: CompanyState,
) -> Literal["builder", "verify_tests", "linkedin_gate", "memory_write"]:
    if state.get("abort"):
        return "memory_write"
    if state.get("status") == "shipped":
        kind = detect_deliverable_kind(state)
        if kind == "github_issue":
            return "verify_tests"
        if kind == "linkedin_posts":
            return "linkedin_gate"
        return "memory_write"
    return "builder"


def route_after_linkedin_gate(
    state: CompanyState,
) -> Literal["linkedin_gate", "linkedin_publish", "memory_write"]:
    phase = state.get("pipeline_phase")
    decision = state.get("linkedin_publish_decision") or {}
    if phase == "linkedin_revise":
        return "linkedin_gate"
    if decision.get("action") == "approve":
        return "linkedin_publish"
    return "memory_write"


def route_after_verify_tests(
    state: CompanyState,
) -> Literal["builder", "create_pr"]:
    passed = bool(state.get("tests_passed"))
    retries = int(state.get("test_retries") or 0)
    if not passed and retries <= 2 and state.get("pipeline_phase") == "fix_loop":
        return "builder"
    if not passed and retries <= 2 and state.get("status") == "building":
        return "builder"
    return "create_pr"


def build_graph():
    graph = StateGraph(CompanyState)
    graph.add_node("memory_recall", memory_recall_node)
    graph.add_node("planner", planner_node)
    graph.add_node("plan_gate", plan_gate_node)
    graph.add_node("specialists", specialists_node)
    graph.add_node("builder", builder_node)
    graph.add_node("critic", critic_node)
    graph.add_node("ship_gate", ship_gate_node)
    graph.add_node("verify_tests", verify_tests_node)
    graph.add_node("create_pr", create_pr_node)
    graph.add_node("linkedin_announce", linkedin_announce_node)
    graph.add_node("linkedin_gate", linkedin_gate_node)
    graph.add_node("linkedin_publish", linkedin_publish_node)
    graph.add_node("memory_write", memory_write_node)

    graph.add_edge(START, "memory_recall")
    graph.add_edge("memory_recall", "planner")
    graph.add_edge("planner", "plan_gate")
    graph.add_conditional_edges(
        "plan_gate",
        route_after_plan_gate,
        {
            "planner": "planner",
            "specialists": "specialists",
            "builder": "builder",
            "memory_write": "memory_write",
        },
    )
    graph.add_edge("specialists", "builder")
    graph.add_conditional_edges(
        "builder",
        route_after_builder,
        {"critic": "critic", "verify_tests": "verify_tests"},
    )
    graph.add_conditional_edges(
        "critic",
        route_after_critic,
        {
            "builder": "builder",
            "ship_gate": "ship_gate",
            "memory_write": "memory_write",
        },
    )
    graph.add_conditional_edges(
        "ship_gate",
        route_after_ship_gate,
        {
            "builder": "builder",
            "verify_tests": "verify_tests",
            "linkedin_gate": "linkedin_gate",
            "memory_write": "memory_write",
        },
    )
    graph.add_conditional_edges(
        "verify_tests",
        route_after_verify_tests,
        {"builder": "builder", "create_pr": "create_pr"},
    )
    graph.add_edge("create_pr", "linkedin_announce")
    graph.add_edge("linkedin_announce", "linkedin_gate")
    graph.add_conditional_edges(
        "linkedin_gate",
        route_after_linkedin_gate,
        {
            "linkedin_gate": "linkedin_gate",
            "linkedin_publish": "linkedin_publish",
            "memory_write": "memory_write",
        },
    )
    graph.add_edge("linkedin_publish", "memory_write")
    graph.add_edge("memory_write", END)
    return graph


def get_graph(force_reload: bool = False):
    global _compiled
    if _compiled is None or force_reload:
        _compiled = build_graph().compile(checkpointer=get_checkpointer())
    return _compiled


def initial_state(
    brief: str,
    thread_id: str,
    builder_backend: str | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    workspace, _ = ensure_run_dirs(thread_id)
    backend = (builder_backend or settings.builder_backend).lower()
    return {
        "brief": brief,
        "thread_id": thread_id,
        "workspace_root": str(workspace),
        "builder_backend": backend,
        "retries": 0,
        "status": "planning",
        "memory_hits": [],
        "specialist_notes": [],
        "files_touched": [],
        "revision_notes": [],
        "critique_history": [],
        "abort": False,
        "deliverable_kind": "software",
        "test_retries": 0,
        "tests_passed": False,
    }
