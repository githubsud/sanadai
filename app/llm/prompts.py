"""Prompts and JSON schemas for the (narrow) LLM tasks: claim extraction and OCR (P3)."""

EXTRACT_SYSTEM = """You extract religious claims from a social-media post so they can be checked against sources.

Rules:
- Find every Quran verse, hadith (a saying/action attributed to the Prophet Muhammad ﷺ), and saying attributed to a
  companion, scholar or other figure.
- `text` MUST be copied VERBATIM, character for character, from the post: the quoted/attributed words only, without
  the attribution phrase ("قال رسول الله ﷺ", "The Prophet said", "قال تعالى"), without surrounding quotes, and without
  added commentary. Never correct, complete, translate, or rewrite a text - copy exactly what the post says.
- `claim_type`: "quran" for verses, "hadith" for anything attributed to the Prophet ﷺ (including hadith qudsi),
  "saying" for words attributed to anyone else or of unclear attribution.
- `attributed_to`: the person/source the post names, copied from the post (e.g. "رسول الله ﷺ", "Ali"), else null.
- `lang`: "ar" or "en" - the language of `text`.
- If there is no religious claim, return an empty list.
- Do not judge authenticity and do not add any information that is not in the post."""

EXTRACT_USER = "Post:\n<<<\n{post}\n>>>"

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "claim_type": {"type": "string", "enum": ["quran", "hadith", "saying"]},
                    "attributed_to": {"type": ["string", "null"]},
                    "lang": {"type": "string", "enum": ["ar", "en"]},
                },
                "required": ["text", "claim_type", "attributed_to", "lang"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["claims"],
    "additionalProperties": False,
}

OCR_SYSTEM = """You transcribe the text visible in an image (typically a social-media screenshot) exactly as written.
Copy Arabic and English text verbatim, keep diacritics and punctuation as shown, keep line order.
Do not translate, correct, complete or comment. Omit UI chrome (buttons, like counts, timestamps, usernames)."""

OCR_USER = "Transcribe the post text in this image."

OCR_SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
    "additionalProperties": False,
}
