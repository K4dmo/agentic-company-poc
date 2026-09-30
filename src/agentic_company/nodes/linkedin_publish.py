"""Human approval + LinkedIn UGC publish nodes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langgraph.types import interrupt

from agentic_company.config import get_settings
from agentic_company.linkedin_client import publish_share
from agentic_company.persistence import write_artifact


def _compose_post_text(package: dict[str, Any], workspace: Path) -> str:
    post_id = package.get("post_id")
    if post_id:
        body_path = workspace / "linkedin_posts" / post_id / "body.txt"
        if body_path.is_file():
            text = body_path.read_text(encoding="utf-8").strip()
            hook = ""
            meta = workspace / "linkedin_posts" / post_id / "post.json"
            if meta.is_file():
                try:
                    data = json.loads(meta.read_text(encoding="utf-8"))
                    hook = str(data.get("hook") or "").strip()
                except json.JSONDecodeError:
                    pass
            if hook and hook not in text:
                return f"{hook}\n\n{text}".strip()
            return text
    hook = str(package.get("hook") or "").strip()
    body = str(package.get("body") or "").strip()
    if hook and body:
        return f"{hook}\n\n{body}".strip()
    return body or hook


def _load_latest_linkedin_package(workspace: Path) -> dict[str, Any]:
    root = workspace / "linkedin_posts"
    if not root.is_dir():
        return {}
    candidates = sorted(
        [p for p in root.iterdir() if p.is_dir() and (p / "post.json").is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return {}
    folder = candidates[0]
    data = json.loads((folder / "post.json").read_text(encoding="utf-8"))
    return {
        "post_id": folder.name,
        "hook": data.get("hook"),
        "body": data.get("body"),
        "pr_url": None,
        "issue_url": None,
    }


def linkedin_gate_node(state: dict[str, Any]) -> dict[str, Any]:
    """Pause for human approval of the drafted LinkedIn post (optional image/URL)."""
    settings = get_settings()
    workspace = Path(state.get("workspace_root") or ".")
    package = dict(state.get("linkedin_announce") or {})
    if not package.get("post_id"):
        package = {**package, **_load_latest_linkedin_package(workspace)}

    text = _compose_post_text(package, workspace)
    default_article = (
        package.get("pr_url")
        or (package.get("project") or {}).get("html_url")
        or package.get("issue_url")
    )
    payload = {
        "type": "linkedin_publish_approval",
        "thread_id": state.get("thread_id"),
        "post_id": package.get("post_id"),
        "text": text,
        "is_first_issue": package.get("is_first_issue"),
        "suggested_article_url": default_article,
        "instructions": (
            "Approve to publish via LinkedIn Share API (w_member_social). "
            "Optionally set image_path to a local image file and/or article_url. "
            "Use action=revise with text to edit copy without publishing. "
            "Use action=skip to continue without publishing."
        ),
        "docs": "https://learn.microsoft.com/en-gb/linkedin/consumer/integrations/self-serve/share-on-linkedin",
    }

    if settings.eval_mode:
        decision = {"action": "skip"}
    else:
        decision = interrupt(payload)

    action = (decision or {}).get("action", "skip")
    if action == "revise":
        revised = (decision or {}).get("text") or text
        post_id = package.get("post_id")
        if post_id:
            body_path = workspace / "linkedin_posts" / post_id / "body.txt"
            body_path.parent.mkdir(parents=True, exist_ok=True)
            body_path.write_text(revised, encoding="utf-8")
            meta_path = body_path.parent / "post.json"
            if meta_path.is_file():
                try:
                    data = json.loads(meta_path.read_text(encoding="utf-8"))
                    data["body"] = revised
                    meta_path.write_text(
                        json.dumps(data, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                except json.JSONDecodeError:
                    pass
        package = {**package, "body": revised}
        return {
            "linkedin_announce": package,
            "linkedin_publish_decision": decision,
            "status": "awaiting_human",
            "pipeline_phase": "linkedin_revise",
        }

    if action in {"abort", "skip"}:
        return {
            "linkedin_publish_decision": decision,
            "linkedin_publish_result": {"ok": False, "skipped": True, "action": action},
            "status": "shipped",
            "pipeline_phase": "done",
        }

    return {
        "linkedin_publish_decision": {
            "action": "approve",
            "text": (decision or {}).get("text") or text,
            "image_path": (decision or {}).get("image_path"),
            "article_url": (decision or {}).get("article_url") or default_article,
            "visibility": (decision or {}).get("visibility") or "PUBLIC",
        },
        "status": "shipped",
        "pipeline_phase": "linkedin_publish",
    }


def linkedin_publish_node(state: dict[str, Any]) -> dict[str, Any]:
    decision = state.get("linkedin_publish_decision") or {}
    if decision.get("action") != "approve":
        return {
            "linkedin_publish_result": {"ok": False, "skipped": True},
            "status": "shipped",
        }

    text = str(decision.get("text") or "").strip()
    if not text:
        workspace = Path(state.get("workspace_root") or ".")
        package = dict(state.get("linkedin_announce") or {})
        text = _compose_post_text(package, workspace)

    image_path = decision.get("image_path") or None
    article_url = decision.get("article_url") or None
    result = publish_share(
        text=text,
        image_path=image_path,
        article_url=None if image_path else article_url,
        visibility=decision.get("visibility") or "PUBLIC",
    )

    thread_id = state.get("thread_id")
    if thread_id:
        write_artifact(thread_id, "linkedin_publish.json", result)

    return {
        "linkedin_publish_result": result,
        "status": "shipped",
        "pipeline_phase": "done",
    }
