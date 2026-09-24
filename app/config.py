"""Central configuration. Values come from environment / .env; thresholds live here so they can be tuned."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-5"

    db_path: Path = ROOT / "db" / "sanad.db"
    chroma_path: Path = ROOT / "index" / "chroma"
    web_dir: Path = ROOT / "web"
    eval_results_path: Path = ROOT / "data" / "eval" / "results.json"

    embed_model: str = "BAAI/bge-m3"
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    device: str = "auto"
    demo_subset: bool = True

    dorar_base_url: str = "https://dorar-hadith-api.vercel.app"
    dorar_offline: bool = False
    dorar_timeout_s: float = 8.0

    max_input_chars: int = 5000
    max_image_bytes: int = 5_000_000

    def resolve(self, p: Path) -> Path:
        return p if p.is_absolute() else ROOT / p

    @property
    def llm_configured(self) -> bool:
        return bool(self.anthropic_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
