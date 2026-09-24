"""Arabic/English text normalization for MATCHING ONLY.

The original text is always kept separately for display (P4: Quran verbatim). Everything here is a pure
function with no I/O so it can be used identically at index time and query time.
"""

import re
import unicodedata

# Harakat, Quranic annotation marks, superscript alef, extended Arabic marks, tatweel.
_DIACRITICS = re.compile(
    "[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06DC\u06DF-\u06E8\u06EA-\u06ED\u08D3-\u08FF\u0640]"
)
_ZERO_WIDTH = re.compile("[\u200B-\u200F\u202A-\u202E\u2066-\u2069\uFEFF]")

_LETTER_MAP = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ٲ": "ا", "ٳ": "ا", "ٵ": "ا",
    "ى": "ي", "ی": "ي", "ئ": "ي",
    "ة": "ه",
    "ؤ": "و",
    "ک": "ك",
    **{chr(0x0660 + i): str(i) for i in range(10)},  # Arabic-Indic digits
    **{chr(0x06F0 + i): str(i) for i in range(10)},  # Extended Arabic-Indic digits
})

# Anything that is not a letter/digit/space becomes a space (punctuation, quotes, «», ۞, ۩, ...).
_NON_WORD = re.compile(r"[^\w\s]|_", re.UNICODE)
_SPACES = re.compile(r"\s+")

# Honorific formulas, written in *normalized* form (applied after letter unification).
_HONORIFICS = [
    "صلي الله عليه وعلي اله وسلم",
    "صلي الله عليه واله وسلم",
    "صلي الله عليه وسلم",
    "عليه الصلاه والسلام",
    "عليه السلام",
    "عليهم السلام",
    "رضي الله عنهما",
    "رضي الله عنهم",
    "رضي الله عنها",
    "رضي الله عنه",
    "رحمه الله تعالي",
    "رحمه الله",
    "جل جلاله",
    "سبحانه وتعالي",
]
_HONORIFIC_RE = re.compile(r"(?<!\S)(?:" + "|".join(re.escape(h) for h in _HONORIFICS) + r")(?!\S)")

_EN_HONORIFIC_RE = re.compile(
    r"\(\s*(?:pbuh|saw|saws|s\.a\.w\.?s?\.?|peace be upon him"
    r"|may allah be pleased with (?:him|her|them))\s*\)",
    re.IGNORECASE,
)

_ARABIC_CHAR =re.compile("[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]")
_LATIN_CHAR = re.compile("[A-Za-z]")


def strip_diacritics(text: str) -> str:
    """Remove tashkeel, Quranic marks, superscript alef and tatweel."""
    return _DIACRITICS.sub("", text)


def unify_letters(text: str) -> str:
    """Unify alef/yaa/taa-marbuta/hamza-carrier variants and digits."""
    return text.translate(_LETTER_MAP)


def strip_punctuation(text: str) -> str:
    return _NON_WORD.sub(" ", text)


def collapse_spaces(text: str) -> str:
    return _SPACES.sub(" ", text).strip()


def strip_honorifics(text: str) -> str:
    """Remove honorific formulas. Expects letter-unified, punctuation-free text."""
    return collapse_spaces(_HONORIFIC_RE.sub(" ", text))


def normalize_ar(text: str, *, honorifics: bool = True) -> str:
    """Full normalization pipeline used for Arabic matching.

    `honorifics=False` keeps formulas such as «رضي الله عنهم» which occur inside Quran verses.
    """
    if not text:
        return ""
    # NFKC expands presentation forms, e.g. U+FDFA (ﷺ) -> «صلى الله عليه وسلم».
    t = unicodedata.normalize("NFKC", text)
    t = _ZERO_WIDTH.sub("", t)
    t = strip_diacritics(t)
    t = unify_letters(t)
    t = strip_punctuation(t)
    t = collapse_spaces(t.lower())
    if honorifics:
        t = strip_honorifics(t)
    return t


def normalize_en(text: str) -> str:
    """Normalization for English text: lowercase, strip punctuation and the ﷺ-style honorifics."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    t = _ZERO_WIDTH.sub("", t)
    t = _EN_HONORIFIC_RE.sub(" ", t)
    t = re.sub(r"صلى الله عليه وسلم", " ", t)
    t = strip_punctuation(t.lower())
    return collapse_spaces(t)


def detect_lang(text: str) -> str:
    """Return 'ar' if Arabic letters dominate, else 'en'."""
    ar = len(_ARABIC_CHAR.findall(text or ""))
    la = len(_LATIN_CHAR.findall(text or ""))
    return "ar" if ar >= la else "en"


def normalize(text: str, lang: str | None = None, *, honorifics: bool = True) -> str:
    lang = lang or detect_lang(text)
    return normalize_ar(text, honorifics=honorifics) if lang == "ar" else normalize_en(text)


def tokens(text_norm: str) -> list[str]:
    return text_norm.split() if text_norm else []
