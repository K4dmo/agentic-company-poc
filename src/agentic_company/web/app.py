"""FastAPI + HTMX dashboard for the agentic company."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from langgraph.types import Command

from agentic_company.config import get_settings
from agentic_company.graph import get_graph, initial_state
from agentic_company.persistence import list_runs, load_run_summary

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app = FastAPI(title="Agentic Company")


def _config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


def _interrupt_payload(thread_id: str) -> Any | None:
    graph = get_graph()
    state = graph.get_state(_config(thread_id))
    if not state or not state.tasks:
        return None
    for task in state.tasks:
        if task.interrupts:
            return task.interrupts[0].value
    return None


def _live_values(thread_id: str) -> dict[str, Any]:
    try:
        state = get_graph().get_state(_config(thread_id))
        return dict(state.values or {}) if state else {}
    except Exception:  # noqa: BLE001
        return {}


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    runs = list_runs()
    return templates.TemplateResponse(
        request,
        "index.html",
        {"runs": runs},
    )


@app.get("/runs/new", response_class=HTMLResponse)
def new_run_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "new_run.html",
        {"default_builder": get_settings().builder_backend},
    )


@app.post("/runs/new")
def create_run(
    brief: str = Form(...),
    builder: str = Form("native"),
) -> RedirectResponse:
    thread_id = str(uuid.uuid4())
    graph = get_graph()
    state = initial_state(brief, thread_id, builder_backend=builder)
    graph.invoke(state, config=_config(thread_id))
    return RedirectResponse(url=f"/runs/{thread_id}", status_code=303)


@app.get("/runs/{thread_id}", response_class=HTMLResponse)
def show_run(request: Request, thread_id: str) -> HTMLResponse:
    summary = load_run_summary(thread_id)
    live = _live_values(thread_id)
    interrupt = _interrupt_payload(thread_id)
    return templates.TemplateResponse(
        request,
        "run_detail.html",
        {
            "thread_id": thread_id,
            "summary": summary,
            "live": live,
            "interrupt": interrupt,
            "poll": bool(interrupt) or live.get("status") in {"building", "planning", "review"},
        },
    )


@app.get("/runs/{thread_id}/fragment", response_class=HTMLResponse)
def run_fragment(request: Request, thread_id: str) -> HTMLResponse:
    summary = load_run_summary(thread_id)
    live = _live_values(thread_id)
    interrupt = _interrupt_payload(thread_id)
    return templates.TemplateResponse(
        request,
        "run_fragment.html",
        {
            "thread_id": thread_id,
            "summary": summary,
            "live": live,
            "interrupt": interrupt,
            "poll": bool(interrupt) or live.get("status") in {"building", "planning", "review"},
        },
    )


@app.post("/runs/{thread_id}/decide")
def decide(
    thread_id: str,
    action: str = Form(...),
    note: str = Form(""),
) -> RedirectResponse:
    if action == "approve":
        decision = {"action": "approve"}
    elif action == "abort":
        decision = {"action": "abort"}
    else:
        decision = {"action": "revise", "brief": note, "revision_notes": note}
    get_graph().invoke(Command(resume=decision), config=_config(thread_id))
    return RedirectResponse(url=f"/runs/{thread_id}", status_code=303)


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "agentic_company.web.app:app",
        host=settings.web_host,
        port=settings.web_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
