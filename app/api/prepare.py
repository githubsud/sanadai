from fastapi import APIRouter, HTTPException

from app.core import pipeline
from app.core.prepare import prepare
from app.db import repo
from app.models import PreparedPost, PrepareRequest

router = APIRouter(prefix="/api", tags=["prepare"])


@router.post("/prepare", response_model=PreparedPost)
def prepare_post(req: PrepareRequest) -> PreparedPost:
    result = repo.get_check(req.check_id)
    post = pipeline.recall_post(req.check_id)
    if result is None or post is None:
        # The post text is only held in memory (never stored): re-run /api/verify after a restart.
        raise HTTPException(404, "check not found or expired — verify the text again")
    p = prepare(post, result["claims"], req.output_lang)
    return PreparedPost(check_id=req.check_id, output_lang=req.output_lang, text=p.text, sources=p.sources,
                        replacements=p.replacements, validated=p.validated, validation_errors=p.validation_errors)
