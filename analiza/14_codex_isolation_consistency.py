"""14_codex_isolation_consistency.py — test zgodności shared-vs-isolated (run 2 Codex).

Pyta: czy współdzielona sesja `agent:profiler:main` (z której powstało 890 profili)
zbiasowała wyniki względem profilowania w izolowanej sesji (świeża sesja per spółka)?

Bierze deterministyczną próbkę N już zrobionych spółek, profiluje je PONOWNIE
mechanizmem izolowanym (call_codex z wipe sesji + --thinking low) i porównuje
z wersją współdzieloną: zgodność coverage, liczby ram, etykiet ram, sentymentu.

Uruchomienie:
  python analiza/14_codex_isolation_consistency.py --n 20            # profiluj + porównaj
  python analiza/14_codex_isolation_consistency.py --compare-only    # tylko raport z gotowego pliku
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from llm_profiling_lib import build_prompt, load_posts_by_company, validate_llm_result
from codex_run_lib import call_codex

ROOT_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT_DIR / "analiza" / "out"
POSTS_FLAT_PATH = OUT_DIR / "posts_flat.jsonl"
SHARED_PATH = OUT_DIR / "llm_axiological_profiles_codex.jsonl"          # 890 z shared session
ISO_PATH = OUT_DIR / "llm_axiological_profiles_codex_isotest.jsonl"     # re-run izolowany

COVERAGE_ORD = {"none": 0, "marginal": 1, "present": 2, "dominant": 3}


def load_rows(path: Path) -> dict[str, dict]:
    rows = {}
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get("symbol"):
                    rows[r["symbol"]] = r
    return rows


def norm_labels(frames: list[dict]) -> set[str]:
    return {str(f.get("label", "")).strip().lower() for f in (frames or []) if f.get("label")}


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def select_sample(shared: dict[str, dict], n: int, seed: int) -> list[str]:
    # tylko udane (nie-error), deterministycznie
    syms = sorted(s for s, r in shared.items() if not r.get("error"))
    rng = random.Random(seed)
    rng.shuffle(syms)
    return sorted(syms[:n])


def run_isolated(symbols: list[str], thinking: str, out_path: Path) -> None:
    companies = load_posts_by_company(POSTS_FLAT_PATH, min_posts=5)
    done = load_rows(out_path)
    with out_path.open("a", encoding="utf-8") as f:
        for i, sym in enumerate(symbols):
            if sym in done and not done[sym].get("error"):
                continue
            data = companies.get(sym)
            if data is None:
                print(f"[{i+1}/{len(symbols)}] {sym} — brak postów, pomijam", file=sys.stderr)
                continue
            print(f"[{i+1}/{len(symbols)}] {sym} ({len(data['posts'])} postów, izolowana)...",
                  end=" ", flush=True)
            prompt = build_prompt(sym, data)
            result = call_codex(sym, prompt, thinking=thinking)
            if result is None:
                print("BŁĄD")
                row = {"symbol": sym, "category": data.get("category"),
                       "industry": data.get("industry"), "post_count": len(data["posts"]),
                       "frames": [], "axiological_coverage": "error",
                       "notes": "Codex call failed", "error": True}
            else:
                v = validate_llm_result(result)
                print(f"OK ({len(v['frames'])} frames, coverage={v['axiological_coverage']})")
                row = {"symbol": sym, "category": data.get("category"),
                       "industry": data.get("industry"), "post_count": len(data["posts"]),
                       **v, "error": False}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()


def compare(ref_path: Path, iso_path: Path) -> None:
    shared = load_rows(ref_path)
    iso = load_rows(iso_path)
    print(f"\nPorównanie: REF={ref_path.name}  vs  ISO={iso_path.name}")
    pairs = [(s, shared[s], iso[s]) for s in sorted(iso)
             if s in shared and not iso[s].get("error") and not shared[s].get("error")]
    if not pairs:
        print("Brak par do porównania (najpierw uruchom profilowanie izolowane).")
        return

    cov_exact = cov_adjacent = 0
    fcount_abs = 0
    jacc_sum = 0.0
    print(f"\n{'symbol':14s} {'shared cov':12s} {'iso cov':12s} {'#fr s/i':8s} {'labelJacc':9s}")
    print("-" * 60)
    for sym, sh, it in pairs:
        cs, ci = sh.get("axiological_coverage", "none"), it.get("axiological_coverage", "none")
        if cs == ci:
            cov_exact += 1
        if abs(COVERAGE_ORD.get(cs, 0) - COVERAGE_ORD.get(ci, 0)) <= 1:
            cov_adjacent += 1
        ns, ni = len(sh.get("frames") or []), len(it.get("frames") or [])
        fcount_abs += abs(ns - ni)
        j = jaccard(norm_labels(sh.get("frames")), norm_labels(it.get("frames")))
        jacc_sum += j
        print(f"{sym:14s} {cs:12s} {ci:12s} {f'{ns}/{ni}':8s} {j:.2f}")

    k = len(pairs)
    print("-" * 60)
    print(f"Par porównanych: {k}")
    print(f"Coverage zgodność DOKŁADNA:   {cov_exact}/{k}  ({100*cov_exact/k:.0f}%)")
    print(f"Coverage zgodność ±1 stopień: {cov_adjacent}/{k}  ({100*cov_adjacent/k:.0f}%)")
    print(f"Śr. |różnica liczby ram|:     {fcount_abs/k:.2f}")
    print(f"Śr. Jaccard etykiet ram:      {jacc_sum/k:.2f}")
    print("\nUWAGA interpretacyjna: exact-string Jaccard etykiet jest NISKI nawet dla dwóch\n"
          "niezależnych przebiegów izolowanych (model nazywa te same tematy różnymi słowami) —\n"
          "to miara szumu nazewnictwa, nie rozjazdu treści. Oceniaj bias sesji przez PORÓWNANIE\n"
          "z podłogą iso-vs-iso: jeśli shared-vs-iso ≈ iso-vs-iso, sesja nie biasuje. Stabilne\n"
          f"sygnały: coverage ±1 i liczba ram. (n={k}, pojedyncze losowanie — wynik poglądowy.)")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=20)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--thinking", type=str, default="low")
    p.add_argument("--compare-only", action="store_true")
    p.add_argument("--out", type=str, default=str(ISO_PATH),
                   help="plik na wyniki izolowane (domyślnie isotest)")
    p.add_argument("--ref", type=str, default=str(SHARED_PATH),
                   help="plik referencyjny do porównania (domyślnie shared 890)")
    args = p.parse_args()

    out_path = Path(args.out)
    ref_path = Path(args.ref)

    if not args.compare_only:
        # próbkę zawsze dobieramy z bazy 890 (shared), żeby porównywać te same spółki
        shared = load_rows(SHARED_PATH)
        if not shared:
            print(f"ERROR: brak {SHARED_PATH}", file=sys.stderr)
            sys.exit(1)
        sample = select_sample(shared, args.n, args.seed)
        print(f"Próbka do testu zgodności: {len(sample)} spółek (seed {args.seed}) -> {out_path.name}")
        run_isolated(sample, args.thinking, out_path)

    compare(ref_path, out_path)


if __name__ == "__main__":
    main()
