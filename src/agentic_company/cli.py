"""CLI for running and resuming company threads."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from typing import Any

from langgraph.types import Command

from agentic_company.config import ensure_run_dirs, get_settings
from agentic_company.github_issues import (
    clone_repo_into_workspace,
    fetch_issue,
    issue_artifact_payload,
    parse_issue_ref,
)
from agentic_company.graph import get_graph, initial_state
from agentic_company.llm import credentials_help, has_llm_credentials, resolve_provider
from agentic_company.persistence import list_runs, load_run_summary, write_artifact


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
    if isinstance(payload, dict) and payload.get("type") == "linkedin_publish_approval":
        print(
            '  python -m agentic_company.cli resume --thread-id <id> --approve '
            '--image ./path/to/image.png --article-url https://...'
        )
        print('  python -m agentic_company.cli resume --thread-id <id> --revise "edited post text"')
        print('  python -m agentic_company.cli resume --thread-id <id> --skip')


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


def _start_run(brief: str, *, builder: str | None, thread_id: str | None, extra: dict[str, Any] | None = None) -> int:
    settings = get_settings()
    if not has_llm_credentials() and not settings.eval_mode:
        print(credentials_help(), file=sys.stderr)
        return 1
    tid = thread_id or str(uuid.uuid4())
    graph = get_graph()
    state = initial_state(brief, tid, builder_backend=builder)
    if extra:
        state.update(extra)
    print(
        f"Starting thread_id={tid} provider={resolve_provider()} "
        f"builder={state['builder_backend']}"
    )
    _run_until_pause(graph, state, _config(tid))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    return _start_run(args.brief, builder=args.builder, thread_id=args.thread_id)


def cmd_issue(args: argparse.Namespace) -> int:
    try:
        ref = parse_issue_ref(args.issue, repo=args.repo, number=args.number)
        issue = fetch_issue(ref, include_comments=not args.no_comments)
    except (ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    thread_id = args.thread_id or str(uuid.uuid4())
    workspace, _ = ensure_run_dirs(thread_id)
    write_artifact(
        thread_id,
        "github_issue.json",
        issue_artifact_payload(issue),
    )
    write_artifact(thread_id, "github_issue.md", issue.to_brief())
    # Seed workspace so Builder tools and humans can open ISSUE.md locally
    (workspace / "ISSUE.md").write_text(issue.to_brief(), encoding="utf-8")

    if args.clone:
        try:
            repo_path = clone_repo_into_workspace(ref, workspace)
            print(f"Cloned {ref.full_name} -> {repo_path}")
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1

    brief = issue.to_brief()
    print(f"Loaded {issue.ref.url}: {issue.title}")
    return _start_run(
        brief,
        builder=args.builder,
        thread_id=thread_id,
        extra={"deliverable_kind": "github_issue"},
    )


def cmd_resume(args: argparse.Namespace) -> int:
    thread_id = args.thread_id
    if args.approve:
        decision: dict[str, Any] = {"action": "approve"}
        if args.text:
            decision["text"] = args.text
        if args.image:
            decision["image_path"] = args.image
        if args.article_url:
            decision["article_url"] = args.article_url
        if args.visibility:
            decision["visibility"] = args.visibility
    elif args.skip:
        decision = {"action": "skip"}
    elif args.abort:
        decision = {"action": "abort"}
    elif args.revise is not None:
        decision = {
            "action": "revise",
            "brief": args.revise,
            "revision_notes": args.revise,
            "text": args.revise,
        }
    else:
        print(
            "Provide --approve, --skip, --abort, or --revise TEXT",
            file=sys.stderr,
        )
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

    issue_p = sub.add_parser(
        "issue",
        help="Fetch a GitHub issue and implement it with the crew",
    )
    issue_p.add_argument(
        "issue",
        nargs="?",
        default=None,
        help="Issue URL or owner/repo#123",
    )
    issue_p.add_argument("--repo", default=None, help="owner/name (with --number)")
    issue_p.add_argument("--number", type=int, default=None, help="Issue number (with --repo)")
    issue_p.add_argument(
        "--clone",
        action="store_true",
        help="Shallow-clone the repository into the run workspace/repo/",
    )
    issue_p.add_argument(
        "--no-comments",
        action="store_true",
        help="Skip fetching issue comments",
    )
    issue_p.add_argument("--builder", choices=["native", "deepagents"], default=None)
    issue_p.add_argument("--thread-id", default=None)
    issue_p.set_defaults(func=cmd_issue)

    resume_p = sub.add_parser("resume", help="Resume after a human interrupt")
    resume_p.add_argument("--thread-id", required=True)
    resume_p.add_argument("--approve", action="store_true")
    resume_p.add_argument("--skip", action="store_true", help="Skip LinkedIn publish")
    resume_p.add_argument("--abort", action="store_true")
    resume_p.add_argument("--revise", type=str, default=None)
    resume_p.add_argument(
        "--text",
        type=str,
        default=None,
        help="Override LinkedIn post text when approving",
    )
    resume_p.add_argument(
        "--image",
        type=str,
        default=None,
        help="Local image path to attach when publishing to LinkedIn",
    )
    resume_p.add_argument(
        "--article-url",
        type=str,
        default=None,
        help="Article/PR URL to attach (ignored if --image is set)",
    )
    resume_p.add_argument(
        "--visibility",
        choices=["PUBLIC", "CONNECTIONS"],
        default=None,
        help="LinkedIn share visibility",
    )
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
