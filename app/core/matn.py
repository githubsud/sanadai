"""Heuristic isnad/matn split. Returns a VERBATIM substring of the dataset text (never rewritten).

Used to improve matching (users quote the matn, not the chain) and to show a focused "original text".
The full text is always kept and shown alongside.
"""

import re

_MARKS = "[\u064B-\u065F\u0670\u0640\u06D6-\u06ED]*"


def _loose(word: str) -> str:
    """Regex matching `word` with optional diacritics after each letter and alef/yaa variants."""
    out = []
    for ch in word:
        if ch == " ":
            out.append(r"[\s\u200f]+")
            continue
        cls = {"ا": "[اأإآٱ]", "ى": "[ىي]", "ي": "[يى]", "ه": "[هة]"}.get(ch, re.escape(ch))
        out.append(cls + _MARKS)
    return "".join(out)


# The Prophet's honorific, in any common written form.
_PROPHET_HONORIFIC = re.compile("ﷺ|" + _loose("صلى الله عليه وسلم"))
# Speech introducers right after the honorific.
_SPEECH_INTRO = re.compile(r"^[\s\u200f\-ـ:،,]*(?:" + "|".join(
    _loose(w) for w in ("قال", "يقول", "فقال", "وقال", "قالت")
) + r")?[\s\u200f:،,]*")

# Opening/closing quotes as used by the datasets.
_QUOTES = '"“”«»'
_STRIP = " \u200f\u200e\t\n.:،,-\u0640" + _QUOTES


def extract_matn(text: str, min_len: int = 15) -> str | None:
    """Best-effort matn (verbatim substring). None if no confident split was found."""
    if not text:
        return None
    # 1) Quoted speech: from first opening quote to last closing quote.
    first = min((i for i in (text.find(q) for q in '"“«') if i >= 0), default=-1)
    last = max(text.rfind(q) for q in '"”»')
    if first >= 0 and last > first:
        span = text[first:last + 1].strip(_STRIP)
        if len(span) >= min_len:
            return span
    # 2) Text after the first Prophet honorific (+ optional "قال/يقول").
    m = _PROPHET_HONORIFIC.search(text)
    if m:
        rest = text[m.end():]
        intro = _SPEECH_INTRO.match(rest)
        rest = rest[intro.end():] if intro else rest
        rest = rest.strip(_STRIP)
        if len(rest) >= min_len:
            return rest
    return None
