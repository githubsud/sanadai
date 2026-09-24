"""Deterministic Sanad Score (0..100) and traffic light.

The score expresses MATCH & EVIDENCE CONFIDENCE — how sure we are that the circulating text corresponds to the
cited source and what the quoted graders said. It is NOT a religious ruling.

    score = round(40 * match_confidence + TYPE_WEIGHT[match_type] + GRADE_WEIGHT[grade])
"""

from collections import Counter
from dataclasses import dataclass, field

from app.config import get_settings

TYPE_WEIGHT = {"identical": 30, "partial": 20, "paraphrase": 15, "altered": 5, "not_found": 0}
GRADE_WEIGHT = {"sahih": 30, "hasan": 25, "daif": 5, "mawdu": 0, "unknown": 10, "quran": 30}
# More cautious class wins ties when aggregating graders.
CAUTION_ORDER = ["mawdu", "daif", "unknown", "hasan", "sahih"]


@dataclass
class ScoreResult:
    score: int
    status: str                       # green | amber | red
    grade_class: str
    reasons: list[str] = field(default_factory=list)   # machine-readable reason codes for the UI


def aggregate_grade(gradings: list[dict]) -> str:
    """Summarise several quoted gradings into one class, deterministically.

    - inclusion in Sahih al-Bukhari / Sahih Muslim -> sahih
    - otherwise the majority class among graders with a known class; ties go to the more cautious class
    - if any grader rates it fabricated / baseless and NO grader authenticates it (sahih/hasan) -> mawdu
      (cautious for publishing; every verdict is still quoted)
    """
    if not gradings:
        return "unknown"
    classes = [g.get("grade_class", "unknown") for g in gradings]
    if any(g.get("source") == "collection_inclusion" for g in gradings):
        return "sahih"
    known = [c for c in classes if c != "unknown"]
    if not known:
        return "unknown"
    counts = Counter(known)
    if counts.get("mawdu") and not (counts.get("sahih") or counts.get("hasan")):
        return "mawdu"
    if counts.get("mawdu") and counts["mawdu"] * 2 >= len(known):
        return "mawdu"
    top = max(counts.values())
    tied = [c for c, n in counts.items() if n == top]
    return min(tied, key=CAUTION_ORDER.index)


def sanad_score(claim_type: str, match_type: str, confidence: float, grade_class: str,
                attributed_to_prophet: bool = True) -> ScoreResult:
    """claim_type: quran | hadith | saying."""
    s = get_settings()
    conf = max(0.0, min(1.0, confidence or 0.0))
    if match_type == "not_found":
        conf = 0.0
    grade = "quran" if (claim_type == "quran" and match_type != "not_found") else grade_class
    score = round(40 * conf + TYPE_WEIGHT.get(match_type, 0) + GRADE_WEIGHT.get(grade, 10))
    if match_type == "not_found":
        score = 0
    score = max(0, min(100, score))
    reasons: list[str] = []

    if match_type == "not_found":
        reasons.append("not_found")
        if claim_type == "quran" or (claim_type == "hadith" and attributed_to_prophet):
            return ScoreResult(score, "red", grade_class, reasons + ["no_basis_in_sources"])
        return ScoreResult(score, "amber", grade_class, reasons)

    if claim_type == "quran":
        if match_type == "altered":
            return ScoreResult(score, "amber", "quran", ["quran_wording_altered"])
        if conf < s.th_low_confidence and match_type == "paraphrase":
            return ScoreResult(score, "amber", "quran", ["low_confidence"])
        return ScoreResult(score, "green", "quran", ["quran_verified"])

    if grade_class == "mawdu":
        return ScoreResult(score, "red", grade_class, ["graded_fabricated"])
    if match_type == "altered":
        reasons.append("wording_altered")
    if grade_class == "daif":
        reasons.append("graded_weak")
    elif grade_class == "unknown":
        reasons.append("grade_unknown")
    if conf < s.th_low_confidence:
        reasons.append("low_confidence")
    if reasons:
        return ScoreResult(score, "amber", grade_class, reasons)
    return ScoreResult(score, "green", grade_class, ["verified"])
