"""Unit tests for app.core.normalize. Samples are generic words or verbatim Tanzil lines (1:1, 1:2)."""

import pytest

from app.core.normalize import (
    collapse_spaces,
    detect_lang,
    normalize,
    normalize_ar,
    normalize_en,
    strip_diacritics,
    strip_honorifics,
    tokens,
    unify_letters,
)

# Verbatim from Tanzil uthmani / simple-clean (1:1, 1:2)
UTHMANI_1_1 = "بِسْمِ ٱللَّهِ ٱلرَّحْمَـٰنِ ٱلرَّحِيمِ"
CLEAN_1_1 = "بسم الله الرحمن الرحيم"
UTHMANI_1_2 = "ٱلْحَمْدُ لِلَّهِ رَبِّ ٱلْعَـٰلَمِينَ"
CLEAN_1_2 = "الحمد لله رب العالمين"


def test_uthmani_diacritics_stripped():
    assert normalize_ar(UTHMANI_1_1) == normalize_ar(CLEAN_1_1) == "بسم الله الرحمن الرحيم"


def test_uthmani_rasm_differs_so_matching_uses_simple_clean():
    # Uthmani orthography (dagger alef) is not recoverable by normalization: this is why text_norm is
    # built from Tanzil simple-clean, while text_uthmani is kept for display only.
    assert normalize_ar(UTHMANI_1_2) != normalize_ar(CLEAN_1_2)
    assert normalize_ar(CLEAN_1_2) == "الحمد لله رب العالمين"


def test_strip_diacritics_removes_harakat_and_tatweel():
    assert strip_diacritics("مُحَمَّـــدٌ") == "محمد"
    assert strip_diacritics("") == ""


def test_superscript_alef_removed():
    assert strip_diacritics("ٱلرَّحْمَـٰنِ") == "ٱلرحمن"


@pytest.mark.parametrize(
    "src,expected",
    [("أحمد", "احمد"), ("إسلام", "اسلام"), ("آمن", "امن"), ("ٱلله", "الله"),
     ("على", "علي"), ("رحمة", "رحمه"), ("مؤمن", "مومن"), ("سئل", "سيل"), ("١٢٣", "123")],
)
def test_unify_letters(src, expected):
    assert unify_letters(src) == expected


def test_punctuation_and_quotes_stripped():
    assert normalize_ar("«قال: نعم!» (هذا) — ذاك، وذلك؛ أليس كذلك؟") == "قال نعم هذا ذاك وذلك اليس كذلك"


def test_quranic_symbols_stripped():
    assert normalize_ar("۞ ذلك ۩") == "ذلك"


@pytest.mark.parametrize(
    "text",
    [
        "قال رسول الله ﷺ اصدق",
        "قال رسول الله صلى الله عليه وسلم اصدق",
        "قال رسولُ اللهِ صلَّى اللهُ عليهِ وسلَّمَ: اصدق",
        "قال رسول الله (صلى الله عليه وسلم) اصدق",
    ],
)
def test_honorifics_stripped(text):
    assert normalize_ar(text) == "قال رسول الله اصدق"


def test_companion_honorific_stripped():
    assert normalize_ar("عن أنس رضي الله عنه قال") == "عن انس قال"
    assert normalize_ar("عن عائشة رضي الله عنها قالت") == "عن عايشه قالت"


def test_honorifics_kept_when_disabled():
    assert normalize_ar("رضي الله عنهم ورضوا عنه", honorifics=False) == "رضي الله عنهم ورضوا عنه"
    assert normalize_ar("رضي الله عنهم ورضوا عنه") == "ورضوا عنه"


def test_honorific_only_matches_whole_words():
    # "عليه السلامة" must not lose "عليه السلام" partially
    assert strip_honorifics("عليه السلامه") == "عليه السلامه"


def test_zero_width_and_whitespace():
    assert normalize_ar("كلمة‏   أخرى\n\tثالثة﻿") == "كلمه اخري ثالثه"
    assert collapse_spaces("  a   b ") == "a b"


def test_empty_and_none_like():
    assert normalize_ar("") == ""
    assert normalize_en("") == ""
    assert tokens("") == []


def test_idempotent():
    once = normalize_ar(UTHMANI_1_1 + " ﷺ «x»")
    assert normalize_ar(once) == once


def test_normalize_en():
    assert normalize_en("The Prophet (ﷺ) said: \"Seek Knowledge!\"") == "the prophet said seek knowledge"
    assert normalize_en("Prophet (peace be upon him) said") == "prophet said"


def test_detect_lang():
    assert detect_lang("قال رسول الله") == "ar"
    assert detect_lang("The Prophet said") == "en"
    assert detect_lang("The Prophet ﷺ said") == "en"


def test_normalize_dispatch():
    assert normalize("أَحْمَد") == "احمد"
    assert normalize("Hello, World") == "hello world"
