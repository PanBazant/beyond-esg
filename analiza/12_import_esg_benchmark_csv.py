from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
INPUT_DIR = ROOT_DIR / "analiza" / "input"
OUT_DIR = ROOT_DIR / "analiza" / "out"
DEFAULT_OUTPUT_PATH = OUT_DIR / "company_real_esg_benchmark.jsonl"
DEFAULT_SUMMARY_PATH = OUT_DIR / "company_real_esg_benchmark_summary.json"
TEMPLATE_PATH = INPUT_DIR / "company_real_esg_benchmark_template.csv"

HEADER_ALIASES = {
    "symbol": {"symbol", "ticker", "st_symbol"},
    "total_esg_score": {"total_esg_score", "esg_score", "totalesgscore", "total score", "esg total score"},
    "environment_score": {"environment_score", "environmental_score", "environmentalscore", "environment score"},
    "social_score": {"social_score", "socialscore", "social score"},
    "governance_score": {"governance_score", "governancescore", "governance score", "governancepillar_score"},
}


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def normalize_header(value: str) -> str:
    return "".join(ch.lower() for ch in str(value).strip() if ch.isalnum() or ch == "_")


def resolve_columns(fieldnames: list[str]) -> dict[str, str]:
    normalized_map = {normalize_header(name): name for name in fieldnames}
    resolved: dict[str, str] = {}
    for canonical_name, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            original = normalized_map.get(normalize_header(alias))
            if original:
                resolved[canonical_name] = original
                break
    if "symbol" not in resolved or "total_esg_score" not in resolved:
        raise ValueError("Plik ESG musi zawierac przynajmniej kolumny symbol/ticker oraz total_esg_score/esg_score.")
    return resolved


def parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    cleaned = str(value).strip().replace(",", ".")
    if not cleaned:
        return None
    try:
        return round(float(cleaned), 4)
    except ValueError:
        return None


def write_template() -> None:
    ensure_dir(INPUT_DIR)
    with TEMPLATE_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["symbol", "total_esg_score", "environment_score", "social_score", "governance_score"],
        )
        writer.writeheader()
    print(str(TEMPLATE_PATH))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-file", type=str, default=None)
    parser.add_argument("--output-file", type=str, default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--summary-file", type=str, default=str(DEFAULT_SUMMARY_PATH))
    parser.add_argument("--source-name", type=str, required=False, default="external-esg-import")
    parser.add_argument("--as-of-date", type=str, required=False, default=None)
    parser.add_argument("--write-template", action="store_true")
    args = parser.parse_args()

    if args.write_template:
        write_template()
        return

    if not args.input_file:
        raise ValueError("Podaj --input-file albo uzyj --write-template.")

    input_path = Path(args.input_file)
    output_path = Path(args.output_file)
    summary_path = Path(args.summary_file)
    ensure_dir(output_path.parent)
    ensure_dir(summary_path.parent)

    with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        column_map = resolve_columns(fieldnames)
        rows = list(reader)

    written_rows = []
    skipped_rows = 0
    with output_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            symbol = str(row.get(column_map["symbol"], "")).strip().upper().replace("-", ".")
            total_score = parse_float(row.get(column_map["total_esg_score"]))
            if not symbol or total_score is None:
                skipped_rows += 1
                continue

            payload = {
                "symbol": symbol,
                "total_esg_score": total_score,
                "environment_score": parse_float(row.get(column_map.get("environment_score", ""))),
                "social_score": parse_float(row.get(column_map.get("social_score", ""))),
                "governance_score": parse_float(row.get(column_map.get("governance_score", ""))),
                "source": args.source_name,
                "as_of_date": args.as_of_date,
            }
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
            written_rows.append(payload)

    summary = {
        "input_file": str(input_path),
        "output_file": str(output_path),
        "source_name": args.source_name,
        "as_of_date": args.as_of_date,
        "rows_read": len(rows),
        "rows_written": len(written_rows),
        "rows_skipped": skipped_rows,
        "symbols_written": len({row["symbol"] for row in written_rows}),
        "column_map": column_map,
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
