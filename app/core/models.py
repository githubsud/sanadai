"""Lazy singletons for the embedding model and reranker.

Backends:
  onnx  - int8 ONNX graphs of the same BAAI weights in models/ (scripts/fetch_models.py). Default on CPU.
  torch - original PyTorch models from the HF hub. Default on CUDA/MPS (fp16 on CUDA).
"""

import logging
import threading
from functools import lru_cache
from pathlib import Path

from app.config import ROOT, get_settings

log = logging.getLogger(__name__)
_lock = threading.Lock()

EMBED_MAX_SEQ = 256
RERANK_MAX_LEN = 320
ONNX_FILE = "onnx/model_int8.onnx"
ONNX_DIRS = {"embed": ROOT / "models" / "bge-m3-onnx", "rerank": ROOT / "models" / "bge-reranker-v2-m3-onnx"}


def pick_device() -> str:
    pref = get_settings().device.lower()
    if pref != "auto":
        return pref
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def backend_for(kind: str) -> str:
    pref = get_settings().model_backend.lower()
    onnx_ready = (ONNX_DIRS[kind] / ONNX_FILE).exists()
    if pref == "onnx" or (pref == "auto" and pick_device() == "cpu" and onnx_ready):
        if not onnx_ready:
            raise RuntimeError(f"ONNX model missing in {ONNX_DIRS[kind]} (run scripts/fetch_models.py)")
        return "onnx"
    return "torch"


def _source(kind: str) -> tuple[str | Path, dict]:
    if backend_for(kind) == "onnx":
        return str(ONNX_DIRS[kind]), {"backend": "onnx", "model_kwargs": {"file_name": ONNX_FILE}, "device": "cpu"}
    s = get_settings()
    dev = pick_device()
    mid = s.embed_model if kind == "embed" else s.rerank_model
    kwargs: dict = {"device": dev}
    if dev == "cuda" and kind == "rerank":
        kwargs["model_kwargs"] = {"torch_dtype": "float16"}
    return mid, kwargs


@lru_cache
def embedder():
    from sentence_transformers import SentenceTransformer

    with _lock:
        src, kwargs = _source("embed")
        log.info("loading embedder %s (%s)", src, kwargs.get("backend", kwargs.get("device")))
        m = SentenceTransformer(src, **kwargs)
        m.max_seq_length = EMBED_MAX_SEQ
        if kwargs.get("device") == "cuda":
            m.half()
        return m


@lru_cache
def reranker():
    from sentence_transformers import CrossEncoder

    with _lock:
        src, kwargs = _source("rerank")
        log.info("loading reranker %s (%s)", src, kwargs.get("backend", kwargs.get("device")))
        return CrossEncoder(src, max_length=RERANK_MAX_LEN, **kwargs)


def describe() -> dict:
    try:
        return {"device": pick_device(), "embed_backend": backend_for("embed"), "rerank_backend": backend_for("rerank")}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def embed(texts: list[str], batch_size: int = 16) -> list[list[float]]:
    vecs = embedder().encode(texts, batch_size=batch_size, normalize_embeddings=True, show_progress_bar=False)
    return vecs.tolist()


def rerank(query: str, docs: list[str], batch_size: int = 10) -> list[float]:
    """Relevance in [0, 1] (sigmoid of the cross-encoder logit)."""
    if not docs:
        return []
    import torch

    scores = reranker().predict([(query, d) for d in docs], batch_size=batch_size,
                                activation_fn=torch.nn.Sigmoid(), show_progress_bar=False)
    return [float(s) for s in scores]
