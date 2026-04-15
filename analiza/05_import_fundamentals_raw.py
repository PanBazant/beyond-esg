from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
INPUT_DIR = ROOT_DIR / "analiza" / "input"
RAW_INPUT_DIR = INPUT_DIR / "raw"
OUT_DIR = ROOT_DIR / "analiza" / "out"
TEMPLATE_PATH = INPUT_DIR / "company_fundamentals_template.csv"
TARGET_PATH = INPUT_DIR / "company_fundamentals.csv"
REPORT_PATH = OUT_DIR / "company_fundamentals_import_report.json"
UNMATCHED_PATH = OUT_DIR / "company_fundamentals_unmatched.csv"

FIELDNAMES = [
    "symbol",
    "company_name",
    "category",
    "industry",
    "net_margin",
    "operating_margin",
    "roe",
    "roa",
    "revenue_growth",
    "source",
    "as_of_date",
]

HEADER_ALIASES = {
    "symbol": {
        "symbol", "ticker", "ticker_symbol", "instrument", "instrumentcode", "code", "stock", "stocksymbol",
    },
    "company_name": {
        "company", "companyname", "name", "issuer", "securityname", "fullname",
    },
    "net_margin": {
        "netmargin", "netprofitmargin", "netincomemargin", "profitmargin", "marginnet",
    },
    "operating_margin": {
        "operatingmargin", "operatingprofitmargin", "ebitmargin", "operatingincomemargin",
    },
    "roe": {
        "roe", "returnonequity", "returnonequityttm",
    },
    "roa": {
        "roa", "returnonassets", "returnonassetsttm",
    },
    "revenue_growth": {
        "revenuegrowth", "salesgrowth", "revenueyoygrowth", "revenuegrowthyoy", "growthrevenue", "revenuecagr",
    },
    "source": {
        "source", "provider", "vendor", "datasource",
    },
    "as_of_date": {
        "asofdate", "date", "reportdate", "snapshotdate", "periodend", "fiscaldate", "pricedate",
    },
}

NORMALIZE_HEADER_RE = re.compile(r"[^a-z0-9]+")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def normalize_header(header: str) -> str:
    return NORMALIZE_HEADER_RE.sub("", str(header).strip().lower())


def normalize_symbol(value: str | None) -> str:
    return str(value or "").strip().upper().replace("-", ".")


def parse_ratio(value: str | None) -> float | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    text = text.replace(",", ".").replace("%", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


def read_csv_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_base_rows() -> tuple[list[dict], dict[str, dict]]:
    source_path = TARGET_PATH if TARGET_PATH.exists() else TEMPLATE_PATH
    if not source_path.exists():
        raise FileNotFoundError(
            "Brakuje bazowego pliku company_fundamentals_template.csv. "
            "Najpierw uruchom 04_build_profitability_features.py, aby go wygenerowac."
        )

    rows = read_csv_rows(source_path)
    by_symbol: dict[str, dict] = {}
    normalized_rows: list[dict] = []
    for row in rows:
        normalized = {field: (row.get(field) or "").strip() for field in FIELDNAMES}
        normalized["symbol"] = normalize_symbol(normalized["symbol"])
        if not normalized["symbol"]:
            continue
        normalized_rows.append(normalized)
        by_symbol[normalized["symbol"]] = normalized
    return normalized_rows, by_symbol


def detect_mapping(headers: list[str]) -> dict[str, str]:
    normalized_headers = {normalize_header(header): header for header in headers}
    mapping: dict[str, str] = {}

    for target_field, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            if alias in normalized_headers:
                mapping[target_field] = normalized_headers[alias]
                break

    if "symbol" not in mapping:
        raise ValueError("Nie udalo sie wykryc kolumny symbol/ticker w surowym eksporcie.")

    return mapping


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in FIELDNAMES})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-file", type=str, required=True)
    parser.add_argument("--source-name", type=str, default=None)
    parser.add_argument("--as-of-date", type=str, default=None)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()

    ensure_dir(INPUT_DIR)
    ensure_dir(RAW_INPUT_DIR)
    ensure_dir(OUT_DIR)

    input_path = Path(args.input_file)
    if not input_path.exists():
        raise FileNotFoundError(f"Brak pliku z surowym eksportem: {input_path}")

    base_rows, base_by_symbol = load_base_rows()
    raw_rows = read_csv_rows(input_path)
    headers = list(raw_rows[0].keys()) if raw_rows else []
    mapping = detect_mapping(headers) if headers else {}

    updated_symbols: set[str] = set()
    unmatched_rows: list[dict] = []
    matched_rows = 0

    for raw_row in raw_rows:
        symbol = normalize_symbol(raw_row.get(mapping["symbol"]))
        if not symbol:
            continue

        target_row = base_by_symbol.get(symbol)
        if target_row is None:
            unmatched_rows.append({"symbol": symbol, "company_name": raw_row.get(mapping.get("company_name", ""), "")})
            continue

        matched_rows += 1
        updated_symbols.add(symbol)

        company_name_header = mapping.get("company_name")
        if company_name_header:
            company_name = (raw_row.get(company_name_header) or "").strip()
            if company_name:
                target_row["company_name"] = company_name

        for metric_field in ("net_margin", "operating_margin", "roe", "roa", "revenue_growth"):
            source_header = mapping.get(metric_field)
            if not source_header:
                continue

            parsed = parse_ratio(raw_row.get(source_header))
            if parsed is None and not args.replace:
                continue
            target_row[metric_field] = "" if parsed is None else str(parsed)

        if args.source_name:
            target_row["source"] = args.source_name
        elif mapping.get("source") and (raw_row.get(mapping["source"]) or "").strip():
            target_row["source"] = (raw_row.get(mapping["source"]) or "").strip()

        if args.as_of_date:
            target_row["as_of_date"] = args.as_of_date
        elif mapping.get("as_of_date") and (raw_row.get(mapping["as_of_date"]) or "").strip():
            target_row["as_of_date"] = (raw_row.get(mapping["as_of_date"]) or "").strip()

    write_csv(TARGET_PATH, base_rows)

    with UNMATCHED_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["symbol", "company_name"])
        writer.writeheader()
        for row in unmatched_rows:
            writer.writerow(row)

    report = {
        "input_file": str(input_path),
        "target_file": str(TARGET_PATH),
        "base_rows": len(base_rows),
        "raw_rows": len(raw_rows),
        "matched_rows": matched_rows,
        "updated_symbols": len(updated_symbols),
        "unmatched_rows": len(unmatched_rows),
        "detected_mapping": mapping,
        "replace_mode": args.replace,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
