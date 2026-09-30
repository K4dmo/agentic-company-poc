#!/usr/bin/env python3
"""Golden eval smoke — auto-approve HITL and assert terminal status."""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

# Ensure package import when run as script
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

os.environ["EVAL_MODE"] = "true"

from agentic_company.config import get_settings  # noqa: E402

get_settings.cache_clear()

from agentic_company.graph import get_graph, initial_state  # noqa: E402


def main() -> int:
    settings = get_settings()
    if not settings.openai_api_key:
        print("SKIP: OPENAI_API_KEY not set")
        return 0

    briefs_path = Path(__file__).parent / "golden_briefs.json"
    briefs = json.loads(briefs_path.read_text(encoding="utf-8"))
    graph = get_graph(force_reload=True)
    failures = 0

    for item in briefs:
        builders = item.get("builders") or ["native"]
        for builder in builders:
            thread_id = f"eval-{item['id']}-{builder}-{uuid.uuid4().hex[:8]}"
            print(f"\n=== {item['id']} builder={builder} thread={thread_id} ===")
            state = initial_state(item["brief"], thread_id, builder_backend=builder)
            config = {"configurable": {"thread_id": thread_id}}
            try:
                result = graph.invoke(state, config=config)
            except Exception as exc:  # noqa: BLE001
                print(f"FAIL invoke: {exc}")
                failures += 1
                continue
            values = graph.get_state(config).values or result
            status = values.get("status")
            critique = values.get("critique")
            ok = status in {"shipped", "failed", "aborted"} and (
                status != "failed" or bool(critique)
            )
            print(f"status={status} verdict={values.get('verdict')} ok={ok}")
            if not ok:
                failures += 1

    if failures:
        print(f"\n{failures} eval case(s) failed")
        return 1
    print("\nAll eval cases passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
