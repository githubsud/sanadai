"""Deterministic mapping of grading LABELS (as written by the grader in the dataset) to a coarse class.

This never creates a grading: it only buckets an existing, quoted label so the traffic light can be
computed. The original label and grader are always shown verbatim.
"""

import re

from app.core.normalize import normalize_ar

GRADE_CLASSES = ("sahih", "hasan", "daif", "mawdu", "unknown")

# Standard hadith-science terms: English transliteration label -> Arabic term.
# Used only to display the Arabic name of a label that exists in the dataset (not a new ruling).
LABEL_AR = {
    "sahih": "صحيح",
    "hasan": "حسن",
    "daif": "ضعيف",
    "very daif": "ضعيف جدا",
    "mawdu": "موضوع",
    "maudu": "موضوع",
    "hasan sahih": "حسن صحيح",
    "sahih lighairihi": "صحيح لغيره",
    "hasan lighairihi": "حسن لغيره",
    "isnaad sahih": "إسناده صحيح",
    "sahih isnaad": "إسناده صحيح",
    "isnaad hasan": "إسناده حسن",
    "hasan isnaad": "إسناده حسن",
    "daif isnaad": "إسناده ضعيف",
    "isnaad daif": "إسناده ضعيف",
    "munkar": "منكر",
    "shadh": "شاذ",
}

_EN_PATTERNS = [
    ("mawdu", re.compile(r"\b(mawdu|maudu|mawdoo|fabricated|mawḍūʿ)\w*", re.I)),
    ("daif", re.compile(r"\b(da'?if|daeef|weak|munkar|shadh|matruk)\b", re.I)),
    ("sahih", re.compile(r"\b(sahih|saheeh|authentic|agreed upon)\b", re.I)),
    ("hasan", re.compile(r"\b(hasan|good)\b", re.I)),
]

# Arabic phrases (normalized). Order of checks matters: fabricated > weak > sahih > hasan.
_AR_MAWDU = ("موضوع", "مكذوب", "كذب", "كذاب", "باطل", "لا اصل له", "ليس له اصل", "ليس بحديث", "لا اصل له مرفوعا")
_AR_DAIF = ("ضعيف", "ضعيف جدا", "منكر", "شاذ", "واه", "متروك", "مرسل", "منقطع", "فيه ضعف", "لين",
            "لا يصح", "لا يثبت", "اسناده ضعيف")
_AR_SAHIH = ("صحيح", "اسناده صحيح", "رجاله ثقات", "متفق عليه", "اخرجه البخاري", "اخرجه مسلم")
_AR_HASAN = ("حسن",)


def classify_label_en(label: str) -> str:
    if not label or not label.strip(" -"):
        return "unknown"
    low = label.lower()
    if "hasan sahih" in low:
        return "sahih"
    hits = [(m.start(), cls) for cls, rx in _EN_PATTERNS if (m := rx.search(low))]
    if not hits:
        return "unknown"
    if any(c == "mawdu" for _, c in hits):
        return "mawdu"
    return min(hits)[1]  # earliest term wins: "Daif Isnaad" -> daif, "Isnaad Sahih" -> sahih


def _find_word(text: str, phrase: str) -> int:
    """Position of `phrase` as whole words in space-separated `text`, or -1."""
    i = f" {text} ".find(f" {phrase} ")
    return i


def classify_label_ar(label: str) -> str:
    t = normalize_ar(label or "")
    if not t:
        return "unknown"
    if any(_find_word(t, p) >= 0 for p in _AR_MAWDU):
        return "mawdu"
    if _find_word(t, "حسن صحيح") >= 0:
        return "sahih"
    hits = []
    for cls, phrases in (("daif", _AR_DAIF), ("sahih", _AR_SAHIH), ("hasan", _AR_HASAN)):
        pos = [i for p in phrases if (i := _find_word(t, p)) >= 0]
        if pos:
            hits.append((min(pos), cls))
    if not hits:
        return "unknown"
    return min(hits)[1]


def label_to_ar(label_en: str) -> str | None:
    return LABEL_AR.get((label_en or "").strip().lower())
