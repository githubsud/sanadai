"""Fetch int8-quantized ONNX versions of BAAI/bge-m3 and BAAI/bge-reranker-v2-m3 for fast CPU inference.

Each local model dir = the official BAAI config/tokenizer/pooling files + an int8 ONNX graph of the SAME weights
exported by the ONNX community (Xenova/bge-m3, onnx-community/bge-reranker-v2-m3-ONNX). Listed in SOURCES.md.
Why: fp32 models (2.2 GB each) swap on 8 GB laptops; int8 ONNX is ~570 MB each and several times faster.
On a GPU machine set MODEL_BACKEND=torch and skip this step.
"""

import shutil
import sys
from pathlib import Path

from huggingface_hub import hf_hub_download, snapshot_download

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
ONNX_FILE = "onnx/model_int8.onnx"

TARGETS = [
    # local dir, official repo (config/tokenizer), onnx repo
    ("bge-m3-onnx", "BAAI/bge-m3", "Xenova/bge-m3"),
    ("bge-reranker-v2-m3-onnx", "BAAI/bge-reranker-v2-m3", "onnx-community/bge-reranker-v2-m3-ONNX"),
]
CONFIG_PATTERNS = ["*.json", "sentencepiece.bpe.model", "1_Pooling/*", "2_Normalize/*"]


def main() -> int:
    for local, official, onnx_repo in TARGETS:
        out = MODELS / local
        if (out / ONNX_FILE).exists():
            print(f"skip {local}: present")
            continue
        print(f"{local}: config/tokenizer from {official}", flush=True)
        snapshot_download(official, local_dir=out, allow_patterns=CONFIG_PATTERNS)
        print(f"{local}: int8 graph from {onnx_repo}", flush=True)
        hf_hub_download(onnx_repo, ONNX_FILE, local_dir=out)
        shutil.rmtree(out / ".cache", ignore_errors=True)
        print(f"  ok {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
