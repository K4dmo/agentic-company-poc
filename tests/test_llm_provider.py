"""Provider resolution tests (no network)."""

from __future__ import annotations

import os

import pytest

from agentic_company import config, llm


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


def test_auto_prefers_openrouter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "auto")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setenv("CURSOR_API_KEY", "crsr_test")
    config.get_settings.cache_clear()
    assert llm.resolve_provider() == "openrouter"
    assert llm.has_llm_credentials() is True


def test_cursor_needs_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "cursor")
    monkeypatch.setenv("CURSOR_API_KEY", "crsr_test")
    monkeypatch.delenv("CURSOR_BASE_URL", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config.get_settings.cache_clear()
    assert llm.resolve_provider() == "cursor"
    assert llm.has_llm_credentials() is False


def test_cursor_with_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "cursor")
    monkeypatch.setenv("CURSOR_API_KEY", "crsr_test")
    monkeypatch.setenv("CURSOR_BASE_URL", "http://127.0.0.1:8787/v1")
    config.get_settings.cache_clear()
    assert llm.has_llm_credentials() is True


def test_openrouter_model_defaults_when_openai_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("PLANNER_MODEL", "openai:gpt-4.1-mini")
    config.get_settings.cache_clear()
    assert llm.resolve_model_name("planner", "openai:gpt-4.1-mini") == "openai/gpt-4o-mini"
