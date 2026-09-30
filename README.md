# Agentic Company

LangGraph “software company” with three core roles — **Planner**, **Builder**, **Critic** — plus optional specialist hiring, sandboxed filesystem tools, human approval gates, SQLite checkpoints, cross-run vector memory, CLI, and a FastAPI + HTMX dashboard.

## Architecture

```
MemoryRecall → Planner → [plan gate] → Specialists? → Builder → Critic
                              ↑                         │
                              └── revise ←──────────────┤
                                                        ↓
                                              [ship gate] → MemoryWrite → END
```

- **Company OS:** custom LangGraph `StateGraph` (not CrewAI)
- **Builder backends:** `native` (tool ReAct loop) or `deepagents` (optional harness; falls back to native if unavailable)
- **Specialists (allowlisted):** `tester`, `docs_writer`, `security_reviewer`

## Setup

Requires Python ≥ 3.11 (this repo was developed with 3.12 via `uv`).

```bash
cd ~/repos/agentic-company
# with uv (recommended)
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# or: python3.12 -m venv .venv && pip install -e ".[dev]"
cp .env.example .env
# set OPENAI_API_KEY in .env
```

## CLI

```bash
python -m agentic_company.cli run "Build a CPF validator module with tests"
python -m agentic_company.cli run "..." --builder deepagents

python -m agentic_company.cli resume --thread-id <id> --approve
python -m agentic_company.cli resume --thread-id <id> --revise "Add edge-case tests"

python -m agentic_company.cli list
python -m agentic_company.cli show --thread-id <id>
```

## Web dashboard

```bash
python -m agentic_company.web
# open http://127.0.0.1:8000
```

## Evals

```bash
EVAL_MODE=true python evals/run_eval.py
```

Auto-approves interrupts and asserts each golden brief ends in `shipped` or `failed` (with critique).

## Tests (offline)

```bash
pytest -q
```

## Layout

See `src/agentic_company/` for graph, nodes, tools, memory, backends, CLI, and web UI. Run artifacts land in `runs/{thread_id}/`.
