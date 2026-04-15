from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SCRAPPER_DIR = ROOT_DIR / "scrapper"
MEDIA_SAMPLE_DIR = SCRAPPER_DIR / "media_sample"
MERGED_FLAT_PATH = SCRAPPER_DIR / "merged_flat_stocktwits.jsonl"
OUT_DIR = ROOT_DIR / "analiza" / "out"
POSTS_FLAT_PATH = OUT_DIR / "posts_flat.jsonl"
SUMMARY_PATH = OUT_DIR / "posts_flat_summary.json"
POSTS_FLAT_SAMPLE_PATH = OUT_DIR / "posts_flat_sample.jsonl"
SUMMARY_SAMPLE_PATH = OUT_DIR / "posts_flat_sample_summary.json"


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_company_index() -> dict[str, dict]:
    by_symbol: dict[str, dict] = {}
    if not MERGED_FLAT_PATH.exists():
        return by_symbol

    with MERGED_FLAT_PATH.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue

            row = json.loads(line)
            symbol = str(row.get("st_url_symbol") or row.get("st_symbol") or "").strip().upper().replace("-", ".")
            if not symbol:
                continue

            rank = row.get("cmc_rank_in_category") or 999999
            current = by_symbol.get(symbol)
            if current and (current.get("rank_in_category") or 999999) <= rank:
                continue

            by_symbol[symbol] = {
                "symbol": symbol,
                "company_name": row.get("st_company_name") or row.get("cmc_company_name") or symbol,
                "category": row.get("category") or "Unknown",
                "industry": row.get("st_industry"),
                "market_cap": row.get("cmc_market_cap") or row.get("st_market_cap"),
                "rank_in_category": row.get("cmc_rank_in_category"),
            }

    return by_symbol


def iter_latest_symbol_runs(limit_symbols: int | None = None):
    symbol_dirs = [entry for entry in MEDIA_SAMPLE_DIR.iterdir() if entry.is_dir()]
    symbol_dirs.sort(key=lambda item: item.name)

    emitted = 0
    for symbol_dir in symbol_dirs:
        runs_dir = symbol_dir / "runs"
        if not runs_dir.exists():
            continue

        run_dirs = [entry for entry in runs_dir.iterdir() if entry.is_dir()]
        if not run_dirs:
            continue

        latest_run = sorted(run_dirs, key=lambda item: item.name)[-1]
        messages_dir = latest_run / "messages"
        if not messages_dir.exists():
            continue

        yield symbol_dir.name.upper(), latest_run, messages_dir

        emitted += 1
        if limit_symbols is not None and emitted >= limit_symbols:
            break


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit-symbols", type=int, default=None)
    args = parser.parse_args()

    ensure_dir(OUT_DIR)
    company_index = load_company_index()
    posts_output = POSTS_FLAT_SAMPLE_PATH if args.limit_symbols is not None else POSTS_FLAT_PATH
    summary_output = SUMMARY_SAMPLE_PATH if args.limit_symbols is not None else SUMMARY_PATH

    posts_written = 0
    empty_text_posts = 0
    symbols_processed = 0

    with posts_output.open("w", encoding="utf-8") as out_handle:
        for symbol, latest_run, messages_dir in iter_latest_symbol_runs(args.limit_symbols):
            symbol_meta = company_index.get(symbol, {})
            message_dirs = [entry for entry in messages_dir.iterdir() if entry.is_dir()]
            for message_dir in message_dirs:
                meta_path = message_dir / "meta.json"
                if not meta_path.exists():
                    continue

                data = json.loads(meta_path.read_text(encoding="utf-8"))
                text = (data.get("text") or "").strip()
                files = data.get("files") or []
                row = {
                    "symbol": symbol,
                    "company_name": symbol_meta.get("company_name") or symbol,
                    "category": symbol_meta.get("category") or "Unknown",
                    "industry": symbol_meta.get("industry"),
                    "market_cap": symbol_meta.get("market_cap"),
                    "rank_in_category": symbol_meta.get("rank_in_category"),
                    "source_run": latest_run.name,
                    "message_id": data.get("id"),
                    "message_url": data.get("url"),
                    "username": data.get("username"),
                    "datetime": data.get("datetime"),
                    "text": text,
                    "text_length": len(text),
                    "is_text_empty": not bool(text),
                    "embed_count": len(data.get("embeds") or []),
                    "media_count": len(data.get("media") or []),
                    "files_count": len(files),
                }
                out_handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                posts_written += 1
                if not text:
                    empty_text_posts += 1

            symbols_processed += 1

    summary = {
        "input_media_dir": str(MEDIA_SAMPLE_DIR),
        "input_merged_file": str(MERGED_FLAT_PATH),
        "symbols_processed": symbols_processed,
        "posts_written": posts_written,
        "empty_text_posts": empty_text_posts,
        "text_posts": posts_written - empty_text_posts,
        "output_file": str(posts_output),
        "is_sample": args.limit_symbols is not None,
    }
    summary_output.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
