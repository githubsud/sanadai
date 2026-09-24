"""Warm the permanent Dorar cache from data/seeds/circulating.txt so the demo works offline.

For every query: Dorar search (cached) + the «الصحيح البديل» page of the best hit (cached).
Writes data/seeds/seed_report.jsonl with exactly what Dorar returned, for the owner's review.

    python scripts/seed_dorar.py [--limit N]
"""

import argparse
import json
import sys
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.normalize import normalize_ar  # noqa: E402
from app.sources.dorar import DorarClient, DorarUnavailable  # noqa: E402

SEEDS = ROOT / "data" / "seeds" / "circulating.txt"
REPORT = ROOT / "data" / "seeds" / "seed_report.jsonl"


def load_seeds() -> list[tuple[str, str]]:
    out = []
    for line in SEEDS.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        q, _, status = line.partition("\t")
        out.append((q.strip(), status.strip() or "needs_review"))
    return out


def best_hit(query: str, hits):
    qn = normalize_ar(query)
    scored = [(SequenceMatcher(None, qn, normalize_ar(h.text), autojunk=False).ratio(), h) for h in hits]
    return max(scored, key=lambda x: x[0]) if scored else (0.0, None)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    seeds = load_seeds()[: a.limit]
    cli = DorarClient(offline=False)
    counts: dict[str, int] = {}
    with REPORT.open("w", encoding="utf-8") as rep:
        for i, (q, status) in enumerate(seeds, 1):
            row: dict = {"query": q, "review_status": status}
            try:
                hits = cli.search(q)
                sim, top = best_hit(q, hits)
                row["n_results"] = len(hits)
                if top:
                    row["top"] = {k: v for k, v in top.as_dict().items() if k != "text_norm"}
                    row["top_similarity"] = round(sim, 3)
                    counts[top.grade_class] = counts.get(top.grade_class, 0) + 1
                    if top.has_alternate and top.hadith_id:
                        alt = cli.alternate(top.hadith_id)
                        if alt:
                            row["alternate"] = {k: v for k, v in alt.as_dict().items() if k != "text_norm"}
                else:
                    counts["no_result"] = counts.get("no_result", 0) + 1
            except DorarUnavailable as e:
                row["error"] = str(e)
                counts["error"] = counts.get("error", 0) + 1
            rep.write(json.dumps(row, ensure_ascii=False) + "\n")
            top = row.get("top", {})
            print(f"[{i}/{len(seeds)}] {q[:40]:<40} -> {top.get('grade_class', row.get('error', '-'))} "
                  f"| {top.get('mohdith', '')} | {top.get('grade', '')[:40]}", flush=True)
    print("summary:", counts)
    print(f"report: {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
