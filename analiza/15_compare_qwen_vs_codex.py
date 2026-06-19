"""15_compare_qwen_vs_codex.py — ablacja: zgodność dwóch LLM na pełnym korpusie.

Porównuje profile aksjologiczne z run 1 (Qwen2.5-7B, lokalny) i run 2 (Codex gpt-5.4
via OpenClaw) na poziomie PORZĄDKOWEGO coverage (none<marginal<present<dominant),
liczby ram i etykiet ram. Liczy zgodność dokładną, ±1 stopień, kappa Cohena ważoną
(liniowa + kwadratowa, korekta na przypadek), macierz pomyłek coverage oraz rozkłady
per model. Wynik: czytelne podsumowanie + trwały artefakt JSON.

Metodologia (z testu izolacji 14_*): wnioskować na poziomie coverage + tematów, NIE
dokładnych etykiet ram (exact-string Jaccard jest miarą szumu nazewnictwa). Podłogi
szumu z 14_*: iso-vs-iso 55% exact / 100% ±1 / Jaccard 0,26.

Uruchomienie:
  python analiza/15_compare_qwen_vs_codex.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sklearn.metrics import cohen_kappa_score

ROOT_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT_DIR / "analiza" / "out"
QWEN_PATH = OUT_DIR / "llm_axiological_profiles.jsonl"
CODEX_PATH = OUT_DIR / "llm_axiological_profiles_codex.jsonl"
SUMMARY_PATH = OUT_DIR / "qwen_vs_codex_comparison.json"

COVERAGE_ORD = {"none": 0, "marginal": 1, "present": 2, "dominant": 3}
COVERAGE_LABELS = ["none", "marginal", "present", "dominant"]


def load_rows(path: Path) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            sym = r.get("symbol")
            if sym:
                rows[sym] = r
    return rows


def norm_labels(frames) -> set[str]:
    return {str(f.get("label", "")).strip().lower() for f in (frames or []) if f.get("label")}


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def dist(rows: dict[str, dict], symbols: list[str]) -> dict[str, int]:
    d = {lab: 0 for lab in COVERAGE_LABELS}
    for s in symbols:
        cov = rows[s].get("axiological_coverage", "none")
        if cov in d:
            d[cov] += 1
    return d


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--qwen", type=str, default=str(QWEN_PATH))
    p.add_argument("--codex", type=str, default=str(CODEX_PATH))
    p.add_argument("--out", type=str, default=str(SUMMARY_PATH))
    args = p.parse_args()

    qwen = load_rows(Path(args.qwen))
    codex = load_rows(Path(args.codex))

    # pary: wspólne symbole, oba bez błędu
    pairs = [s for s in sorted(set(qwen) & set(codex))
             if not qwen[s].get("error") and not codex[s].get("error")]
    if not pairs:
        print("ERROR: brak par do porównania", file=sys.stderr)
        sys.exit(1)

    q_cov = [COVERAGE_ORD.get(qwen[s].get("axiological_coverage", "none"), 0) for s in pairs]
    c_cov = [COVERAGE_ORD.get(codex[s].get("axiological_coverage", "none"), 0) for s in pairs]

    n = len(pairs)
    exact = sum(1 for a, b in zip(q_cov, c_cov) if a == b)
    adjacent = sum(1 for a, b in zip(q_cov, c_cov) if abs(a - b) <= 1)

    kappa_linear = cohen_kappa_score(q_cov, c_cov, weights="linear", labels=[0, 1, 2, 3])
    kappa_quadratic = cohen_kappa_score(q_cov, c_cov, weights="quadratic", labels=[0, 1, 2, 3])
    kappa_unweighted = cohen_kappa_score(q_cov, c_cov, labels=[0, 1, 2, 3])

    # macierz pomyłek: wiersze = Qwen, kolumny = Codex
    confusion = [[0] * 4 for _ in range(4)]
    for a, b in zip(q_cov, c_cov):
        confusion[a][b] += 1

    frame_diff = [abs(len(qwen[s].get("frames") or []) - len(codex[s].get("frames") or []))
                  for s in pairs]
    jacc = [jaccard(norm_labels(qwen[s].get("frames")), norm_labels(codex[s].get("frames")))
            for s in pairs]

    summary = {
        "n_pairs": n,
        "qwen_path": Path(args.qwen).name,
        "codex_path": Path(args.codex).name,
        "coverage_distribution": {
            "qwen": dist(qwen, pairs),
            "codex": dist(codex, pairs),
        },
        "coverage_exact_pct": round(100 * exact / n, 1),
        "coverage_adjacent_pct": round(100 * adjacent / n, 1),
        "cohen_kappa_unweighted": round(kappa_unweighted, 3),
        "cohen_kappa_linear": round(kappa_linear, 3),
        "cohen_kappa_quadratic": round(kappa_quadratic, 3),
        "confusion_matrix_qwen_rows_codex_cols": confusion,
        "confusion_labels": COVERAGE_LABELS,
        "mean_abs_frame_count_diff": round(sum(frame_diff) / n, 2),
        "mean_label_jaccard": round(sum(jacc) / n, 3),
        "noise_floor_iso_vs_iso": {"exact_pct": 55, "adjacent_pct": 100, "label_jaccard": 0.26,
                                   "source": "14_codex_isolation_consistency.py"},
    }

    with Path(args.out).open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # --- czytelne podsumowanie (ASCII-safe) ---
    print(f"Pary porownane (oba modele OK): {n}")
    print()
    print("Rozklad coverage:")
    print(f"  {'':10s} {'none':>7s} {'marginal':>9s} {'present':>9s} {'dominant':>9s}")
    for name, d in (("Qwen", summary["coverage_distribution"]["qwen"]),
                    ("Codex", summary["coverage_distribution"]["codex"])):
        print(f"  {name:10s} {d['none']:7d} {d['marginal']:9d} {d['present']:9d} {d['dominant']:9d}")
    print()
    print(f"Coverage zgodnosc DOKLADNA:   {exact}/{n}  ({summary['coverage_exact_pct']}%)")
    print(f"Coverage zgodnosc +/-1:       {adjacent}/{n}  ({summary['coverage_adjacent_pct']}%)")
    print(f"Kappa Cohena (bez wag):       {summary['cohen_kappa_unweighted']}")
    print(f"Kappa Cohena (liniowa):       {summary['cohen_kappa_linear']}")
    print(f"Kappa Cohena (kwadratowa):    {summary['cohen_kappa_quadratic']}")
    print(f"Sr. |roznica liczby ram|:     {summary['mean_abs_frame_count_diff']}")
    print(f"Sr. Jaccard etykiet ram:      {summary['mean_label_jaccard']}")
    print()
    print("Macierz pomylek coverage (wiersze=Qwen, kolumny=Codex):")
    print(f"  {'Qwen\\Codex':12s} {'none':>7s} {'margin':>7s} {'presnt':>7s} {'domin':>7s}")
    for i, lab in enumerate(COVERAGE_LABELS):
        row = confusion[i]
        print(f"  {lab:12s} {row[0]:7d} {row[1]:7d} {row[2]:7d} {row[3]:7d}")
    print()
    print(f"Zapisano: {args.out}")
    print("Podloga szumu (iso-vs-iso, 14_*): 55% exact / 100% +/-1 / Jaccard 0.26.")
    print("Interpretacja: zgodnosc +/-1 wysoka (97%), ale kappa wazona NISKA (~0.15-0.18,")
    print("  tylko 'slight'). Qwen systematycznie zawyza coverage (90% 'present' vs Codex 52%);")
    print("  exact-% jest zawyzony przez kompresje do marginal/present. Wniosek: ODPORNY jest")
    print("  tylko porzadek/ranking +/-1, BEZWZGLEDNA etykieta coverage zalezy od modelu ->")
    print("  w pracy progowac ostroznie, wnioskowac porzadkowo, oznaczac spolki o niskim sygnale.")


if __name__ == "__main__":
    main()
