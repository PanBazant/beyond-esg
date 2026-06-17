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
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from llm_profiling_lib import build_prompt, load_posts_by_company, validate_llm_result
from codex_run_lib import select_stratified_sample, build_openclaw_cmd, parse_openclaw_response

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


def call_codex(symbol: str, prompt: str, agent: str, retries: int = 2) -> dict | None:
    cmd = build_openclaw_cmd(symbol, prompt, agent=agent)
    for attempt in range(retries + 1):
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  encoding="utf-8", timeout=360)
        except subprocess.TimeoutExpired:
            print(f"  timeout (attempt {attempt+1})", file=sys.stderr)
            continue
        if proc.returncode != 0:
            print(f"  exit {proc.returncode}: {proc.stderr[:200]}", file=sys.stderr)
            time.sleep(2)
            continue
        parsed = parse_openclaw_response(proc.stdout)
        if parsed is not None:
            return parsed
        print(f"  unparsable response (attempt {attempt+1})", file=sys.stderr)
        time.sleep(1)
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-n", type=int, default=90)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--agent", type=str, default="profiler")
    parser.add_argument("--min-posts", type=int, default=5)
    parser.add_argument("--max-posts-per-company", type=int, default=25)
    parser.add_argument("--limit", type=int, default=None, help="ogranicz liczbę spółek (smoke)")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

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
            result = call_codex(symbol, prompt, args.agent)
            if result is None:
                errors += 1
                print("BŁĄD")
                row = {"symbol": symbol, "category": data.get("category"),
                       "industry": data.get("industry"), "post_count": len(data["posts"]),
                       "frames": [], "axiological_coverage": "error",
                       "notes": "Codex call failed", "error": True}
            else:
                processed += 1
                validated = validate_llm_result(result)
                print(f"OK ({len(validated['frames'])} frames, coverage={validated['axiological_coverage']})")
                row = {"symbol": symbol, "category": data.get("category"),
                       "industry": data.get("industry"), "post_count": len(data["posts"]),
                       **validated, "error": False}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()

    print(f"\nGotowe: {processed} OK, {errors} błędów -> {OUT_PATH}")


if __name__ == "__main__":
    main()
