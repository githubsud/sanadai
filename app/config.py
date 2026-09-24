"""Central configuration. Values come from environment / .env; thresholds live here so they can be tuned."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str = ""
    llm_model: str = "claude-opus-5"

    db_path: Path = ROOT / "db" / "sanad.db"
    chroma_path: Path = ROOT / "index" / "chroma"
    web_dir: Path = ROOT / "web"
    eval_results_path: Path = ROOT / "data" / "eval" / "results.json"

    embed_model: str = "BAAI/bge-m3"
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    device: str = "auto"
    model_backend: str = "auto"  # auto | onnx | torch
    demo_subset: bool = True
    use_dense: bool = True
    use_reranker: bool = True

    # retrieval
    rrf_k: int = 60
    lexical_k: int = 50
    dense_k: int = 50
    fuse_top: int = 20
    rerank_top: int = 10  # CPU latency budget; set 20 on GPU
    keep_top: int = 5
    weak_match_threshold: float = 0.5  # best rerank score below this -> "weak" -> consult Dorar

    # classification thresholds (spec 6.5; tuned on the eval set in Phase 8)
    th_identical: float = 0.95
    th_partial_span: float = 0.90
    th_partial_coverage: float = 0.60
    th_altered: float = 0.60
    th_paraphrase_rerank: float = 0.50       # cross-language meaning match
    th_paraphrase_same_lang: float = 0.90    # same-language meaning match needs a higher score ...
    th_paraphrase_overlap: float = 0.40      # ... and this share of the claim's words in the source
    th_low_confidence: float = 0.50  # below this a sahih/hasan match is only amber

    dorar_base_url: str = "https://dorar-hadith-api.vercel.app"
    dorar_offline: bool = False
    dorar_timeout_s: float = 8.0

    max_input_chars: int = 5000
    request_timeout_s: float = 180.0
    warm_up: bool = True
    max_image_bytes: int = 5_000_000

    def resolve(self, p: Path) -> Path:
        return p if p.is_absolute() else ROOT / p

    @property
    def llm_configured(self) -> bool:
        return bool(self.anthropic_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
