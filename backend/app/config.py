"""Runtime configuration (environment-driven; see .env.example)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FIN04_", env_file=".env", extra="ignore")

    database_url: str = f"sqlite:///{BACKEND_DIR / 'fin04.db'}"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    log_level: str = "INFO"
    max_monte_carlo_runs: int = 5000
    max_page_size: int = 200
    run_cache_size: int = 64
    data_dir: Path = DATA_DIR
    # AI copilot: local Ollama by default; deterministic templates are always the fallback; Anthropic only if a key is set
    llm_provider: str = "ollama"                # ollama | anthropic | deterministic
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:8b"
    anthropic_api_key: SecretStr | None = None  # FIN04_ANTHROPIC_API_KEY; never exposed to the frontend
    anthropic_model: str = "claude-haiku-5-5"
    llm_timeout_s: float = 90.0

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
