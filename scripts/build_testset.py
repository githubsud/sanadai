"""Build data/eval/testset.jsonl deterministically (seeded) from the sources — no invented religious text.

Categories (~120 items):
  authentic  40  Bukhari/Muslim matn from the DB: identical, partial excerpt, dataset English translation,
                 and "altered" (one word dropped by the builder -> expected amber)
  weak_fab   40  circulating phrasings from data/seeds/circulating.txt whose Dorar top hit matched (seed report);
                 expected status from the top hit's verdict class (silver label, needs owner review)
  quran      20  Tanzil verses/ranges: exact, excerpt, one word replaced by a marked test token, English translation
  no_basis   20  well-known proverbs / sayings (not religious texts) falsely attributed to the Prophet ﷺ
Every item carries `label_basis` and `review_status: needs_review` until the owner reviews it.
"""

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.normalize import normalize_ar  # noqa: E402
from app.db import repo  # noqa: E402

OUT = ROOT / "data" / "eval" / "testset.jsonl"
SEED_REPORT = ROOT / "data" / "seeds" / "seed_report.jsonl"
rng = random.Random(7)
TEST_TOKEN = "كلمةتجريبية"  # marked, obviously-not-Quranic token used for the deliberate alterations

# Proverbs / common sayings (not hadith, not Quran) — popularly misattributed; used as "no basis" probes.
NO_BASIS = [
    ("ar", "العقل السليم في الجسم السليم"),
    ("ar", "الوقت كالسيف إن لم تقطعه قطعك"),
    ("ar", "من جد وجد ومن زرع حصد"),
    ("ar", "خير جليس في الزمان كتاب"),
    ("ar", "العلم نور والجهل ظلام"),
    ("ar", "إذا كان الكلام من فضة فالسكوت من ذهب"),
    ("ar", "درهم وقاية خير من قنطار علاج"),
    ("ar", "لكل مقام مقال"),
    ("ar", "من شب على شيء شاب عليه"),
    ("ar", "الحاجة أم الاختراع"),
    ("ar", "كل إناء بما فيه ينضح"),
    ("ar", "ما حك جلدك مثل ظفرك"),
    ("ar", "لا تؤجل عمل اليوم إلى الغد"),
    ("ar", "رب أخ لك لم تلده أمك"),
    ("ar", "العين لا تعلو على الحاجب"),
    ("ar", "اطلب العلا تسهر الليالي"),
    ("en", "Cleanliness is next to godliness"),
    ("en", "God helps those who help themselves"),
    ("en", "An apple a day keeps the doctor away"),
    ("en", "Knowledge is power"),
]


def _quoted_speech(r) -> bool:
    """Matn taken from quoted prophetic speech: a quote mark right before it and none inside it."""
    i = r["text_ar"].find(r["matn_ar"])
    return i > 0 and '"' in r["text_ar"][max(0, i - 4):i] and '"' not in r["matn_ar"] and "قَالَ" not in r["matn_ar"][:12]


def authentic(items: list[dict]) -> None:
    rows = repo.conn().execute(
        "SELECT id, collection, number, text_ar, matn_ar, matn_norm, text_en FROM hadiths "
        "WHERE collection IN ('bukhari','muslim') AND matn_ar IS NOT NULL "
        "AND instr(matn_ar, 'حَدَّثَنَا') = 0 AND instr(matn_ar, 'أَخْبَرَنَا') = 0 ORDER BY id").fetchall()
    rows = [r for r in rows if 8 <= len(r["matn_norm"].split()) <= 30 and _quoted_speech(r)]
    seen, pool = set(), []
    for r in rows:
        if r["matn_norm"] not in seen:
            seen.add(r["matn_norm"])
            pool.append(r)
    rng.shuffle(pool)

    def ids_with(norm: str) -> list[int]:
        return [x[0] for x in repo.conn().execute(
            "SELECT id FROM hadiths WHERE instr(text_norm, ?) > 0 LIMIT 50", (norm,))]

    plan = [("identical", 15), ("partial", 10), ("english", 8), ("altered", 7)]
    k = 0
    for kind, n in plan:
        made = 0
        while made < n:
            r = pool[k]
            k += 1
            words = r["matn_ar"].split()
            if kind == "identical":
                text, inp, status, match = r["matn_ar"], f"قال رسول الله ﷺ: «{r['matn_ar']}»", "green", "identical"
            elif kind == "partial":
                cut = max(5, int(len(words) * 0.6))
                text = " ".join(words[:cut]).rstrip("،,")
                inp, status, match = f"قال رسول الله ﷺ: «{text}»", "green", "partial"
            elif kind == "english":
                en = (r["text_en"] or "").strip()
                if ":" in en[:80]:
                    en = en.split(":", 1)[1].strip()
                if not en or len(en.split()) > 60:
                    continue
                text, inp, status, match = en, en, "green", "paraphrase"
            else:
                drop = len(words) // 2
                text = " ".join(words[:drop] + words[drop + 1:])
                inp, status, match = f"قال رسول الله ﷺ: «{text}»", "amber", "altered"
            same_text = ids_with(normalize_ar(text)) if kind in ("identical", "partial") else []
            acceptable = sorted(set([r["id"]] + same_text))
            items.append({"id": f"auth-{kind}-{made + 1:02d}", "category": "authentic", "variant": kind,
                          "input": inp, "lang": "en" if kind == "english" else "ar", "expected_type": "hadith",
                          "expected_status": status, "expected_match": match,
                          "expected_source_id": f"hadith:{r['id']}",
                          "expected_source_ids": [f"hadith:{i}" for i in acceptable],
                          "label_basis": f"{r['collection']} {r['number']} (dataset text; builder variant '{kind}')",
                          "review_status": "needs_review"})
            made += 1


def weak_fabricated(items: list[dict]) -> None:
    rows = [json.loads(line) for line in SEED_REPORT.read_text(encoding="utf-8").splitlines() if line.strip()]
    good = [r for r in rows if (r.get("top") or {}).get("grade_class") in ("daif", "mawdu")
            and r.get("top_similarity", 0) >= 0.9 and r["top"].get("hadith_id")]
    mawdu = [r for r in good if r["top"]["grade_class"] == "mawdu"][:20]
    daif = [r for r in good if r["top"]["grade_class"] == "daif"][: 40 - len(mawdu)]
    for n, r in enumerate(mawdu + daif, 1):
        t = r["top"]
        items.append({"id": f"weak-{n:02d}", "category": "weak_fabricated", "variant": t["grade_class"],
                      "input": f"قال رسول الله ﷺ: «{r['query']}»", "lang": "ar", "expected_type": "hadith",
                      "expected_status": "red" if t["grade_class"] == "mawdu" else "amber",
                      "expected_source_id": f"dorar:{t['hadith_id']}",
                      "expected_source_ids": [f"dorar:{t['hadith_id']}"],
                      "label_basis": f"Dorar top hit: {t['mohdith']} — «{t['grade']}» "
                                     f"({t['book']} {t['number_or_page']})",
                      "review_status": "needs_review"})


def quran(items: list[dict]) -> None:
    ayahs = [a for a in (repo.get_ayah_by_id(i) for i in range(1, 6237))]
    short = [a for a in ayahs if 5 <= len(a["text_clean"].split()) <= 20]
    long_ = [a for a in ayahs if len(a["text_clean"].split()) >= 14]
    rng.shuffle(short)
    rng.shuffle(long_)

    def add(kind, inp, lang, status, match, ref, basis):
        items.append({"id": f"quran-{kind}-{sum(1 for i in items if i['id'].startswith('quran-' + kind)) + 1:02d}",
                      "category": "quran", "variant": kind, "input": inp, "lang": lang, "expected_type": "quran",
                      "expected_status": status, "expected_match": match, "expected_source_id": f"ayah:{ref}",
                      "expected_source_ids": [f"ayah:{ref}"], "label_basis": basis, "review_status": "needs_review"})

    for a in short[:7]:
        add("exact", f"قال تعالى: ﴿{a['text_clean']}﴾", "ar", "green", "identical", f"{a['surah']}:{a['ayah']}",
            "Tanzil simple-clean, verbatim")
    pairs = [a for a in short[7:] if a["id"] < 6236 and repo.get_ayah_by_id(a["id"] + 1)["surah"] == a["surah"]][:3]
    for a in pairs:
        b = repo.get_ayah_by_id(a["id"] + 1)
        add("exact", f"قال تعالى: ﴿{a['text_clean']} {b['text_clean']}﴾", "ar", "green", "identical",
            f"{a['surah']}:{a['ayah']}-{b['ayah']}", "Tanzil simple-clean, two consecutive verses")
    for a in long_[:4]:
        w = a["text_clean"].split()
        add("excerpt", f"﴿{' '.join(w[2:-2])}﴾", "ar", "green", "partial", f"{a['surah']}:{a['ayah']}",
            "Tanzil simple-clean, excerpt (edges trimmed by builder)")
    for a in long_[4:8]:
        w = a["text_clean"].split()
        w[len(w) // 2] = TEST_TOKEN
        add("altered", f"قال تعالى: ﴿{' '.join(w)}﴾", "ar", "amber", "altered", f"{a['surah']}:{a['ayah']}",
            f"Tanzil simple-clean with one word replaced by the marked test token {TEST_TOKEN}")
    for a in [x for x in short[10:] if x["text_en"] and len(x["text_en"].split()) >= 8][:2]:
        add("english", f"Allah says in the Quran: \"{a['text_en']}\"", "en", "green", "paraphrase",
            f"{a['surah']}:{a['ayah']}", "Saheeh International translation (Tanzil)")


def no_basis(items: list[dict]) -> None:
    for n, (lang, s) in enumerate(NO_BASIS, 1):
        inp = f"قال رسول الله ﷺ: «{s}»" if lang == "ar" else f"The Prophet ﷺ said: \"{s}\""
        items.append({"id": f"nobasis-{n:02d}", "category": "no_basis", "variant": lang, "input": inp, "lang": lang,
                      "expected_type": "hadith", "expected_status": "red", "expected_match": "not_found",
                      "label_basis": "common proverb/saying, attributed to the Prophet ﷺ in the input",
                      "review_status": "needs_review"})


def main() -> int:
    items: list[dict] = []
    authentic(items)
    weak_fabricated(items)
    quran(items)
    no_basis(items)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    from collections import Counter
    print(len(items), "items", dict(Counter(i["category"] for i in items)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
