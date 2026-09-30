"""Vector memory store — local Chroma with optional remote HTTP adapter."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Protocol

from agentic_company.config import get_settings


class MemoryStore(Protocol):
    def query(self, text: str, top_k: int = 3) -> list[dict[str, Any]]: ...

    def upsert(self, doc_id: str, text: str, metadata: dict[str, Any]) -> None: ...


class LocalChromaStore:
    def __init__(self) -> None:
        import chromadb
        from chromadb.utils import embedding_functions

        settings = get_settings()
        settings.memory_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(settings.memory_dir))

        from agentic_company.llm import embedding_config

        emb = embedding_config()
        if emb:
            kwargs: dict[str, Any] = {
                "api_key": emb["api_key"],
                "model_name": emb["model_name"],
            }
            if emb.get("api_base"):
                kwargs["api_base"] = emb["api_base"]
            ef = embedding_functions.OpenAIEmbeddingFunction(**kwargs)
            self._collection = self._client.get_or_create_collection(
                name="company_memory",
                embedding_function=ef,
            )
        else:
            # Deterministic local embeddings when no compatible embedding key
            self._collection = self._client.get_or_create_collection(name="company_memory")

    def query(self, text: str, top_k: int = 3) -> list[dict[str, Any]]:
        if not text.strip():
            return []
        try:
            result = self._collection.query(query_texts=[text], n_results=top_k)
        except Exception:  # noqa: BLE001
            return []
        docs = (result.get("documents") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        ids = (result.get("ids") or [[]])[0]
        hits: list[dict[str, Any]] = []
        for i, doc in enumerate(docs):
            meta = metas[i] if i < len(metas) else {}
            hits.append(
                {
                    "id": ids[i] if i < len(ids) else f"hit-{i}",
                    "text": doc,
                    "metadata": meta or {},
                }
            )
        return hits

    def upsert(self, doc_id: str, text: str, metadata: dict[str, Any]) -> None:
        clean_meta = {k: (v if isinstance(v, (str, int, float, bool)) else json.dumps(v)) for k, v in metadata.items()}
        self._collection.upsert(ids=[doc_id], documents=[text], metadatas=[clean_meta])


class RemoteMemoryStore:
    """Minimal HTTP JSON adapter: POST /query and POST /upsert."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            return {"error": str(exc), "hits": []}

    def query(self, text: str, top_k: int = 3) -> list[dict[str, Any]]:
        data = self._post("/query", {"text": text, "top_k": top_k})
        return list(data.get("hits") or [])

    def upsert(self, doc_id: str, text: str, metadata: dict[str, Any]) -> None:
        self._post("/upsert", {"id": doc_id, "text": text, "metadata": metadata})


_store: MemoryStore | None = None


def get_memory_store() -> MemoryStore:
    global _store
    if _store is not None:
        return _store
    settings = get_settings()
    if settings.memory_backend == "remote" and settings.memory_remote_url:
        _store = RemoteMemoryStore(settings.memory_remote_url)
    else:
        _store = LocalChromaStore()
    return _store
