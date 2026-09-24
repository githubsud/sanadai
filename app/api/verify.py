import asyncio
import base64
import binascii

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

from app.config import get_settings
from app.core import pipeline
from app.models import VerifyRequest, VerifyResponse

router = APIRouter(prefix="/api", tags=["verify"])


@router.post("/verify", response_model=VerifyResponse)
async def verify(req: VerifyRequest) -> VerifyResponse:
    s = get_settings()
    if not (req.text and req.text.strip()) and not req.image_base64:
        raise HTTPException(422, "provide text or image_base64")
    if req.image_base64:
        b64 = req.image_base64.split(",", 1)[-1] if req.image_base64.startswith("data:") else req.image_base64
        if len(b64) * 3 // 4 > s.max_image_bytes:
            raise HTTPException(413, f"image larger than {s.max_image_bytes // 1_000_000} MB")
        try:
            base64.b64decode(b64[:64] + "=" * (-len(b64[:64]) % 4), validate=True)
        except (binascii.Error, ValueError) as e:
            raise HTTPException(422, "image_base64 is not valid base64") from e
    # CPU-bound (retrieval, reranking): keep the event loop free; bound the wait.
    try:
        return await asyncio.wait_for(run_in_threadpool(pipeline.verify, req.text, req.image_base64, req.lang_hint),
                                      timeout=s.request_timeout_s)
    except TimeoutError as e:
        raise HTTPException(504, "verification took too long — try a shorter text") from e
