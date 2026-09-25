"""Download the prebuilt SQLite DB and vector index from a Hugging Face dataset repo (used by the Dockerfile).

    SANADAI_DATA_REPO=huggingfacesud/sanadai-data python scripts/fetch_space_data.py

The same artifacts are reproducible locally with scripts/build_all.ps1 / .sh.
"""

import os
import sys
from pathlib import Path

from huggingface_hub import snapshot_download

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    repo = os.environ.get("SANADAI_DATA_REPO", "huggingfacesud/sanadai-data")
    if (ROOT / "db" / "sanad.db").exists() and (ROOT / "index" / "chroma").exists():
        print("data present, skip")
        return 0
    snapshot_download(repo_id=repo, repo_type="dataset", local_dir=ROOT, allow_patterns=["db/*", "index/chroma/**"])
    print("downloaded", repo, "->", ROOT / "db", ROOT / "index" / "chroma")
    return 0


if __name__ == "__main__":
    sys.exit(main())
