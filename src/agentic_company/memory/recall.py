"""Memory recall node helpers."""

from __future__ import annotations

from typing import Any

from agentic_company.config import get_settings
from agentic_company.memory.store import get_memory_store


def recall_for_brief(brief: str) -> list[dict[str, Any]]:
    settings = get_settings()
    store = get_memory_store()
    return store.query(brief, top_k=settings.memory_top_k)
