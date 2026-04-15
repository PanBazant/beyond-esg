from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SCRAPPER_DIR = ROOT_DIR / "scrapper"
INPUT_DIR = ROOT_DIR / "analiza" / "input"
OUT_DIR = ROOT_DIR / "analiza" / "out"
MERGED_FLAT_PATH = SCRAPPER_DIR / "merged_flat_stocktwits.jsonl"
TECHNICALS_INPUT_PATH = INPUT_DIR / "company_technicals.csv"
TECHNICALS_TEMPLATE_PATH = INPUT_DIR / "company_technicals_template.csv"
TECHNICAL_FEATURES_PATH = OUT_DIR / "company_technical_features.jsonl"
SUMMARY_PATH = OUT_DIR / "company_technical_features_summary.json"
TECHNICAL_FEATURES_SAMPLE_PATH = OUT_DIR / "company_technical_features_sample.jsonl"
SUMMARY_SAMPLE_PATH = OUT_DIR / "company_technical_features_sample_summary.json"

METRIC_WEIGHTS = {
    "momentum_30d": 0.25,
    "momentum_90d": 0.35,
    "volatility_30d": 0.20,
    "drawdown_90d": 0.20,
}
INVERSE_METRICS = {"volatility_30d", "drawdown_90d"}
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


def load_companies() -> list[dict]:
    by_symbol: dict[str, dict] = {}
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
                "category": normalize_label(row.get("category")),
                "industry": row.get("st_industry"),
                "rank_in_category": row.get("cmc_rank_in_category"),
            }

    return [by_symbol[key] for key in sorted(by_symbol)]


def export_template(template_path: Path, companies: list[dict]) -> None:
    fieldnames = [
        "symbol",
        "company_name",
        "category",
        "industry",
        "momentum_30d",
        "momentum_90d",
        "volatility_30d",
        "drawdown_90d",
        "source",
        "as_of_date",
    ]

    with template_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for company in companies:
            writer.writerow(
                {
                    "symbol": company["symbol"],
                    "company_name": company["company_name"],
                    "category": company["category"],
                    "industry": company.get("industry"),
                    "momentum_30d": "",
                    "momentum_90d": "",
                    "volatility_30d": "",
                    "drawdown_90d": "",
                    "source": "",
                    "as_of_date": "",
                }
            )


def parse_metric(value: str | None) -> float | None:
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


def quantile(values: list[float], q: float) -> float:
    if not values:
        raise ValueError("Brak wartosci do wyznaczenia kwantyla.")
    if len(values) == 1:
        return values[0]

    pos = (len(values) - 1) * q
    low = int(pos)
    high = min(low + 1, len(values) - 1)
    fraction = pos - low
    return values[low] * (1 - fraction) + values[high] * fraction


def build_bounds(rows: list[dict], metric_name: str) -> tuple[float, float] | None:
    values = sorted(row[metric_name] for row in rows if row.get(metric_name) is not None)
    if not values:
        return None

    low = quantile(values, 0.10)
    high = quantile(values, 0.90)
    if high <= low:
        low = min(values)
        high = max(values)
    if high <= low:
        return None
    return low, high


def normalize_value(value: float | None, bounds: tuple[float, float] | None, inverse: bool = False) -> float | None:
    if value is None or bounds is None:
        return None

    low, high = bounds
    if high <= low:
        return None

    normalized = (value - low) / (high - low)
    clipped = max(0.0, min(1.0, normalized))
    return 1 - clipped if inverse else clipped


def load_input_rows(input_path: Path, limit_rows: int | None = None) -> list[dict]:
    rows: list[dict] = []
    with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for index, raw_row in enumerate(reader, start=1):
            if limit_rows is not None and index > limit_rows:
                break

            symbol = str(raw_row.get("symbol") or "").strip().upper().replace("-", ".")
            if not symbol:
                continue

            row = {
                "symbol": symbol,
                "company_name": (raw_row.get("company_name") or "").strip() or symbol,
                "source": (raw_row.get("source") or "").strip() or None,
                "as_of_date": (raw_row.get("as_of_date") or "").strip() or None,
            }
            for metric_name in METRIC_WEIGHTS:
                row[metric_name] = parse_metric(raw_row.get(metric_name))
            rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-file", type=str, default=str(TECHNICALS_INPUT_PATH))
    parser.add_argument("--limit-rows", type=int, default=None)
    parser.add_argument("--sample", action="store_true")
    args = parser.parse_args()

    ensure_dir(INPUT_DIR)
    ensure_dir(OUT_DIR)

    input_path = Path(args.input_file)
    output_path = TECHNICAL_FEATURES_SAMPLE_PATH if args.sample else TECHNICAL_FEATURES_PATH
    summary_path = SUMMARY_SAMPLE_PATH if args.sample else SUMMARY_PATH
    companies = load_companies()

    if not input_path.exists():
        export_template(TECHNICALS_TEMPLATE_PATH, companies)
        summary = {
            "input_file": str(input_path),
            "template_file": str(TECHNICALS_TEMPLATE_PATH),
            "rows_loaded": 0,
            "rows_written": 0,
            "message": "Brak pliku z technikaliami. Wygenerowano szablon do uzupelnienia.",
            "is_sample": args.sample,
        }
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return

    rows = load_input_rows(input_path, args.limit_rows)
    metric_bounds = {metric_name: build_bounds(rows, metric_name) for metric_name in METRIC_WEIGHTS}

    rows_written = 0
    with output_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            normalized_metrics: dict[str, float] = {}
            available_weight = 0.0
            weighted_score = 0.0

            for metric_name, weight in METRIC_WEIGHTS.items():
                normalized = normalize_value(
                    row.get(metric_name),
                    metric_bounds[metric_name],
                    inverse=metric_name in INVERSE_METRICS,
                )
                if normalized is None:
                    continue
                normalized_metrics[metric_name] = round(normalized, 4)
                available_weight += weight
                weighted_score += normalized * weight

            technical_score = None
            if available_weight > 0:
                technical_score = round(100 * (weighted_score / available_weight), 2)

            feature_row = {
                "symbol": row["symbol"],
                "company_name": row["company_name"],
                "source": row["source"],
                "as_of_date": row["as_of_date"],
                "momentum_30d": row.get("momentum_30d"),
                "momentum_90d": row.get("momentum_90d"),
                "volatility_30d": row.get("volatility_30d"),
                "drawdown_90d": row.get("drawdown_90d"),
                "normalized_metrics": normalized_metrics,
                "technical_completeness": round(available_weight, 4),
                "technical_metric_count": len(normalized_metrics),
                "technical_score": technical_score,
                "technical_metric_version": "technical-v1-manual",
            }
            handle.write(json.dumps(feature_row, ensure_ascii=False) + "\n")
            rows_written += 1

    summary = {
        "input_file": str(input_path),
        "template_file": str(TECHNICALS_TEMPLATE_PATH),
        "output_file": str(output_path),
        "rows_loaded": len(rows),
        "rows_written": rows_written,
        "companies_universe": len(companies),
        "metric_bounds": metric_bounds,
        "is_sample": args.sample,
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
