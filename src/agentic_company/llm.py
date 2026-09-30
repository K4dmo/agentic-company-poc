"""LLM provider resolution: OpenAI, OpenRouter, or Cursor (OpenAI-compatible gateway)."""

from __future__ import annotations

from typing import Any, Literal

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel

from agentic_company.config import get_settings

Provider = Literal["openai", "openrouter", "cursor"]

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

DEFAULT_MODELS: dict[Provider, dict[str, str]] = {
    "openai": {
        "planner": "gpt-4.1-mini",
        "critic": "gpt-4.1-mini",
        "specialist": "gpt-4.1-mini",
        "builder": "gpt-4.1",
    },
    "openrouter": {
        "planner": "openai/gpt-4o-mini",
        "critic": "openai/gpt-4o-mini",
        "specialist": "openai/gpt-4o-mini",
        "builder": "openai/gpt-4o",
    },
    "cursor": {
        # Used with an OpenAI-compatible Cursor gateway (CURSOR_BASE_URL).
        "planner": "composer-2.5",
        "critic": "composer-2.5",
        "specialist": "composer-2.5",
        "builder": "composer-2.5",
    },
}


def resolve_provider() -> Provider:
    settings = get_settings()
    explicit = settings.llm_provider
    if explicit in {"openai", "openrouter", "cursor"}:
        return explicit  # type: ignore[return-value]

    # auto: prefer whichever key is present
    if settings.openrouter_api_key:
        return "openrouter"
    if settings.cursor_api_key:
        return "cursor"
    return "openai"


def has_llm_credentials() -> bool:
    settings = get_settings()
    provider = resolve_provider()
    if provider == "openrouter":
        return bool(settings.openrouter_api_key)
    if provider == "cursor":
        return bool(settings.cursor_api_key and settings.cursor_base_url)
    return bool(settings.openai_api_key)


def credentials_help() -> str:
    provider = resolve_provider()
    if provider == "openrouter":
        return (
            "Set OPENROUTER_API_KEY in .env (https://openrouter.ai/keys). "
            "Optional: LLM_PROVIDER=openrouter"
        )
    if provider == "cursor":
        return (
            "Cursor API keys are for Cloud Agents, not chat completions. "
            "To use CURSOR_API_KEY here, also set CURSOR_BASE_URL to an "
            "OpenAI-compatible gateway (e.g. http://127.0.0.1:8787/v1). "
            "Or use OPENROUTER_API_KEY / OPENAI_API_KEY instead."
        )
    return "Set OPENAI_API_KEY in .env (or OPENROUTER_API_KEY / CURSOR_API_KEY)."


def _strip_known_prefix(model: str) -> str:
    for prefix in ("openai:", "openrouter:", "cursor:"):
        if model.startswith(prefix):
            return model[len(prefix) :]
    return model


def resolve_model_name(role: str, configured: str) -> str:
    """Pick configured model, or provider default when still on openai:* leftovers."""
    provider = resolve_provider()
    defaults = DEFAULT_MODELS[provider]
    name = (configured or "").strip()
    if not name:
        return defaults[role]

    # If user left openai: defaults but switched provider, swap to provider defaults
    if provider != "openai" and name.startswith("openai:"):
        return defaults[role]
    if provider == "openai" and ("/" in name and not name.startswith("openai:")):
        # openrouter-style id while on openai provider — leave as-is (may fail)
        return _strip_known_prefix(name)
    return _strip_known_prefix(name)


def get_chat_model(role: str = "planner", *, model: str | None = None) -> BaseChatModel:
    """Build a chat model for a crew role using the active LLM provider."""
    settings = get_settings()
    provider = resolve_provider()

    configured = model
    if configured is None:
        configured = {
            "planner": settings.planner_model,
            "critic": settings.critic_model,
            "specialist": settings.specialist_model,
            "builder": settings.builder_model,
        }.get(role, settings.planner_model)

    model_name = resolve_model_name(role, configured or "")

    if provider == "openrouter":
        if not settings.openrouter_api_key:
            raise RuntimeError(credentials_help())
        return init_chat_model(
            model_name,
            model_provider="openai",
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url or OPENROUTER_BASE_URL,
            default_headers={
                "HTTP-Referer": settings.openrouter_http_referer or "https://github.com/K4dmo/agentic-company-poc",
                "X-Title": settings.openrouter_app_name or "agentic-company",
            },
        )

    if provider == "cursor":
        if not settings.cursor_api_key:
            raise RuntimeError(credentials_help())
        if not settings.cursor_base_url:
            raise RuntimeError(credentials_help())
        return init_chat_model(
            model_name,
            model_provider="openai",
            api_key=settings.cursor_api_key,
            base_url=settings.cursor_base_url.rstrip("/"),
        )

    if not settings.openai_api_key:
        raise RuntimeError(credentials_help())
    return init_chat_model(
        model_name,
        model_provider="openai",
        api_key=settings.openai_api_key,
    )


def embedding_config() -> dict[str, Any] | None:
    """Return OpenAI-compatible embedding settings for Chroma, if available."""
    settings = get_settings()
    provider = resolve_provider()
    if provider == "openrouter" and settings.openrouter_api_key:
        return {
            "api_key": settings.openrouter_api_key,
            "api_base": (settings.openrouter_base_url or OPENROUTER_BASE_URL).rstrip("/"),
            "model_name": "openai/text-embedding-3-small",
        }
    if provider == "openai" and settings.openai_api_key:
        return {
            "api_key": settings.openai_api_key,
            "api_base": None,
            "model_name": "text-embedding-3-small",
        }
    # Cursor gateways rarely expose embeddings — fall back to local chroma default
    return None
