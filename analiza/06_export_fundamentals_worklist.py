from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT_DIR / "analiza" / "out"
INPUT_DIR = ROOT_DIR / "analiza" / "input"
MASTER_DATASET_PATH = OUT_DIR / "company_master_dataset.jsonl"
WORKLIST_PATH = INPUT_DIR / "fundamentals_worklist.csv"
SUMMARY_PATH = OUT_DIR / "fundamentals_worklist_summary.json"
LEADING_NOISE_PATTERN = re.compile(r"^[^A-Za-z0-9]+")
MULTISPACE_PATTERN = re.compile(r"\s+")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def normalize_label(value: str | None) -> str:
    if not value:
        return "Unknown"

    cleaned = str(value).strip()
    parts = cleaned.split()
    while len(parts) > 1 and any(ord(char) > 127 for char in parts[0]):
        parts = parts[1:]
    cleaned = " ".join(parts)
    cleaned = LEADING_NOISE_PATTERN.sub("", cleaned)
    cleaned = MULTISPACE_PATTERN.sub(" ", cleaned).strip(" -_/")
    return cleaned or "Unknown"


def load_master_rows() -> list[dict]:
    rows: list[dict] = []
    if not MASTER_DATASET_PATH.exists():
        return rows

    with MASTER_DATASET_PATH.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-posts", type=int, default=30)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--only-missing", action="store_true")
    args = parser.parse_args()

    ensure_dir(INPUT_DIR)
    ensure_dir(OUT_DIR)

    rows = load_master_rows()
    filtered = [row for row in rows if (row.get("posts_count") or 0) >= args.min_posts]
    if args.only_missing:
        filtered = [row for row in filtered if row.get("profitability_score") is None]

    filtered.sort(
        key=lambda item: (
            -(item.get("posts_count") or 0),
            item.get("rank_in_category") or 999999,
            item.get("symbol") or "",
        )
    )
    if args.limit:
        filtered = filtered[: args.limit]

    fieldnames = [
        "symbol",
        "company_name",
        "category",
        "industry",
        "posts_count",
        "custom_esg_proxy_score",
        "market_cap_label",
        "rank_in_category",
    ]

    with WORKLIST_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in filtered:
            writer.writerow(
                {
                    **{field: row.get(field) for field in fieldnames},
                    "category": normalize_label(row.get("category")),
                }
            )

    summary = {
        "input_file": str(MASTER_DATASET_PATH),
        "output_file": str(WORKLIST_PATH),
        "rows_written": len(filtered),
        "min_posts": args.min_posts,
        "only_missing": args.only_missing,
        "limit": args.limit,
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
