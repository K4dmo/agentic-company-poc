"""CLI for running and resuming company threads."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from typing import Any

from langgraph.types import Command

from agentic_company.config import get_settings
from agentic_company.graph import get_graph, initial_state
from agentic_company.persistence import list_runs, load_run_summary


def _config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


def _print_interrupt(payload: Any) -> None:
    print("\n=== Awaiting human decision ===")
    if isinstance(payload, (dict, list)):
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(payload)
    print("Resume with:")
    print('  python -m agentic_company.cli resume --thread-id <id> --approve')
    print('  python -m agentic_company.cli resume --thread-id <id> --revise "notes or new brief"')


def _run_until_pause(graph, input_data: Any, config: dict[str, Any]) -> dict[str, Any] | None:
    result = graph.invoke(input_data, config=config)
    state = graph.get_state(config)
    if state.tasks:
        for task in state.tasks:
            if task.interrupts:
                _print_interrupt(task.interrupts[0].value)
                print(f"\nthread_id={config['configurable']['thread_id']}")
                return None
    print("\n=== Run finished ===")
    values = state.values if state else result
    print(json.dumps({
        "status": values.get("status"),
        "verdict": values.get("verdict"),
        "files_touched": values.get("files_touched"),
        "builder_summary": values.get("builder_summary"),
        "critique": values.get("critique"),
    }, indent=2, ensure_ascii=False, default=str))
    return values


def cmd_run(args: argparse.Namespace) -> int:
    settings = get_settings()
    if not settings.openai_api_key and not settings.eval_mode:
        print("OPENAI_API_KEY is not set. Copy .env.example to .env", file=sys.stderr)
        return 1
    thread_id = args.thread_id or str(uuid.uuid4())
    graph = get_graph()
    state = initial_state(args.brief, thread_id, builder_backend=args.builder)
    print(f"Starting thread_id={thread_id} builder={state['builder_backend']}")
    _run_until_pause(graph, state, _config(thread_id))
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    thread_id = args.thread_id
    if args.approve:
        decision = {"action": "approve"}
    elif args.abort:
        decision = {"action": "abort"}
    elif args.revise is not None:
        # plan gate uses brief; ship gate uses revision_notes
        decision = {
            "action": "revise",
            "brief": args.revise,
            "revision_notes": args.revise,
        }
    else:
        print("Provide --approve, --abort, or --revise TEXT", file=sys.stderr)
        return 1

    graph = get_graph()
    print(f"Resuming thread_id={thread_id} decision={decision}")
    _run_until_pause(graph, Command(resume=decision), _config(thread_id))
    return 0


def cmd_list(_: argparse.Namespace) -> int:
    runs = list_runs()
    if not runs:
        print("No runs yet.")
        return 0
    for run in runs:
        print(
            f"{run.get('thread_id')}\tstatus={run.get('status')}\t"
            f"verdict={run.get('verdict')}\tbrief={str(run.get('brief', ''))[:60]}"
        )
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    summary = load_run_summary(args.thread_id)
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    # Also show live graph state if present
    try:
        graph = get_graph()
        state = graph.get_state(_config(args.thread_id))
        if state and state.values:
            print("\n--- live checkpoint ---")
            print(json.dumps({
                "status": state.values.get("status"),
                "verdict": state.values.get("verdict"),
                "next": list(state.next) if state.next else [],
            }, indent=2, default=str))
    except Exception as exc:  # noqa: BLE001
        print(f"(no live checkpoint: {exc})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentic-company", description="LangGraph agentic company CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Start a new company run")
    run_p.add_argument("brief", help="Product brief for the crew")
    run_p.add_argument("--builder", choices=["native", "deepagents"], default=None)
    run_p.add_argument("--thread-id", default=None)
    run_p.set_defaults(func=cmd_run)

    resume_p = sub.add_parser("resume", help="Resume after a human interrupt")
    resume_p.add_argument("--thread-id", required=True)
    resume_p.add_argument("--approve", action="store_true")
    resume_p.add_argument("--abort", action="store_true")
    resume_p.add_argument("--revise", type=str, default=None)
    resume_p.set_defaults(func=cmd_resume)

    list_p = sub.add_parser("list", help="List past runs")
    list_p.set_defaults(func=cmd_list)

    show_p = sub.add_parser("show", help="Show run artifacts / state")
    show_p.add_argument("--thread-id", required=True)
    show_p.set_defaults(func=cmd_show)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
