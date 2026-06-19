"""13_profile_via_codex.py — run 2 profilowania aksjologicznego modelem Codex (gpt-5.4)
przez OpenClaw w WSL. Walidacja ablacyjna do runu 1; NIE wchodzi do fuzji/mastera.

Uruchomienie (Windows Python):
  python analiza/13_profile_via_codex.py --target-n 90
  python analiza/13_profile_via_codex.py --limit 3        # smoke
  python analiza/13_profile_via_codex.py --resume
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from llm_profiling_lib import build_prompt, load_posts_by_company, validate_llm_result
from codex_run_lib import select_stratified_sample, call_codex

ROOT_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT_DIR / "analiza" / "out"
POSTS_FLAT_PATH = OUT_DIR / "posts_flat.jsonl"
RUN1_PATH = OUT_DIR / "llm_axiological_profiles.jsonl"
SAMPLE_PATH = OUT_DIR / "codex_sample_symbols.json"
OUT_PATH = OUT_DIR / "llm_axiological_profiles_codex.jsonl"


def load_run1_rows(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_done_symbols(path: Path) -> set[str]:
    """Symbole uznane za gotowe przy --resume.

    Liczą się TYLKO udane wiersze. Wiersze error (np. brak quoty Codexa) są
    pomijane, żeby przy wznowieniu zostały ponowione, a nie zaliczone jako zrobione.
    """
    done = set()
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if row.get("error"):
                        continue
                    symbol = row.get("symbol")
                    if symbol:
                        done.add(symbol)
    return done


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-n", type=int, default=90)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--agent", type=str, default="profiler")
    parser.add_argument("--thinking", type=str, default="low",
                        help="poziom reasoningu Codexa: off|minimal|low|medium|high|xhigh")
    parser.add_argument("--min-posts", type=int, default=5)
    parser.add_argument("--max-posts-per-company", type=int, default=25)
    parser.add_argument("--limit", type=int, default=None, help="ogranicz liczbę spółek (smoke)")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-consecutive-errors", type=int, default=8,
                        help="po tylu błędach pod rząd: stop (lub czekaj, gdy --wait-on-limit)")
    parser.add_argument("--wait-on-limit", action="store_true",
                        help="zamiast kończyć na limicie, śpij i wznawiaj aż do końca korpusu")
    parser.add_argument("--limit-wait-min", type=int, default=155,
                        help="ile minut spać po wykryciu limitu (domyślnie ~reset okna)")
    parser.add_argument("--overwrite", action="store_true",
                        help="pozwól nadpisać niepusty plik wynikowy (bez --resume)")
    args = parser.parse_args()

    # GUARD: bez --resume skrypt otwiera plik w trybie 'w' i UTNIE go.
    # Jeśli plik ma już dane, odmów — chyba że jawne --overwrite. Chroni przed
    # skasowaniem wyników udanego runu (zdarzyło się: 697 profili nadpisanych smoke-testem).
    if not args.resume and not args.overwrite and OUT_PATH.exists() and OUT_PATH.stat().st_size > 0:
        print(f"ERROR: {OUT_PATH} ma dane, a uruchamiasz bez --resume.\n"
              f"  Użyj --resume (dopisze i pominie zrobione) albo --overwrite (świadome nadpisanie).",
              file=sys.stderr)
        sys.exit(2)

    for p in (POSTS_FLAT_PATH, RUN1_PATH):
        if not p.exists():
            print(f"ERROR: brak pliku {p}", file=sys.stderr)
            sys.exit(1)

    run1_rows = load_run1_rows(RUN1_PATH)
    symbols = select_stratified_sample(run1_rows, target_n=args.target_n, seed=args.seed)
    SAMPLE_PATH.write_text(json.dumps(symbols, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Próbka: {len(symbols)} spółek -> {SAMPLE_PATH}")

    if args.limit:
        symbols = symbols[:args.limit]

    companies = load_posts_by_company(POSTS_FLAT_PATH, min_posts=args.min_posts)

    done = load_done_symbols(OUT_PATH) if args.resume else set()
    if done:
        print(f"Wznowienie: pominięto {len(done)} spółek")

    mode = "a" if args.resume else "w"
    processed = errors = 0
    consecutive_errors = 0
    stopped_early = False
    with OUT_PATH.open(mode, encoding="utf-8") as f:
        for i, symbol in enumerate(symbols):
            if symbol in done:
                continue
            data = companies.get(symbol)
            if data is None:
                print(f"[{i+1}/{len(symbols)}] {symbol} — brak postów, pomijam", file=sys.stderr)
                continue
            print(f"[{i+1}/{len(symbols)}] {symbol} ({len(data['posts'])} postów)...", end=" ", flush=True)
            prompt = build_prompt(symbol, data, max_posts=args.max_posts_per_company)
            result = call_codex(symbol, prompt, args.agent, thinking=args.thinking)
            if result is None:
                errors += 1
                consecutive_errors += 1
                print("BŁĄD")
                row = {"symbol": symbol, "category": data.get("category"),
                       "industry": data.get("industry"), "post_count": len(data["posts"]),
                       "frames": [], "axiological_coverage": "error",
                       "notes": "Codex call failed", "error": True}
            else:
                processed += 1
                consecutive_errors = 0
                validated = validate_llm_result(result)
                print(f"OK ({len(validated['frames'])} frames, coverage={validated['axiological_coverage']})")
                row = {"symbol": symbol, "category": data.get("category"),
                       "industry": data.get("industry"), "post_count": len(data["posts"]),
                       **validated, "error": False}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            # Seria błędów pod rząd = najpewniej wyczerpany limit Codexa.
            if consecutive_errors >= args.max_consecutive_errors:
                if args.wait_on_limit:
                    # Przeczekaj reset okna i jedź dalej — run sam dobija korpus.
                    print(f"\n{consecutive_errors} błędów pod rząd — limit Codexa. "
                          f"Śpię {args.limit_wait_min} min i wznawiam...",
                          file=sys.stderr, flush=True)
                    time.sleep(args.limit_wait_min * 60)
                    consecutive_errors = 0
                    continue
                stopped_early = True
                print(f"\n{consecutive_errors} błędów pod rząd — prawdopodobnie limit Codexa. "
                      f"Przerywam pass; wznów `--resume` po resecie.", file=sys.stderr)
                break

    tail = " (przerwane na limicie)" if stopped_early else ""
    print(f"\nGotowe: {processed} OK, {errors} błędów -> {OUT_PATH}{tail}")
    # Kod wyjścia 3 = przerwane na limicie (sygnał dla pętli wznawiającej).
    if stopped_early:
        sys.exit(3)


if __name__ == "__main__":
    main()
