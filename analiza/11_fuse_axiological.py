"""11_fuse_axiological.py

Fuzja wyników z BERTopic (×3 filtry) i LLM.
Produkuje company_axiological_profile.jsonl.

Uruchomienie:
  python 11_fuse_axiological.py
  python 11_fuse_axiological.py --sample
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT_DIR / "analiza" / "out"

sys.path.insert(0, str(ROOT_DIR / "analiza"))
from fuse_axiological_lib import (
    compute_axiological_confidence,
    compute_inter_method_agreement,
    merge_frames,
)

BERTOPIC_EXPOSURE_PATHS = {
    "seed": OUT_DIR / "company_bertopic_exposure_seed.jsonl",
    "nofilter": OUT_DIR / "company_bertopic_exposure_nofilter.jsonl",
    "embed": OUT_DIR / "company_bertopic_exposure_embed.jsonl",
}
BERTOPIC_EXPOSURE_SAMPLE_PATHS = {
    "seed": OUT_DIR / "company_bertopic_exposure_seed_sample.jsonl",
    "nofilter": OUT_DIR / "company_bertopic_exposure_nofilter_sample.jsonl",
    "embed": OUT_DIR / "company_bertopic_exposure_embed_sample.jsonl",
}
LLM_PATH = OUT_DIR / "llm_axiological_profiles.jsonl"
LLM_SAMPLE_PATH = OUT_DIR / "llm_axiological_profiles_sample.jsonl"
PROFILE_OUT_PATH = OUT_DIR / "company_axiological_profile.jsonl"
PROFILE_SAMPLE_OUT_PATH = OUT_DIR / "company_axiological_profile_sample.jsonl"
COVERAGE_SUMMARY_PATH = OUT_DIR / "axiological_coverage_summary.json"


def load_jsonl(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    result = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    row = json.loads(line)
                    result[str(row.get("symbol") or "").upper()] = row
                except json.JSONDecodeError as e:
                    print(f"WARN: skipping malformed line: {e}", file=sys.stderr)
    return result


def build_profile(symbol: str, bertopic_data: dict[str, dict], llm_data: dict | None) -> dict:
    methods: dict[str, dict] = {}

    for filter_name, data in bertopic_data.items():
        methods[f"bertopic_{filter_name}"] = {
            "topic_exposure": data.get("topic_exposure", {}),
            "axiological_coverage": data.get("axiological_coverage", 0.0),
            "post_count": data.get("post_count", 0),
        }

    llm_frames: list[dict] = []
    llm_coverage = "none"
    if llm_data and not llm_data.get("error"):
        llm_frames = llm_data.get("frames") or []
        llm_coverage = llm_data.get("axiological_coverage", "none")
        methods["llm"] = {"frames": llm_frames}

    agreement = compute_inter_method_agreement(methods)

    # Zbierz coverage z BERTopic (max z trzech filtrów)
    bertopic_coverages = [
        d.get("axiological_coverage", 0.0)
        for d in bertopic_data.values()
    ]
    max_coverage = max(bertopic_coverages) if bertopic_coverages else 0.0
    post_count = max(d.get("post_count", 0) for d in bertopic_data.values()) if bertopic_data else 0
    active_methods = sum(1 for m in methods.values() if m.get("topic_exposure") or m.get("frames"))

    confidence = compute_axiological_confidence(max_coverage, post_count, active_methods)

    # Frames ze wszystkich metod
    all_frames = list(llm_frames)  # LLM daje najbogatszy opis
    merged = merge_frames(all_frames)

    return {
        "symbol": symbol,
        "post_count": post_count,
        "axiological_coverage": round(max_coverage, 4),
        "axiological_coverage_by_filter": {k: round(v.get("axiological_coverage", 0.0), 4) for k, v in methods.items() if "bertopic" in k},
        "axiological_confidence": confidence,
        "inter_method_agreement": agreement,
        "active_method_count": active_methods,
        "llm_coverage": llm_coverage,
        "frames": merged,
        "has_signal": max_coverage > 0.05 or bool(merged),
        "profile_null": max_coverage < 0.03 and not merged,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", action="store_true")
    args = parser.parse_args()

    exposure_paths = BERTOPIC_EXPOSURE_SAMPLE_PATHS if args.sample else BERTOPIC_EXPOSURE_PATHS
    llm_path = LLM_SAMPLE_PATH if args.sample else LLM_PATH
    out_path = PROFILE_SAMPLE_OUT_PATH if args.sample else PROFILE_OUT_PATH

    bertopic_by_filter: dict[str, dict[str, dict]] = {}
    for filter_name, path in exposure_paths.items():
        bertopic_by_filter[filter_name] = load_jsonl(path)
        print(f"BERTopic {filter_name}: {len(bertopic_by_filter[filter_name])} spółek")

    llm = load_jsonl(llm_path)
    print(f"LLM profiles: {len(llm)} spółek")

    # Zbierz wszystkie symbole
    all_symbols: set[str] = set()
    for data in bertopic_by_filter.values():
        all_symbols.update(data.keys())
    all_symbols.update(llm.keys())

    profiles = []
    for symbol in sorted(all_symbols):
        bert_data = {f: bertopic_by_filter[f].get(symbol, {}) for f in bertopic_by_filter}
        llm_data = llm.get(symbol)
        profile = build_profile(symbol, bert_data, llm_data)
        profiles.append(profile)

    # Posortuj po coverage malejąco
    profiles.sort(key=lambda p: (-p["axiological_coverage"], p["symbol"]))

    with out_path.open("w", encoding="utf-8") as f:
        for p in profiles:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    # Summary
    has_signal = sum(1 for p in profiles if p["has_signal"])
    null_profiles = sum(1 for p in profiles if p["profile_null"])
    summary = {
        "total_companies": len(profiles),
        "has_signal": has_signal,
        "profile_null": null_profiles,
        "avg_coverage": round(sum(p["axiological_coverage"] for p in profiles) / len(profiles), 4) if profiles else 0.0,
        "avg_confidence": round(sum(p["axiological_confidence"] for p in profiles) / len(profiles), 4) if profiles else 0.0,
        "avg_agreement": round(sum(p["inter_method_agreement"] for p in profiles) / len(profiles), 4) if profiles else 0.0,
    }
    COVERAGE_SUMMARY_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nProfile: {len(profiles)} spółek")
    print(f"  Z sygnałem: {has_signal} ({100*has_signal//len(profiles) if profiles else 0}%)")
    print(f"  Null (za słabe dane): {null_profiles}")
    print(f"  Avg coverage: {summary['avg_coverage']:.3f}")
    print(f"Zapisano: {out_path}")


if __name__ == "__main__":
    main()
