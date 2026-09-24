"""Grade-label bucketing (labels taken from fawazahmed0/hadith-api info.json) and matn extraction.

Matn tests use obviously synthetic placeholder sentences («نص تجريبي ...»), never real hadith text.
"""

import pytest

from app.core.grades import classify_label_ar, classify_label_en, label_to_ar
from app.core.matn import extract_matn


@pytest.mark.parametrize(
    "label,cls",
    [
        ("Sahih", "sahih"), ("Hasan Sahih", "sahih"), ("Sahih Lighairihi", "sahih"),
        ("Isnaad Sahih", "sahih"), ("Sahih - Agreed Upon", "sahih"),
        ("Sahih Bukhari (1224) Sahih Muslim (570)", "sahih"),
        ("Hasan", "hasan"), ("Isnaad Hasan", "hasan"), ("Hasan Lighairihi", "hasan"),
        ("Daif", "daif"), ("Daif Isnaad", "daif"), ("Very Daif", "daif"), ("Munkar", "daif"),
        ("Shadh", "daif"), ("Mauquf Daif", "daif"), ("Sanad Daif", "daif"),
        ("Mawdu", "mawdu"), ("-", "unknown"), ("", "unknown"), ("Maqtu", "unknown"),
    ],
)
def test_classify_label_en(label, cls):
    assert classify_label_en(label) == cls


@pytest.mark.parametrize(
    "label,cls",
    [
        ("صحيح", "sahih"), ("إسناده صحيح", "sahih"), ("حسن صحيح", "sahih"), ("حسن", "hasan"),
        ("ضعيف", "daif"), ("ضعيف جداً", "daif"), ("إسناده ضعيف", "daif"), ("منكر", "daif"),
        ("موضوع", "mawdu"), ("لا أصل له", "mawdu"), ("باطل", "mawdu"),
        ("", "unknown"), ("انظر شرح الحديث", "unknown"),
    ],
)
def test_classify_label_ar(label, cls):
    assert classify_label_ar(label) == cls


def test_label_whole_word_only():
    # «الذين» contains no standalone grading term
    assert classify_label_ar("الذين") == "unknown"


def test_label_to_ar():
    assert label_to_ar("Sahih") == "صحيح"
    assert label_to_ar("hasan sahih") == "حسن صحيح"
    assert label_to_ar("Something custom") is None


SYN_CHAIN = "حَدَّثَنَا فُلَانٌ، عَنْ فُلَانٍ، قَالَ قَالَ رَسُولُ اللَّهِ صلى الله عليه وسلم "
SYN_BODY = "نص تجريبي للاختبار فقط وليس حديثا"


def test_matn_from_quotes():
    text = SYN_CHAIN + '‏"‏ ' + SYN_BODY + ' ‏"‏ ‏.‏ تعليق المصنف بعد النص'
    assert extract_matn(text) == SYN_BODY


def test_matn_after_honorific_without_quotes():
    text = "حدثنا فلان عن فلان أنه سمع رسول الله صَلَّى اللَّهُ عَلَيْهِ وَسَلَّمَ يَقُولُ : " + SYN_BODY
    assert extract_matn(text) == SYN_BODY


def test_matn_after_symbol_honorific():
    assert extract_matn("قال النبي ﷺ: " + SYN_BODY) == SYN_BODY


def test_matn_is_verbatim_substring():
    text = SYN_CHAIN + '"' + SYN_BODY + '"'
    m = extract_matn(text)
    assert m is not None and m in text


def test_matn_none_when_no_markers():
    assert extract_matn("نص بلا إسناد ولا علامات") is None
    assert extract_matn("") is None
