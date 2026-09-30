"""Runtime configuration loaded from environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    planner_model: str
    critic_model: str
    specialist_model: str
    builder_model: str
    builder_backend: str
    runs_dir: Path
    max_builder_retries: int
    builder_max_turns: int
    test_timeout_seconds: int
    memory_backend: str
    memory_remote_url: str
    memory_top_k: int
    web_host: str
    web_port: int
    eval_mode: bool

    @property
    def checkpoints_db(self) -> Path:
        return self.runs_dir / "checkpoints.db"

    @property
    def memory_dir(self) -> Path:
        return self.runs_dir / "memory"

    def run_dir(self, thread_id: str) -> Path:
        return self.runs_dir / thread_id

    def workspace_dir(self, thread_id: str) -> Path:
        return self.run_dir(thread_id) / "workspace"

    def artifacts_dir(self, thread_id: str) -> Path:
        return self.run_dir(thread_id) / "artifacts"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    runs = Path(os.getenv("RUNS_DIR", "runs"))
    if not runs.is_absolute():
        runs = PROJECT_ROOT / runs

    backend = os.getenv("BUILDER_BACKEND", "native").strip().lower()
    if backend not in {"native", "deepagents"}:
        backend = "native"

    memory_backend = os.getenv("MEMORY_BACKEND", "local").strip().lower()
    if memory_backend not in {"local", "remote"}:
        memory_backend = "local"

    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        planner_model=os.getenv("PLANNER_MODEL", "openai:gpt-4.1-mini"),
        critic_model=os.getenv("CRITIC_MODEL", "openai:gpt-4.1-mini"),
        specialist_model=os.getenv("SPECIALIST_MODEL", "openai:gpt-4.1-mini"),
        builder_model=os.getenv("BUILDER_MODEL", "openai:gpt-4.1"),
        builder_backend=backend,
        runs_dir=runs,
        max_builder_retries=int(os.getenv("MAX_BUILDER_RETRIES", "3")),
        builder_max_turns=int(os.getenv("BUILDER_MAX_TURNS", "25")),
        test_timeout_seconds=int(os.getenv("TEST_TIMEOUT_SECONDS", "60")),
        memory_backend=memory_backend,
        memory_remote_url=os.getenv("MEMORY_REMOTE_URL", "").strip(),
        memory_top_k=int(os.getenv("MEMORY_TOP_K", "3")),
        web_host=os.getenv("WEB_HOST", "127.0.0.1"),
        web_port=int(os.getenv("WEB_PORT", "8000")),
        eval_mode=os.getenv("EVAL_MODE", "").lower() in {"1", "true", "yes"},
    )


def ensure_run_dirs(thread_id: str) -> tuple[Path, Path]:
    settings = get_settings()
    workspace = settings.workspace_dir(thread_id)
    artifacts = settings.artifacts_dir(thread_id)
    workspace.mkdir(parents=True, exist_ok=True)
    artifacts.mkdir(parents=True, exist_ok=True)
    settings.memory_dir.mkdir(parents=True, exist_ok=True)
    settings.runs_dir.mkdir(parents=True, exist_ok=True)
    return workspace, artifacts
