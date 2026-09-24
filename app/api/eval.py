import json

from fastapi import APIRouter, HTTPException

from app.config import get_settings

router = APIRouter(prefix="/api", tags=["eval"])


@router.get("/eval/latest")
def latest() -> dict:
    s = get_settings()
    path = s.resolve(s.eval_results_path)
    if not path.exists():
        raise HTTPException(404, "no evaluation run yet (python scripts/run_eval.py)")
    return json.loads(path.read_text(encoding="utf-8"))
