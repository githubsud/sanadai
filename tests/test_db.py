"""Integrity tests on the built database (skipped if not built)."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.normalize import normalize_ar
from app.db import repo
from app.main import app

RAW = Path(__file__).resolve().parent.parent / "data" / "raw" / "tanzil"
client = TestClient(app)


def test_counts(db_ready):
    c = repo.conn()
    assert c.execute("SELECT COUNT(*) FROM ayahs").fetchone()[0] == 6236
    assert c.execute("SELECT COUNT(*) FROM hadiths").fetchone()[0] > 35000
    assert c.execute("SELECT COUNT(DISTINCT collection) FROM hadiths").fetchone()[0] == 10


def test_quran_text_is_verbatim_tanzil(db_ready):
    """P4: stored Uthmani text must be byte-identical to the Tanzil file."""
    import xml.etree.ElementTree as ET

    raw = {}
    for sura in ET.parse(RAW / "quran-uthmani.xml").getroot().iter("sura"):
        for aya in sura.iter("aya"):
            raw[(int(sura.get("index")), int(aya.get("index")))] = aya.get("text")
    for sid, aid, text in repo.conn().execute("SELECT surah, ayah, text_uthmani FROM ayahs"):
        assert raw[(sid, aid)] == text


def test_bismillah_kept_separate(db_ready):
    assert repo.get_ayah(112, 1)["text_clean"] == "قل هو الله أحد"
    assert repo.get_ayah(112, 1)["bismillah"]
    assert repo.get_ayah(1, 1)["bismillah"] is None and repo.get_ayah(9, 1)["bismillah"] is None


def test_grade_classes_valid(db_ready):
    classes = {r[0] for r in repo.conn().execute("SELECT DISTINCT grade_class FROM gradings")}
    assert classes <= {"sahih", "hasan", "daif", "mawdu", "unknown"}


def test_every_grading_has_grader_and_source(db_ready):
    n = repo.conn().execute("SELECT COUNT(*) FROM gradings WHERE grader = '' OR source = ''").fetchone()[0]
    assert n == 0


def test_matn_is_verbatim_substring(db_ready):
    bad = repo.conn().execute(
        "SELECT COUNT(*) FROM hadiths WHERE matn_ar IS NOT NULL AND instr(text_ar, matn_ar) = 0").fetchone()[0]
    assert bad == 0


def test_fts_ayah_lookup(db_ready):
    a = repo.get_ayah(1, 2)
    hits = repo.fts_ayahs(a["text_norm"], limit=5)
    assert a["id"] in [h for h, _ in hits]


def test_fts_hadith_finds_itself(db_ready):
    row = repo.conn().execute("SELECT id, matn_ar FROM hadiths WHERE collection='bukhari' AND matn_ar IS NOT NULL "
                              "ORDER BY id LIMIT 1 OFFSET 100").fetchone()
    hits = repo.fts_hadiths(normalize_ar(row["matn_ar"]), limit=10)
    assert row["id"] in [h for h, _ in hits]


def test_lookup_endpoints(db_ready):
    r = client.get("/api/ayah/112/1")
    assert r.status_code == 200 and r.json()["surah_name_ar"] == "الإخلاص"
    assert client.get("/api/ayah/115/1").status_code == 404
    hid = repo.conn().execute("SELECT id FROM hadiths WHERE collection='bukhari' LIMIT 1").fetchone()[0]
    body = client.get(f"/api/hadith/{hid}").json()
    assert body["collection"] == "bukhari" and body["gradings"]
    assert body["gradings"][0]["source"] == "collection_inclusion"


def test_text_exists_verbatim(db_ready):
    a = repo.get_ayah(2, 255)
    assert repo.text_exists_verbatim(a["text_uthmani"][:40])
    assert not repo.text_exists_verbatim("نص تجريبي غير موجود في أي مصدر ١٢٣")
