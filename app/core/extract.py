"""Claim extraction: LLM (structured JSON, Pydantic-validated, one retry) with a rule-based fallback (P3).

Every extracted claim text must exist verbatim in the input (whitespace-insensitive); anything the LLM returns
that is not in the post is dropped, so the LLM can never inject sacred text.
"""

import base64
import logging
import re
from dataclasses import dataclass

from pydantic import ValidationError

from app.core.normalize import detect_lang
from app.llm import prompts
from app.llm.provider import LLMError, get_provider
from app.models import ExtractedClaim, ExtractionResult, OCRResult

log = logging.getLogger(__name__)


@dataclass
class Extraction:
    claims: list[ExtractedClaim]
    method: str                 # "llm" | "rules"
    notes: list[str]


# ---------------- verbatim guard ----------------

def _ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def find_verbatim(span: str, text: str) -> str | None:
    """Return the exact substring of `text` equal to `span` modulo whitespace, else None."""
    span = _ws(span).strip("«»\"“”'")
    if not span:
        return None
    pattern = r"\s+".join(re.escape(p) for p in span.split(" "))
    m = re.search(pattern, text)
    return m.group(0) if m else None


# ---------------- rule-based extractor ----------------

_PROPHET_CUES = [
    r"رسول\s*الله", r"النبي", r"النبى", r"ﷺ", r"صلى\s*الله\s*عليه\s*وسلم", r"صلّى\s*الله", r"المصطفى",
    r"\bprophet\b", r"\bmessenger\b", r"\bpbuh\b",
]
_QURAN_CUES = [
    r"قال\s*(?:الله\s*)?تعالى", r"قال\s*الله", r"يقول\s*الله", r"قوله\s*تعالى", r"الله\s*عز\s*وجل\s*(?:يقول|قال)",
    r"في\s*كتابه", r"\bqur'?an\b", r"\ballah\s+(?:says|said)\b", r"\bgod\s+says\b", r"\bsurah\b",
]
_SAYING_CUES = [r"\bقال\b", r"\bيقول\b", r"\bsaid\b", r"\bsays\b"]
_QUOTE_PAIRS = [("﴿", "﴾"), ("«", "»"), ("“", "”"), ('"', '"'), ("❝", "❞")]
_SENT_END = re.compile(r"[.!؟?\n]")
_CUE_THEN_SPEECH = re.compile(
    r"(?P<cue>(?:قال|يقول|قالت)\s+(?:رسول\s*الله|النبي|النبى)[^:،\n]{0,40}?|"
    r"(?:قال|يقول)\s+(?:الله\s+)?تعالى|"
    r"the\s+(?:prophet|messenger(?:\s+of\s+allah)?)[^:\n]{0,30}?\s+said|allah\s+says)\s*[:：]?\s*",
    re.IGNORECASE,
)


_NAMED_SPEAKER = re.compile(r"(?:قال|قالت|يقول|يقال عن)\s+(?P<who>[^:«\"“﴿\n]{2,40}?)\s*[:：]?\s*$")


def _last_pos(patterns: list[str], ctx: str) -> tuple[int, str | None]:
    best, found = -1, None
    for p in patterns:
        for m in re.finditer(p, ctx, re.I):
            if m.start() > best:
                best, found = m.start(), m.group(0)
    return best, found


def _cue_type(context: str, bracket: str | None) -> tuple[str, str | None]:
    """Classify a claim from the text right before it; the NEAREST cue wins."""
    if bracket == "﴿":
        return "quran", "القرآن"
    ctx = context[-80:]
    q_pos, _ = _last_pos(_QURAN_CUES, ctx)
    h_pos, h_cue = _last_pos(_PROPHET_CUES, ctx)
    if q_pos < 0 and h_pos < 0:
        m = _NAMED_SPEAKER.search(ctx)
        return "saying", (m.group("who").strip(" ،,") if m else None)
    if q_pos > h_pos:
        return "quran", "القرآن"
    return "hadith", ("النبي ﷺ" if detect_lang(ctx) == "ar" else "the Prophet ﷺ")


def rule_extract(text: str) -> list[ExtractedClaim]:
    claims: list[ExtractedClaim] = []
    used: list[tuple[int, int]] = []

    def add(start: int, end: int, ctype: str, who: str | None):
        span = text[start:end].strip(" \t\n:：،,.")
        if len(span) < 6 or any(s < end and start < e for s, e in used):
            return
        used.append((start, end))
        claims.append(ExtractedClaim(text=span, claim_type=ctype, attributed_to=who, lang=detect_lang(span)))

    # 1) quoted spans
    for open_q, close_q in _QUOTE_PAIRS:
        pos = 0
        while (i := text.find(open_q, pos)) >= 0:
            j = text.find(close_q, i + 1)
            if j < 0:
                break
            prev_end = max((e for _, e in used if e <= i), default=0)
            ctype, who = _cue_type(text[prev_end:i], open_q)
            add(i + 1, j, ctype, who)
            pos = j + 1
    # 2) cue followed by speech without quotes (up to the end of the sentence)
    for m in _CUE_THEN_SPEECH.finditer(text):
        start = m.end()
        if any(s <= start < e for s, e in used):
            continue
        end_m = _SENT_END.search(text, start + 5)
        end = end_m.start() if end_m else len(text)
        ctype, who = _cue_type(m.group("cue"), None)
        add(start, end, ctype, who)
    # 3) nothing found: a short post is checked as one claim of unknown attribution ("saying"); the pipeline
    #    re-types it if it matches a verse or hadith, and a miss is "not found", never "fabricated".
    if not claims and 6 <= len(text.strip()) <= 600:
        claims.append(ExtractedClaim(text=text.strip(), claim_type="saying", attributed_to=None,
                                     lang=detect_lang(text)))
    claims.sort(key=lambda c: text.find(c.text))
    return claims[:20]


# ---------------- LLM extractor ----------------

def _validated(post: str, raw: dict) -> list[ExtractedClaim]:
    result = ExtractionResult.model_validate(raw)
    out: list[ExtractedClaim] = []
    for c in result.claims:
        exact = find_verbatim(c.text, post)
        if exact is None:
            log.warning("dropping non-verbatim LLM claim: %r", c.text[:60])
            continue
        out.append(c.model_copy(update={"text": exact}))
    return out


def extract_claims(post: str) -> Extraction:
    provider = get_provider()
    notes: list[str] = []
    if provider.available:
        content = [{"type": "text", "text": prompts.EXTRACT_USER.format(post=post)}]
        for attempt in (1, 2):
            try:
                raw = provider.json(prompts.EXTRACT_SYSTEM, content, prompts.EXTRACT_SCHEMA, max_tokens=4096)
                claims = _validated(post, raw)
                if claims or not raw.get("claims"):
                    return Extraction(claims, "llm", notes)
                notes.append("llm_claims_not_verbatim")
            except (LLMError, ValidationError) as e:
                log.warning("LLM extraction attempt %d failed: %s", attempt, e)
                notes.append(f"llm_attempt_{attempt}_failed")
    else:
        notes.append("llm_not_configured")
    return Extraction(rule_extract(post), "rules", notes)


# ---------------- OCR ----------------

_DATA_URL = re.compile(r"^data:(image/[a-z+]+);base64,", re.I)


def sniff_media_type(raw: bytes) -> str | None:
    if raw.startswith(b"\x89PNG"):
        return "image/png"
    if raw[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    if raw[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return None


def ocr_image(image_b64: str) -> str:
    """Transcribe text from an image with the vision model. Raises LLMError / ValueError."""
    image_b64 = _DATA_URL.sub("", image_b64.strip())
    raw = base64.b64decode(image_b64, validate=False)
    media = sniff_media_type(raw)
    if not media:
        raise ValueError("unsupported image format (use PNG, JPEG, WebP or GIF)")
    provider = get_provider()
    if not provider.available:
        raise LLMError("image reading needs ANTHROPIC_API_KEY")
    content = [
        {"type": "image", "source": {"type": "base64", "media_type": media, "data": base64.b64encode(raw).decode()}},
        {"type": "text", "text": prompts.OCR_USER},
    ]
    last: Exception | None = None
    for _ in (1, 2):
        try:
            return OCRResult.model_validate(provider.json(prompts.OCR_SYSTEM, content, prompts.OCR_SCHEMA)).text
        except (LLMError, ValidationError) as e:
            last = e
    raise LLMError(f"OCR failed: {last}")
