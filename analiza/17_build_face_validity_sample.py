"""Buduje stratyfikowana probke do walidacji face validity profilowania LLM.

Wybiera ~40 spolek z profilem (rozlozonych po sektorach) + ~10 z profile_null,
laczy nazwe/kategorie z master datasetu i zapisuje arkusz anotacji
(analiza/out/face_validity_sample.csv) w formacie dlugim: 1 wiersz = 1 rama.

Anotator wypelnia kolumny: frame_confirmed (0/1), evidence_correct (0/1), notes.
Po anotacji: precision = sum(frame_confirmed)/liczba ram; evidence_accuracy =
sum(evidence_correct)/liczba ram.

Uzycie: python analiza/17_build_face_validity_sample.py --n-profiled 40 --n-null 10 --seed 42
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "analiza" / "out"
PROFILE_PATH = OUT / "company_axiological_profile.jsonl"
MASTER_PATH = OUT / "company_master_dataset.jsonl"
SAMPLE_CSV = OUT / "face_validity_sample.csv"

FIELDS = [
    "sample_id", "symbol", "company_name", "category", "post_count",
    "axiological_coverage", "profile_null",
    "frame_label", "frame_evidence", "frame_exposure", "frame_sentiment",
    "frame_confirmed", "evidence_correct", "notes",
]


def load_meta() -> dict[str, dict]:
    meta: dict[str, dict] = {}
    if not MASTER_PATH.exists():
        return meta
    with MASTER_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            sym = r.get("symbol")
            if sym:
                meta[sym] = {"company_name": r.get("company_name"), "category": r.get("category")}
    return meta


def score() -> None:
    if not SAMPLE_CSV.exists():
        print("Brak wypelnionego pliku:", SAMPLE_CSV)
        return
    rows = list(csv.DictReader(SAMPLE_CSV.open(encoding="utf-8-sig")))
    frame_rows = [r for r in rows if str(r.get("profile_null")).lower() != "true"]
    conf = [r for r in frame_rows if r.get("frame_confirmed", "").strip() in ("0", "1")]
    evid = [r for r in frame_rows if r.get("evidence_correct", "").strip() in ("0", "1")]
    null_rows = [r for r in rows if str(r.get("profile_null")).lower() == "true"]
    null_done = [r for r in null_rows if r.get("frame_confirmed", "").strip() in ("0", "1")]
    res = {
        "frames_total": len(frame_rows),
        "frames_annotated": len(conf),
        "precision": round(sum(int(r["frame_confirmed"]) for r in conf) / len(conf), 3) if conf else None,
        "evidence_accuracy": round(sum(int(r["evidence_correct"]) for r in evid) / len(evid), 3) if evid else None,
        "null_judged_correct": round(sum(int(r["frame_confirmed"]) for r in null_done) / len(null_done), 3) if null_done else None,
        "uwaga": "anotator = autor (confirmation bias); brak inter-rater (kappa niepoliczalna)",
    }
    print(json.dumps(res, indent=2, ensure_ascii=False))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-profiled", type=int, default=40)
    ap.add_argument("--n-null", type=int, default=10)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--score", action="store_true", help="policz metryki z wypelnionego CSV")
    args = ap.parse_args()
    if args.score:
        return score()
    rng = random.Random(args.seed)

    profiles = [json.loads(l) for l in PROFILE_PATH.open(encoding="utf-8") if l.strip()]
    meta = load_meta()

    profiled = [p for p in profiles if not p.get("profile_null") and p.get("frames")]
    nulls = [p for p in profiles if p.get("profile_null")]

    # stratyfikacja profilowanych: round-robin po kategoriach (z meta)
    by_cat: dict[str, list] = defaultdict(list)
    for p in profiled:
        cat = (meta.get(p["symbol"], {}).get("category") or "Unknown")
        by_cat[cat].append(p)
    for cat in by_cat:
        rng.shuffle(by_cat[cat])
    cats = list(by_cat)
    rng.shuffle(cats)
    chosen_profiled: list = []
    i = 0
    while len(chosen_profiled) < args.n_profiled and any(by_cat[c] for c in cats):
        c = cats[i % len(cats)]
        if by_cat[c]:
            chosen_profiled.append(by_cat[c].pop())
        i += 1

    rng.shuffle(nulls)
    chosen_null = nulls[: args.n_null]

    rows: list[dict] = []
    sid = 0
    for p in chosen_profiled:
        sid += 1
        m = meta.get(p["symbol"], {})
        base = {
            "sample_id": sid, "symbol": p["symbol"],
            "company_name": m.get("company_name") or "", "category": m.get("category") or "",
            "post_count": p.get("post_count"), "axiological_coverage": p.get("axiological_coverage"),
            "profile_null": False,
        }
        for fr in p.get("frames", []):
            rows.append({**base,
                         "frame_label": fr.get("label", ""),
                         "frame_evidence": (fr.get("evidence") or "").replace("\n", " ").strip(),
                         "frame_exposure": fr.get("exposure", ""),
                         "frame_sentiment": fr.get("sentiment", ""),
                         "frame_confirmed": "", "evidence_correct": "", "notes": ""})
    for p in chosen_null:
        sid += 1
        m = meta.get(p["symbol"], {})
        rows.append({"sample_id": sid, "symbol": p["symbol"],
                     "company_name": m.get("company_name") or "", "category": m.get("category") or "",
                     "post_count": p.get("post_count"), "axiological_coverage": p.get("axiological_coverage"),
                     "profile_null": True,
                     "frame_label": "(profile_null — oceń czy słusznie brak profilu)",
                     "frame_evidence": "", "frame_exposure": "", "frame_sentiment": "",
                     "frame_confirmed": "", "evidence_correct": "", "notes": ""})

    with SAMPLE_CSV.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    n_frames = sum(1 for r in rows if not r["profile_null"])
    sectors = {r["category"] for r in rows if r["category"]}
    print(json.dumps({
        "profiled_selected": len(chosen_profiled),
        "null_selected": len(chosen_null),
        "frame_rows_to_annotate": n_frames,
        "distinct_sectors": len(sectors),
        "output": str(SAMPLE_CSV),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
