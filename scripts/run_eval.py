"""Run the evaluation set through the real pipeline and write metrics.

    python scripts/run_eval.py [--limit N] [--lexical-only] [--only CATEGORY]

Offline & reproducible: Dorar is read from the permanent cache (DORAR_OFFLINE), extraction uses the rule-based
extractor unless an ANTHROPIC_API_KEY is configured. Outputs:
  data/eval/results.json       metrics (served by GET /api/eval/latest)
  data/eval/predictions.jsonl  one line per item (expected vs predicted, timings)
  docs/EVALUATION.md           human-readable report
"""

import argparse
import json
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.core import models as ml  # noqa: E402
from app.core.normalize import normalize  # noqa: E402
from app.core.pipeline import verify  # noqa: E402
from app.db import repo  # noqa: E402
from app.sources import dorar  # noqa: E402

TESTSET = ROOT / "data" / "eval" / "testset.jsonl"
RESULTS = ROOT / "data" / "eval" / "results.json"
PREDS = ROOT / "data" / "eval" / "predictions.jsonl"
REPORT = ROOT / "docs" / "EVALUATION.md"
STATUSES = ["green", "amber", "red"]
_QUOTED = re.compile(r"[«\"“﴿](.+?)[»\"”﴾]", re.S)


def core_text(inp: str) -> str:
    m = _QUOTED.search(inp)
    return m.group(1) if m else inp


def overlap(a: str, b: str) -> float:
    ta, tb = set(normalize(a).split()), set(normalize(b).split())
    return len(ta & tb) / max(1, len(tb))


def pred_source_id(c: dict) -> str | None:
    if c.get("ayah"):
        return f"ayah:{c['ayah']['ref']}"
    s = c.get("source")
    if not s:
        return None
    if s.get("kind") == "dorar":
        m = re.search(r"/h/([A-Za-z0-9]+)", s.get("url") or "")
        return f"dorar:{m.group(1)}" if m else None
    return f"hadith:{s['hadith_id']}"


def _ayah_range(ref: str) -> tuple[int, int, int]:
    surah, rng = ref.split(":", 1)
    a, _, b = rng.partition("-")
    return int(surah), int(a), int(b or a)


def same_source(pred: str | None, expected: list[str]) -> bool:
    if not pred:
        return False
    if pred in expected:
        return True
    if pred.startswith("ayah:"):
        ps, pa, pb = _ayah_range(pred[5:])
        for e in expected:
            if e.startswith("ayah:"):
                es, ea, eb = _ayah_range(e[5:])
                if ps == es and pa <= ea and eb <= pb:
                    return True
    return False


def top_candidates(c: dict) -> list[str]:
    out: list[str] = []
    for st in c.get("evidence_trace", []):
        ids = st.get("detail", {}).get("top_ids") or []
        if st["step"] == "retrieve":
            out += [f"hadith:{i}" for i in ids]
        elif st["step"] == "dorar":
            out += [f"dorar:{i}" for i in ids if i]
        elif st["step"] == "quran_match":
            for i in ids:
                a = repo.get_ayah_by_id(i)
                if a:
                    out.append(f"ayah:{a['surah']}:{a['ayah']}")
    return out


def in_top5(c: dict, expected: list[str]) -> bool:
    pred = pred_source_id(c)
    if same_source(pred, expected):
        return True
    cands = top_candidates(c)
    for e in expected:
        if e.startswith("ayah:"):
            s, a, _ = _ayah_range(e[5:])
            if f"ayah:{s}:{a}" in cands[:5] + cands[5:10]:
                return True
        elif e in cands:
            return True
    return False


def run(items: list[dict]) -> list[dict]:
    preds = []
    for n, it in enumerate(items, 1):
        t0 = time.perf_counter()
        r = verify(it["input"]).model_dump()
        ms = (time.perf_counter() - t0) * 1000
        core = core_text(it["input"])
        claims = r["claims"]
        best = max(claims, key=lambda c: overlap(c["claim_text"], core), default=None)
        extracted = best is not None and overlap(best["claim_text"], core) >= 0.8
        p = {"id": it["id"], "category": it["category"], "variant": it.get("variant"),
             "expected_status": it["expected_status"], "expected_match": it.get("expected_match"),
             "expected_source_ids": it.get("expected_source_ids") or [],
             "extracted": extracted, "n_claims": len(claims), "ms": round(ms),
             "status": best["status"] if best else None, "match_type": best["match_type"] if best else None,
             "claim_type": best["claim_type"] if best else None, "score": best["sanad_score"] if best else None,
             "pred_source": pred_source_id(best) if best else None,
             "top1": bool(best) and same_source(pred_source_id(best), it.get("expected_source_ids") or []),
             "top5": bool(best) and in_top5(best, it.get("expected_source_ids") or []),
             "summary": best["summary_ar"] if best else None}
        preds.append(p)
        ok = "✓" if p["status"] == p["expected_status"] else "✗"
        print(f"[{n:3}/{len(items)}] {ok} {it['id']:<22} exp={it['expected_status']:<5} got={p['status']!s:<5} "
              f"match={p['match_type']!s:<10} src={'1' if p['top1'] else ('5' if p['top5'] else '-')} "
              f"{ms / 1000:5.1f}s",
              flush=True)
    return preds


def metrics(preds: list[dict]) -> dict:
    def rate(xs):
        return round(sum(xs) / len(xs), 4) if xs else None

    with_src = [p for p in preds if p["expected_source_ids"]]
    conf = {e: {g: 0 for g in STATUSES + ["none"]} for e in STATUSES}
    for p in preds:
        conf[p["expected_status"]][p["status"] or "none"] += 1
    per_cat = {}
    for cat, ps in sorted(defaultdict(list, {k: [p for p in preds if p["category"] == k]
                                             for k in {p["category"] for p in preds}}).items()):
        src = [p for p in ps if p["expected_source_ids"]]
        per_cat[cat] = {"n": len(ps), "extraction_recall": rate([p["extracted"] for p in ps]),
                        "top1": rate([p["top1"] for p in src]), "top5": rate([p["top5"] for p in src]),
                        "status_acc": rate([p["status"] == p["expected_status"] for p in ps]),
                        "match_acc": rate([p["match_type"] == p["expected_match"] for p in ps if p["expected_match"]]),
                        "median_ms": round(statistics.median([p["ms"] for p in ps])) if ps else None}
    lat = sorted(p["ms"] for p in preds)
    return {
        "n": len(preds),
        "extraction_recall": rate([p["extracted"] for p in preds]),
        "top1_source_accuracy": rate([p["top1"] for p in with_src]),
        "top5_source_accuracy": rate([p["top5"] for p in with_src]),
        "n_with_source": len(with_src),
        "status_accuracy": rate([p["status"] == p["expected_status"] for p in preds]),
        "match_type_accuracy": rate([p["match_type"] == p["expected_match"] for p in preds if p["expected_match"]]),
        "confusion_matrix": conf,
        "latency_ms": {"median": round(statistics.median(lat)), "p90": lat[int(len(lat) * 0.9) - 1] if lat else None,
                       "max": lat[-1] if lat else None},
        "per_category": per_cat,
    }


def report(m: dict, preds: list[dict], cfg: dict) -> str:
    pc = lambda v: "—" if v is None else f"{v * 100:.1f}%"  # noqa: E731
    lines = [
        "# EVALUATION — SanadAI",
        "",
        f"_Generated by `scripts/run_eval.py` on {cfg['run_at']} — {m['n']} items, "
        f"extraction: {cfg['extraction']}, dense: {cfg['dense']}, reranker: {cfg['reranker']}, "
        f"models: {cfg['models']}, Dorar: offline cache._",
        "",
        "> ⚠️ Labels are generated deterministically from the sources (see `scripts/build_testset.py`) and are marked",
        "> `needs_review` until the project owner reviews them. Weak/fabricated labels are *silver*: they come",
        "> from the verdict of Dorar's top hit, which the system also quotes.",
        "",
        "## Headline metrics",
        "",
        "| Metric | Value | Target |",
        "|---|---|---|",
        f"| Claim-extraction recall | {pc(m['extraction_recall'])} | — |",
        f"| Top-1 source accuracy ({m['n_with_source']} items with a known source) "
        f"| {pc(m['top1_source_accuracy'])} | — |",
        f"| Top-5 source accuracy | {pc(m['top5_source_accuracy'])} | ≥ 90% |",
        f"| Status (traffic-light) accuracy | {pc(m['status_accuracy'])} | — |",
        f"| Match-type accuracy | {pc(m['match_type_accuracy'])} | — |",
        f"| Latency median / p90 / max | {m['latency_ms']['median'] / 1000:.1f}s / "
        f"{(m['latency_ms']['p90'] or 0) / 1000:.1f}s / {(m['latency_ms']['max'] or 0) / 1000:.1f}s | — |",
        "",
        "## Per category",
        "",
        "| Category | n | Extraction | Top-1 | Top-5 | Status acc. | Match acc. | Median latency |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for cat, v in m["per_category"].items():
        lines.append(f"| {cat} | {v['n']} | {pc(v['extraction_recall'])} | {pc(v['top1'])} | {pc(v['top5'])} | "
                     f"{pc(v['status_acc'])} | {pc(v['match_acc'])} | {v['median_ms'] / 1000:.1f}s |")
    lines += ["", "## Status confusion matrix (rows = expected, columns = predicted)", "",
              "| expected \\ predicted | green | amber | red | none |", "|---|---|---|---|---|"]
    for e in STATUSES:
        row = m["confusion_matrix"][e]
        lines.append(f"| **{e}** | {row['green']} | {row['amber']} | {row['red']} | {row['none']} |")
    wrong = [p for p in preds if p["status"] != p["expected_status"] or (p["expected_source_ids"] and not p["top1"])]
    lines += ["", f"## Mismatches ({len(wrong)})", "",
              "| id | expected | predicted | match | source top-1 | predicted source |", "|---|---|---|---|---|---|"]
    for p in wrong:
        lines.append(f"| {p['id']} | {p['expected_status']} | {p['status']} | {p['match_type']} | "
                     f"{'yes' if p['top1'] else 'no'} | {p['pred_source'] or '—'} |")
    for extra in ("_evaluation_analysis.md", "_evaluation_method.md"):
        path = ROOT / "docs" / extra
        if path.exists():
            lines += ["", path.read_text(encoding="utf-8")]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--only")
    ap.add_argument("--lexical-only", action="store_true")
    ap.add_argument("--report-only", action="store_true", help="rewrite EVALUATION.md from the last run")
    a = ap.parse_args()
    if a.report_only:
        saved = json.loads(RESULTS.read_text(encoding="utf-8"))
        preds = [json.loads(x) for x in PREDS.read_text(encoding="utf-8").splitlines() if x.strip()]
        REPORT.write_text(report(saved["metrics"], preds, saved["config"]), encoding="utf-8")
        return 0
    sys.stdout.reconfigure(encoding="utf-8")
    s = get_settings()
    if a.lexical_only:
        s.use_dense = False
        s.use_reranker = False
    dorar._default = dorar.DorarClient(offline=True)
    items = [json.loads(line) for line in TESTSET.read_text(encoding="utf-8").splitlines() if line.strip()]
    if a.only:
        items = [i for i in items if i["category"] == a.only]
    items = items[: a.limit]
    preds = run(items)
    m = metrics(preds)
    cfg = {"run_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
           "extraction": "llm" if s.llm_configured else "rules",
           "dense": s.use_dense, "reranker": s.use_reranker, "models": ml.describe(),
           "thresholds": {k: v for k, v in s.model_dump().items() if k.startswith("th_")}}
    RESULTS.write_text(json.dumps({"config": cfg, "metrics": m}, ensure_ascii=False, indent=2), encoding="utf-8")
    with PREDS.open("w", encoding="utf-8", newline="\n") as f:
        for p in preds:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    if not a.limit and not a.only:
        REPORT.write_text(report(m, preds, cfg), encoding="utf-8")
    print(json.dumps({k: v for k, v in m.items() if k not in ("per_category", "confusion_matrix")}, indent=1))
    print("status counts:", Counter(p["status"] for p in preds))
    return 0


if __name__ == "__main__":
    sys.exit(main())
