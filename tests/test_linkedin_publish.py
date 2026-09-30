"""LinkedIn Share API helpers and publish gate (offline)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from agentic_company.graph import route_after_linkedin_gate
from agentic_company.linkedin_client import create_ugc_post, publish_share
from agentic_company.nodes.linkedin_publish import (
    _compose_post_text,
    linkedin_gate_node,
    linkedin_publish_node,
)


def test_route_after_linkedin_gate() -> None:
    assert (
        route_after_linkedin_gate({"pipeline_phase": "linkedin_revise"})
        == "linkedin_gate"
    )
    assert (
        route_after_linkedin_gate(
            {"pipeline_phase": "linkedin_publish", "linkedin_publish_decision": {"action": "approve"}}
        )
        == "linkedin_publish"
    )
    assert (
        route_after_linkedin_gate(
            {"pipeline_phase": "done", "linkedin_publish_decision": {"action": "skip"}}
        )
        == "memory_write"
    )


def test_compose_post_text_from_package(tmp_path: Path) -> None:
    post_id = "post-01"
    folder = tmp_path / "linkedin_posts" / post_id
    folder.mkdir(parents=True)
    (folder / "body.txt").write_text("Body copy here.", encoding="utf-8")
    (folder / "post.json").write_text(
        json.dumps({"hook": "Hook line", "body": "Body copy here."}),
        encoding="utf-8",
    )
    text = _compose_post_text({"post_id": post_id}, tmp_path)
    assert "Hook line" in text
    assert "Body copy here." in text


def test_linkedin_gate_skips_in_eval_mode(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("EVAL_MODE", "true")
    from agentic_company.config import get_settings

    get_settings.cache_clear()
    try:
        result = linkedin_gate_node(
            {
                "workspace_root": str(tmp_path),
                "thread_id": "t1",
                "linkedin_announce": {
                    "post_id": None,
                    "hook": "Hello",
                    "body": "World",
                    "pr_url": "https://example.com/pr/1",
                },
            }
        )
        assert result["linkedin_publish_result"]["skipped"] is True
        assert result["pipeline_phase"] == "done"
    finally:
        get_settings.cache_clear()


def test_linkedin_publish_node_calls_client(tmp_path: Path) -> None:
    with patch(
        "agentic_company.nodes.linkedin_publish.publish_share",
        return_value={"ok": True, "ugc_post_id": "urn:li:share:1"},
    ) as mock_pub:
        result = linkedin_publish_node(
            {
                "workspace_root": str(tmp_path),
                "thread_id": None,
                "linkedin_publish_decision": {
                    "action": "approve",
                    "text": "Ship it",
                    "image_path": None,
                    "article_url": "https://example.com",
                    "visibility": "PUBLIC",
                },
            }
        )
    mock_pub.assert_called_once()
    assert result["linkedin_publish_result"]["ok"] is True


def test_publish_share_requires_token(monkeypatch) -> None:
    monkeypatch.delenv("LINKEDIN_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("LINKEDIN_OAUTH_TOKEN", raising=False)
    out = publish_share(text="hi")
    assert out["ok"] is False
    assert "LINKEDIN_ACCESS_TOKEN" in out["error"]


def test_create_ugc_post_text_payload() -> None:
    captured: dict = {}

    def fake_request(method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["payload"] = kwargs.get("payload")
        return 201, {"X-RestLi-Id": "urn:li:share:99"}, b""

    with patch("agentic_company.linkedin_client._request", side_effect=fake_request):
        result = create_ugc_post(
            text="Hello LinkedIn",
            person_urn="urn:li:person:abc",
            visibility="PUBLIC",
        )
    assert result["ok"] is True
    assert result["ugc_post_id"] == "urn:li:share:99"
    share = captured["payload"]["specificContent"]["com.linkedin.ugc.ShareContent"]
    assert share["shareCommentary"]["text"] == "Hello LinkedIn"
    assert share["shareMediaCategory"] == "NONE"


def test_create_ugc_post_with_image_asset() -> None:
    captured: dict = {}

    def fake_request(method, url, **kwargs):
        captured["payload"] = kwargs.get("payload")
        return 201, {"X-RestLi-Id": "urn:li:share:100"}, b""

    with patch("agentic_company.linkedin_client._request", side_effect=fake_request):
        create_ugc_post(
            text="With image",
            person_urn="urn:li:person:abc",
            image_asset="urn:li:digitalmediaAsset:XYZ",
        )
    share = captured["payload"]["specificContent"]["com.linkedin.ugc.ShareContent"]
    assert share["shareMediaCategory"] == "IMAGE"
    assert share["media"][0]["media"] == "urn:li:digitalmediaAsset:XYZ"
