from fastapi import APIRouter, HTTPException

from app.db import repo

router = APIRouter(prefix="/api", tags=["lookup"])


@router.get("/hadith/{hadith_id}")
def hadith(hadith_id: int) -> dict:
    h = repo.get_hadith(hadith_id)
    if not h:
        raise HTTPException(404, "hadith not found")
    h.pop("text_norm", None)
    h.pop("matn_norm", None)
    return h


@router.get("/ayah/{surah}/{ayah}")
def ayah(surah: int, ayah: int) -> dict:
    a = repo.get_ayah(surah, ayah)
    if not a:
        raise HTTPException(404, "ayah not found")
    a.pop("text_norm", None)
    a["source"] = "Tanzil Quran Text (Uthmani v1.1) — tanzil.net, CC BY 3.0"
    a["url"] = f"https://tanzil.net/#{surah}:{ayah}"
    return a
