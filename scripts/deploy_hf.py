"""Deploy SanadAI to Hugging Face: a dataset repo with the prebuilt data + a Docker Space with the app.

    python scripts/deploy_hf.py [--data] [--space] [--user NAME]     (default: both)

Reads HF_TOKEN and GEMINI_API_KEY from .env. Uploads ONLY git-tracked files to the Space (so .env and local
artifacts can never be published); the Gemini key is stored as a Space *secret*, never in files.
"""

import argparse
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from dotenv import dotenv_values
from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parent.parent

SPACE_VARIABLES = {
    "LLM_PROVIDER": "gemini",
    "GEMINI_MODEL": "gemini-3.8-flash",
    "GEMINI_FALLBACK_MODELS": "gemini-2.5-flash,gemini-flash-latest",
    "RATE_VERIFY_PER_HOUR": "60",
    "RATE_LLM_PER_HOUR": "20",
    "RATE_LLM_PER_DAY_GLOBAL": "500",
    "DORAR_TIMEOUT_S": "6",
}


def clean_db_copy(dst: Path) -> None:
    """Consistent copy of db/sanad.db without the `checks` table rows (no user data is published)."""
    src = sqlite3.connect(ROOT / "db" / "sanad.db")
    out = sqlite3.connect(dst)
    src.backup(out)
    src.close()
    out.execute("DELETE FROM checks")
    out.commit()
    out.execute("VACUUM")
    out.close()


def deploy_data(api: HfApi, repo: str) -> None:
    api.create_repo(repo, repo_type="dataset", exist_ok=True, private=False)
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        (t / "db").mkdir()
        clean_db_copy(t / "db" / "sanad.db")
        shutil.copytree(ROOT / "index" / "chroma", t / "index" / "chroma")
        (t / "README.md").write_text(
            "# SanadAI prebuilt data\n\nSQLite DB (Tanzil Quran, hadith collections, gradings, Dorar cache) and the "
            "Chroma vector index used by the SanadAI Space. Reproducible with `scripts/build_all` from "
            "https://github.com/githubsud/sanadai — see SOURCES.md there for every dataset's license and terms "
            "(Tanzil text is CC BY 3.0 and must not be modified).\n", encoding="utf-8")
        api.upload_folder(repo_id=repo, repo_type="dataset", folder_path=t,
                          commit_message="Upload prebuilt DB and vector index")
    print("data ->", f"https://huggingface.co/datasets/{repo}")


def deploy_space(api: HfApi, repo: str, gemini_key: str) -> None:
    api.create_repo(repo, repo_type="space", space_sdk="docker", exist_ok=True, private=False)
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    skip_prefixes = ("docs/screenshots/", "tests/fixtures/")
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        for f in tracked:
            if f.startswith(skip_prefixes) or f == ".env":
                continue
            (t / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / f, t / f)
        shutil.copy2(ROOT / "deploy" / "hf_space_README.md", t / "README.md")
        api.upload_folder(repo_id=repo, repo_type="space", folder_path=t, commit_message="Deploy SanadAI",
                          delete_patterns=["*"])
    for k, v in SPACE_VARIABLES.items():
        api.add_space_variable(repo, k, v)
    if gemini_key:
        api.add_space_secret(repo, "GEMINI_API_KEY", gemini_key)
    print("space ->", f"https://huggingface.co/spaces/{repo}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", action="store_true")
    ap.add_argument("--space", action="store_true")
    ap.add_argument("--user", default="huggingfacesud")
    a = ap.parse_args()
    env = dotenv_values(ROOT / ".env")
    token = (env.get("HF_TOKEN") or "").strip()
    if not token:
        print("HF_TOKEN missing in .env")
        return 1
    api = HfApi(token=token)
    both = not (a.data or a.space)
    if a.data or both:
        deploy_data(api, f"{a.user}/sanadai-data")
    if a.space or both:
        deploy_space(api, f"{a.user}/sanadai", (env.get("GEMINI_API_KEY") or "").strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
