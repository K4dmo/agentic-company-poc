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
- **Specialists (allowlisted):** `tester`, `docs_writer`, `security_reviewer`, `social_copywriter`, `visual_designer`
- **Deliverables:** software, Instagram (`posts/`), LinkedIn (`linkedin_posts/`), or GitHub issue implementations (optional repo clone into `workspace/repo/`)

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
# set one of: OPENROUTER_API_KEY, OPENAI_API_KEY, or CURSOR_API_KEY (+ CURSOR_BASE_URL)
```

## LLM providers

| Provider | Env | Notes |
|---|---|---|
| **OpenRouter** | `OPENROUTER_API_KEY` | Recommended multi-model option. Set `LLM_PROVIDER=openrouter` or leave `auto`. |
| **OpenAI** | `OPENAI_API_KEY` | Direct OpenAI. |
| **Cursor** | `CURSOR_API_KEY` + `CURSOR_BASE_URL` | Cursor keys are for [Cloud Agents](https://cursor.com/docs/api), not chat completions. Use an OpenAI-compatible gateway URL in `CURSOR_BASE_URL` (e.g. `http://127.0.0.1:8787/v1`). |

`LLM_PROVIDER=auto` picks **openrouter → cursor → openai** based on which credentials are present.

OpenRouter example:

```bash
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-...
PLANNER_MODEL=openai/gpt-4o-mini
BUILDER_MODEL=openai/gpt-4o
```

## CLI

```bash
python -m agentic_company.cli run "Build a CPF validator module with tests"
python -m agentic_company.cli run "Create 3 Instagram posts for a cold-brew brand launch"
python -m agentic_company.cli run "Write 3 LinkedIn posts for a B2B SaaS product launch"
python -m agentic_company.cli run "..." --builder deepagents

# GitHub issue → plan → implement (optional --clone)
python -m agentic_company.cli issue https://github.com/owner/repo/issues/123 --clone
python -m agentic_company.cli issue owner/repo#123
python -m agentic_company.cli issue --repo owner/repo --number 123 --clone

python -m agentic_company.cli resume --thread-id <id> --approve
python -m agentic_company.cli resume --thread-id <id> --revise "Add edge-case tests"
# LinkedIn publish gate (after draft):
python -m agentic_company.cli resume --thread-id <id> --approve --image ./shot.png
python -m agentic_company.cli resume --thread-id <id> --skip

python -m agentic_company.cli list
python -m agentic_company.cli show --thread-id <id>
```

## GitHub issues

Set `GITHUB_TOKEN` in `.env` for private repos and higher rate limits (public issues often work without a token).

```bash
python -m agentic_company.cli issue https://github.com/owner/repo/issues/42 --clone
```

This fetches title/body/labels/comments, writes `artifacts/github_issue.md` + workspace `ISSUE.md`, optionally shallow-clones into `workspace/repo/`, then runs the crew with `deliverable_kind=github_issue`.

**GitHub issue pipeline after you approve ship:**
1. Builder implements + writes tests (tools: `run_tests`, `write_issue_notes`, …)
2. `verify_tests` runs `pytest` (retries Builder up to 2 times on failure)
3. `create_pr` commits, pushes a branch, opens a PR (`GITHUB_TOKEN` required)
4. `linkedin_announce` drafts a LinkedIn post under `linkedin_posts/` about the shipped fix
   - If this is the **first issue** in the repo (`#1` or earliest non-PR issue), the post also introduces the **project** (README/description/topics), not only the fix
5. `linkedin_gate` pauses and returns the drafted post for **your approval**
6. On approve, `linkedin_publish` posts via LinkedIn UGC (`POST /v2/ugcPosts`) — optional local `--image` or `--article-url`

Artifacts: `test_results.json`, `pull_request.json`, `linkedin_announce.json`, `linkedin_publish.json`.

## LinkedIn publish (Share on LinkedIn)

Uses the [Share on LinkedIn](https://learn.microsoft.com/en-gb/linkedin/consumer/integrations/self-serve/share-on-linkedin) consumer integration (`w_member_social`).

Set in `.env`:

```bash
LINKEDIN_ACCESS_TOKEN=...   # member token with w_member_social
LINKEDIN_PERSON_URN=        # optional urn:li:person:...
LINKEDIN_VISIBILITY=PUBLIC  # or CONNECTIONS
```

After a draft exists (GitHub ship pipeline or a `linkedin_posts` brief), the run **interrupts** with the post text. You review, optionally attach an image, then approve:

```bash
# Publish text (+ optional article/PR link)
python -m agentic_company.cli resume --thread-id <id> --approve \
  --article-url https://github.com/owner/repo/pull/12

# Publish with a local image (image takes precedence over article URL)
python -m agentic_company.cli resume --thread-id <id> --approve \
  --image ./assets/launch.png --text "Optional override copy"

# Edit copy and re-prompt for approval (does not publish yet)
python -m agentic_company.cli resume --thread-id <id> --revise "Updated post body…"

# Continue without publishing
python -m agentic_company.cli resume --thread-id <id> --skip
```

The web dashboard shows the same gate with text / image path / article URL fields.

## Web dashboard

```bash
python -m agentic_company.web
# open http://127.0.0.1:8000
```

## Instagram posts

Briefs about Instagram / captions / carousels / Reels are planned as `deliverable_kind=instagram_posts`. The Planner typically hires `social_copywriter` + `visual_designer`. The Builder writes:

```
posts/README.md
posts/<id>/post.json
posts/<id>/caption.txt
posts/<id>/image_prompt.txt
posts/<id>/slides.md          # carousels
```

See `src/agentic_company/templates/instagram_post.example.json` for the `post.json` shape. Image binaries are not generated — `image_prompts` are text for a designer or image model.

The **Builder** gets Instagram tools: `write_instagram_post` (schema-validated package writer), `write_campaign_readme`, `list_instagram_posts`.

## LinkedIn posts

Briefs about LinkedIn / thought leadership / LinkedIn carousels or polls use `deliverable_kind=linkedin_posts`. Output:

```
linkedin_posts/README.md
linkedin_posts/<id>/post.json
linkedin_posts/<id>/body.txt
linkedin_posts/<id>/image_prompt.txt   # when needed
linkedin_posts/<id>/slides.md          # document carousels
linkedin_posts/<id>/poll.txt           # polls
```

Formats: `text`, `single_image`, `carousel_document`, `poll`.  
See `src/agentic_company/templates/linkedin_post.example.json`.

Builder tools: `write_linkedin_post`, `write_linkedin_campaign_readme`, `list_linkedin_posts`.

After ship approval, LinkedIn deliverables also hit `linkedin_gate` → human approve (optional image) → `linkedin_publish` (same Share API as above).

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
