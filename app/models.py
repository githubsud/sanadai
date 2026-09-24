"""Pydantic request/response models (API contract, spec 6.9)."""

from typing import Literal

from pydantic import BaseModel, Field

ClaimType = Literal["quran", "hadith", "saying"]
Status = Literal["green", "amber", "red"]
MatchType = Literal["identical", "partial", "altered", "paraphrase", "not_found"]


# ---------- LLM outputs (validated, P3) ----------

class ExtractedClaim(BaseModel):
    text: str = Field(min_length=2, max_length=2000)
    claim_type: ClaimType
    attributed_to: str | None = None
    lang: Literal["ar", "en"]


class ExtractionResult(BaseModel):
    claims: list[ExtractedClaim] = Field(max_length=20)


class OCRResult(BaseModel):
    text: str = Field(max_length=10000)


# ---------- API ----------

class VerifyRequest(BaseModel):
    text: str | None = Field(default=None, max_length=5000)
    image_base64: str | None = Field(default=None, description="PNG/JPEG/WebP, base64 (data: URL prefix allowed)")
    lang_hint: Literal["ar", "en"] | None = None


class DiffToken(BaseModel):
    op: Literal["equal", "insert", "delete", "replace"]
    text: str
    source: str | None = None


class Grading(BaseModel):
    grade_ar: str | None = None
    grade_en: str | None = None
    grade_class: str = "unknown"
    grader: str
    reference: str | None = None
    source: str


class SourceRef(BaseModel):
    kind: Literal["hadith", "dorar"] = "hadith"
    hadith_id: int | None = None
    collection: str | None = None
    collection_en: str | None = None
    number: str | None = None
    book: str | None = None
    narrator: str | None = None
    text_ar: str                     # verbatim from the dataset / Dorar
    text_ar_full: str | None = None  # full text incl. isnad (local datasets)
    text_en: str | None = None
    url: str | None = None
    provider: str


class AyahRef(BaseModel):
    surah: int
    surah_name_ar: str
    surah_name_en: str
    ayah_start: int
    ayah_end: int
    surah_end: int
    ref: str
    text_uthmani: str                # verbatim Tanzil
    text_clean: str
    text_en: str | None = None
    url: str
    source: str
    other_occurrences: list[str] = []


class Alternative(BaseModel):
    origin: str
    text_ar: str
    text_en: str | None = None
    source: dict
    gradings: list[Grading]
    grade_class: str
    hadith_id: int | None = None
    meaning_score: float | None = None


class TraceStep(BaseModel):
    step: str            # extract | retrieve | quran_match | dorar | classify | grade | score | alternatives
    label_ar: str
    label_en: str
    status: Literal["ok", "skipped", "degraded", "error"] = "ok"
    ms: float = 0.0
    detail: dict = {}


class ClaimResult(BaseModel):
    index: int
    claim_text: str
    claim_type: ClaimType
    attributed_to: str | None = None
    lang: Literal["ar", "en"]
    status: Status
    sanad_score: int
    match_type: MatchType
    match_confidence: float
    reasons: list[str] = []
    grade_class: str = "unknown"
    diff: list[DiffToken] = []
    source: SourceRef | None = None
    ayah: AyahRef | None = None
    gradings: list[Grading] = []
    alternatives: list[Alternative] = []
    evidence_trace: list[TraceStep] = []
    notes: list[str] = []
    summary_ar: str = ""
    summary_en: str = ""


class VerifyResponse(BaseModel):
    check_id: str
    input_text: str
    input_lang: Literal["ar", "en"]
    extraction_method: Literal["llm", "rules"]
    claims: list[ClaimResult]
    evidence_trace: list[TraceStep] = []
    notes: list[str] = []
    disclaimer_ar: str = "النتيجة مطابقة للمصادر ومقتبسة منها، وليست حكمًا شرعيًا من النظام."
    disclaimer_en: str = "Results quote and match sources; the system does not issue religious rulings."


class PrepareRequest(BaseModel):
    check_id: str
    output_lang: Literal["ar", "en"] = "ar"


class PreparedPost(BaseModel):
    check_id: str
    output_lang: Literal["ar", "en"]
    text: str
    sources: list[str]
    replacements: list[dict]
    validated: bool
    validation_errors: list[str] = []
