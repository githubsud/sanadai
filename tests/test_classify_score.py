"""Pure unit tests for classify.py and score.py. Synthetic placeholder sentences only (not sacred texts)."""

import pytest

from app.core.classify import best_window, char_ratio, classify, compare, word_diff
from app.core.score import aggregate_grade, sanad_score

SRC = "هذه جملة تجريبية طويلة تستخدم لاختبار المطابقة بين النص المتداول والنص الاصلي في المصدر فقط"


def test_identical():
    assert compare(SRC, SRC).match_type == "identical"


def test_any_changed_word_is_altered_even_if_char_similarity_high():
    # one letter differs in a long text: char similarity > 0.95 but the word changed -> altered (with diff)
    c = compare(SRC.replace("فقط", "فقت"), SRC)
    assert c.similarity > 0.95 and c.match_type == "altered"


def test_hadith_mode_tolerates_leading_conjunction_only():
    src = "انما الكلمات التجريبيه بالمعاني وانما لكل جمله ما قصد"
    claim = "انما الكلمات التجريبيه بالمعاني انما لكل جمله ما قصد"
    assert compare(claim, src).match_type == "identical"
    assert compare(claim, src, strict=True).match_type == "altered"


def test_edge_insertions_tolerated():
    c = compare("قال " + "تستخدم لاختبار المطابقة بين النص", SRC)
    assert c.match_type == "partial" and c.diff[0]["op"] == "insert"


def test_partial_excerpt():
    excerpt = "تستخدم لاختبار المطابقة بين النص المتداول والنص الاصلي"
    c = compare(excerpt, SRC)
    assert c.match_type == "partial"
    assert SRC.split()[c.span[0]:c.span[1]] == excerpt.split()
    assert all(d["op"] == "equal" for d in c.diff)


def test_altered_word_substitution():
    altered = "تستخدم لاختبار الموافقه بين النص المتداول والنص الاصلي"
    c = compare(altered, SRC)
    assert c.match_type == "altered"
    rep = [d for d in c.diff if d["op"] == "replace"]
    assert rep and rep[0]["text"] == "الموافقه" and rep[0]["source"] == "المطابقة"


def test_altered_word_added():
    added = "تستخدم لاختبار المطابقة الدقيقه جدا بين النص المتداول"
    c = compare(added, SRC)
    assert c.match_type in ("altered", "partial")
    assert any(d["op"] == "insert" and "الدقيقه" in d["text"] for d in c.diff)


def test_not_found_unrelated():
    assert compare("كلام اخر لا علاقه له بالموضوع مطلقا", SRC).match_type == "not_found"


def test_too_short_claim_not_found():
    assert compare("النص", SRC).match_type == "not_found"


def test_same_language_paraphrase_needs_score_and_word_overlap():
    # high reranker score alone is not enough in the same language (unrelated proverbs can score > 0.9)
    assert classify("عباره مختلفه تماما في الالفاظ", {"text": SRC}, rerank=0.95).match_type == "not_found"
    claim = "تستخدم كثيرا جملة قصيرة بين الناس لاختبار الفهم في المصدر"  # 40% shared words, low similarity
    c = classify(claim, {"text": SRC}, rerank=0.95)
    assert c.match_type == "paraphrase" and c.diff == []
    assert classify(claim, {"text": SRC}, rerank=0.6).match_type == "not_found"


def test_cross_language_paraphrase_from_meaning_score():
    assert classify("completely different words", {"text": SRC}, rerank=0.6, cross_lang=True).match_type == "paraphrase"


def test_classify_prefers_best_reference():
    matn = "النص المتداول والنص الاصلي في المصدر"
    full = "حدثنا فلان عن فلان " + matn
    c = classify(matn, {"matn": matn, "text": full}, rerank=None)
    assert c.match_type == "identical" and c.reference == "matn"


def test_cross_language_never_identical_to_arabic():
    c = classify("seek knowledge", {"text": "seek knowledge"}, rerank=0.9, cross_lang=True)
    assert c.match_type == "paraphrase"
    c = classify("seek knowledge", {"en": "seek knowledge"}, rerank=0.9, cross_lang=True)
    assert c.match_type == "paraphrase" and c.translation_quote


def test_best_window_finds_excerpt():
    src = ("a b c d e f g h i j k l m n o p").split()
    s, e, r = best_window("f g h i".split(), src)
    assert (s, e) == (5, 9) and r == 1.0


def test_word_diff_ops():
    d = word_diff("a x c d".split(), "a b c".split())
    assert [x["op"] for x in d] == ["equal", "replace", "equal", "insert"]
    assert d[1] == {"op": "replace", "text": "x", "source": "b"}


def test_char_ratio_edges():
    assert char_ratio("", "x") == 0.0
    assert char_ratio("abc", "abc") == 1.0


# ---------------- score ----------------

@pytest.mark.parametrize(
    "claim_type,match,conf,grade,status,score",
    [
        ("hadith", "identical", 1.0, "sahih", "green", 100),
        ("hadith", "partial", 0.9, "hasan", "green", 81),
        ("hadith", "paraphrase", 0.8, "sahih", "amber", 77),
        ("hadith", "identical", 1.0, "daif", "amber", 75),
        ("hadith", "identical", 1.0, "unknown", "amber", 80),
        ("hadith", "altered", 0.9, "sahih", "amber", 71),
        ("hadith", "identical", 1.0, "mawdu", "red", 70),
        ("hadith", "identical", 0.3, "sahih", "amber", 72),
        ("hadith", "not_found", 0.0, "unknown", "red", 0),
        ("saying", "not_found", 0.0, "unknown", "amber", 0),
        ("quran", "identical", 1.0, "unknown", "green", 100),
        ("quran", "altered", 0.8, "unknown", "amber", 67),
        ("quran", "not_found", 0.0, "unknown", "red", 0),
    ],
)
def test_sanad_score_table(claim_type, match, conf, grade, status, score):
    r = sanad_score(claim_type, match, conf, grade)
    assert (r.status, r.score) == (status, score)


def test_cross_language_paraphrase_can_be_green_same_language_never():
    assert sanad_score("hadith", "paraphrase", 0.9, "sahih", cross_lang=True).status == "green"
    r = sanad_score("hadith", "paraphrase", 0.99, "sahih", cross_lang=False)
    assert r.status == "amber" and "meaning_only" in r.reasons
    assert sanad_score("quran", "paraphrase", 0.99, "unknown", cross_lang=False).status == "amber"


def test_score_bounds_and_determinism():
    for conf in (-1, 0, 0.5, 1, 2):
        r1 = sanad_score("hadith", "identical", conf, "sahih")
        r2 = sanad_score("hadith", "identical", conf, "sahih")
        assert 0 <= r1.score <= 100 and r1 == r2


def g(cls, source="x"):
    return {"grade_class": cls, "source": source}


@pytest.mark.parametrize(
    "grades,expected",
    [
        ([], "unknown"),
        ([g("sahih", "collection_inclusion")], "sahih"),
        ([g("sahih"), g("sahih"), g("daif")], "sahih"),
        ([g("sahih"), g("daif")], "daif"),            # tie -> more cautious
        ([g("hasan"), g("sahih")], "hasan"),
        ([g("mawdu"), g("daif")], "mawdu"),
        ([g("mawdu"), g("sahih"), g("sahih")], "sahih"),
        ([g("unknown")], "unknown"),
    ],
)
def test_aggregate_grade(grades, expected):
    assert aggregate_grade(grades) == expected
