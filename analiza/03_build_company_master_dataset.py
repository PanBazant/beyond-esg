from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.instrument_universe import INSTRUMENT_UNIVERSE_LABELS, classify_instrument

SCRAPPER_DIR = ROOT_DIR / "scrapper"
OUT_DIR = ROOT_DIR / "analiza" / "out"
MERGED_FLAT_PATH = SCRAPPER_DIR / "merged_flat_stocktwits.jsonl"
SOCIAL_FEATURES_PATH = OUT_DIR / "company_social_features.jsonl"
SOCIAL_FEATURES_SAMPLE_PATH = OUT_DIR / "company_social_features_sample.jsonl"
COMMENT_ESG_FEATURES_PATH = OUT_DIR / "company_comment_esg_features.jsonl"
COMMENT_ESG_FEATURES_SAMPLE_PATH = OUT_DIR / "company_comment_esg_features_sample.jsonl"
PROFITABILITY_FEATURES_PATH = OUT_DIR / "company_profitability_features.jsonl"
PROFITABILITY_FEATURES_SAMPLE_PATH = OUT_DIR / "company_profitability_features_sample.jsonl"
TECHNICAL_FEATURES_PATH = OUT_DIR / "company_technical_features.jsonl"
TECHNICAL_FEATURES_SAMPLE_PATH = OUT_DIR / "company_technical_features_sample.jsonl"
REAL_ESG_FEATURES_PATH = OUT_DIR / "company_real_esg_benchmark.jsonl"
MASTER_JSONL_PATH = OUT_DIR / "company_master_dataset.jsonl"
MASTER_CSV_PATH = OUT_DIR / "company_master_dataset.csv"
SUMMARY_PATH = OUT_DIR / "company_master_summary.json"
MASTER_JSONL_SAMPLE_PATH = OUT_DIR / "company_master_dataset_sample.jsonl"
MASTER_CSV_SAMPLE_PATH = OUT_DIR / "company_master_dataset_sample.csv"
SUMMARY_SAMPLE_PATH = OUT_DIR / "company_master_sample_summary.json"

MONEY_PATTERN = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*([KMBT])?", re.IGNORECASE)
SUFFIX_MULTIPLIER = {
    "K": 1_000,
    "M": 1_000_000,
    "B": 1_000_000_000,
    "T": 1_000_000_000_000,
}


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def parse_market_cap(value: str | None) -> float | None:
    if not value:
        return None

    match = MONEY_PATTERN.search(str(value).replace(",", "").upper())
    if not match:
        return None

    base = float(match.group(1))
    suffix = (match.group(2) or "").upper()
    return base * SUFFIX_MULTIPLIER.get(suffix, 1)


def load_signal_features(path: Path) -> dict[str, dict]:
    by_symbol: dict[str, dict] = {}
    if not path.exists():
        return by_symbol

    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            row = json.loads(line)
            by_symbol[str(row["symbol"]).upper()] = row
    return by_symbol


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

            market_cap_label = row.get("cmc_market_cap") or row.get("st_market_cap")
            instrument_universe, instrument_reason = classify_instrument(
                company_name=row.get("st_company_name") or row.get("cmc_company_name") or symbol,
                industry=row.get("st_industry"),
                category=row.get("category"),
                symbol_href=row.get("st_symbol_href"),
                company_href=row.get("st_company_href"),
            )
            by_symbol[symbol] = {
                "symbol": symbol,
                "company_name": row.get("st_company_name") or row.get("cmc_company_name") or symbol,
                "category": row.get("category") or "Unknown",
                "industry": row.get("st_industry"),
                "market_cap_label": market_cap_label,
                "market_cap_numeric": parse_market_cap(market_cap_label),
                "rank_in_category": row.get("cmc_rank_in_category"),
                "cmc_symbol_raw": row.get("cmc_symbol_raw"),
                "st_symbol": row.get("st_symbol"),
                "st_symbol_href": row.get("st_symbol_href"),
                "instrument_universe": instrument_universe,
                "instrument_universe_label": INSTRUMENT_UNIVERSE_LABELS[instrument_universe],
                "instrument_universe_reason": instrument_reason,
            }

    return [by_symbol[key] for key in sorted(by_symbol)]


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--social-features-file", type=str, default=None)
    parser.add_argument("--comment-esg-file", type=str, default=None)
    parser.add_argument("--profitability-features-file", type=str, default=None)
    parser.add_argument("--technical-features-file", type=str, default=None)
    parser.add_argument("--real-esg-features-file", type=str, default=None)
    parser.add_argument("--sample", action="store_true")
    args = parser.parse_args()

    ensure_dir(OUT_DIR)
    social_path = Path(args.social_features_file) if args.social_features_file else (SOCIAL_FEATURES_SAMPLE_PATH if args.sample else SOCIAL_FEATURES_PATH)
    comment_esg_path = Path(args.comment_esg_file) if args.comment_esg_file else (COMMENT_ESG_FEATURES_SAMPLE_PATH if args.sample else COMMENT_ESG_FEATURES_PATH)
    profitability_path = Path(args.profitability_features_file) if args.profitability_features_file else (PROFITABILITY_FEATURES_SAMPLE_PATH if args.sample else PROFITABILITY_FEATURES_PATH)
    technical_path = Path(args.technical_features_file) if args.technical_features_file else (TECHNICAL_FEATURES_SAMPLE_PATH if args.sample else TECHNICAL_FEATURES_PATH)
    real_esg_path = Path(args.real_esg_features_file) if args.real_esg_features_file else REAL_ESG_FEATURES_PATH
    master_jsonl_path = MASTER_JSONL_SAMPLE_PATH if args.sample else MASTER_JSONL_PATH
    master_csv_path = MASTER_CSV_SAMPLE_PATH if args.sample else MASTER_CSV_PATH
    summary_path = SUMMARY_SAMPLE_PATH if args.sample else SUMMARY_PATH

    social = load_signal_features(social_path)
    comment_esg = load_signal_features(comment_esg_path)
    profitability = load_signal_features(profitability_path)
    technical = load_signal_features(technical_path)
    real_esg = load_signal_features(real_esg_path)
    companies = load_companies()

    fieldnames = [
        "symbol",
        "company_name",
        "category",
        "industry",
        "instrument_universe",
        "instrument_universe_label",
        "instrument_universe_reason",
        "market_cap_label",
        "market_cap_numeric",
        "rank_in_category",
        "cmc_symbol_raw",
        "st_symbol",
        "st_symbol_href",
        "posts_count",
        "text_posts_count",
        "authors_count",
        "avg_sentiment",
        "positive_share",
        "negative_share",
        "neutral_share",
        "controversy_score",
        "coverage_score",
        "author_diversity_score",
        "sector_norm_prior",
        "custom_esg_proxy_score",
        "custom_esg_confidence",
        "custom_esg_axes_json",
        "custom_esg_families_json",
        "custom_esg_summary_axes_json",
        "custom_esg_axis_1_label",
        "custom_esg_axis_1_score",
        "custom_esg_axis_1_exposure",
        "custom_esg_axis_1_confidence",
        "custom_esg_axis_2_label",
        "custom_esg_axis_2_score",
        "custom_esg_axis_2_exposure",
        "custom_esg_axis_2_confidence",
        "custom_esg_axis_3_label",
        "custom_esg_axis_3_score",
        "custom_esg_axis_3_exposure",
        "custom_esg_axis_3_confidence",
        "metric_version",
        "custom_esg_metric_version",
        "custom_value_dimensions_metric_version",
        "real_esg_total_score",
        "real_esg_environment_score",
        "real_esg_social_score",
        "real_esg_governance_score",
        "real_esg_source",
        "real_esg_as_of_date",
        "net_margin",
        "operating_margin",
        "roe",
        "roa",
        "revenue_growth",
        "profitability_completeness",
        "profitability_metric_count",
        "profitability_score",
        "profitability_metric_version",
        "fundamentals_source",
        "fundamentals_as_of_date",
        "momentum_30d",
        "momentum_90d",
        "volatility_30d",
        "drawdown_90d",
        "technical_completeness",
        "technical_metric_count",
        "technical_score",
        "technical_metric_version",
        "technicals_source",
        "technicals_as_of_date",
    ]

    rows_written = 0
    instrument_counts: dict[str, int] = {}
    with master_jsonl_path.open("w", encoding="utf-8") as jsonl_handle, master_csv_path.open("w", encoding="utf-8", newline="") as csv_handle:
        writer = csv.DictWriter(csv_handle, fieldnames=fieldnames)
        writer.writeheader()

        for company in companies:
            signal = social.get(company["symbol"], {})
            comment_row = comment_esg.get(company["symbol"], {})
            fundamentals = profitability.get(company["symbol"], {})
            technicals = technical.get(company["symbol"], {})
            real_esg_row = real_esg.get(company["symbol"], {})
            summary_axes = list(comment_row.get("custom_esg_summary_axes", []))

            def axis_value(index: int, key: str):
                if index < len(summary_axes):
                    return summary_axes[index].get(key)
                return None

            row = {
                **company,
                "posts_count": signal.get("posts_count", 0),
                "text_posts_count": signal.get("text_posts_count", 0),
                "authors_count": signal.get("authors_count", 0),
                "avg_sentiment": signal.get("avg_sentiment"),
                "positive_share": signal.get("positive_share"),
                "negative_share": signal.get("negative_share"),
                "neutral_share": signal.get("neutral_share"),
                "controversy_score": signal.get("controversy_score"),
                "coverage_score": signal.get("coverage_score"),
                "author_diversity_score": signal.get("author_diversity_score"),
                "sector_norm_prior": signal.get("sector_norm_prior"),
                "custom_esg_axes": comment_row.get("custom_esg_axes", []),
                "custom_esg_families": comment_row.get("custom_esg_families", []),
                "custom_esg_summary_axes": summary_axes,
                "custom_esg_proxy_score": comment_row.get("custom_esg_proxy_score", signal.get("custom_esg_proxy_score")),
                "custom_esg_confidence": comment_row.get("custom_esg_confidence"),
                "custom_esg_axes_json": json.dumps(comment_row.get("custom_esg_axes", []), ensure_ascii=False),
                "custom_esg_families_json": json.dumps(comment_row.get("custom_esg_families", []), ensure_ascii=False),
                "custom_esg_summary_axes_json": json.dumps(summary_axes, ensure_ascii=False),
                "custom_esg_axis_1_label": axis_value(0, "axis_label"),
                "custom_esg_axis_1_score": axis_value(0, "axis_score"),
                "custom_esg_axis_1_exposure": axis_value(0, "axis_exposure"),
                "custom_esg_axis_1_confidence": axis_value(0, "axis_confidence"),
                "custom_esg_axis_2_label": axis_value(1, "axis_label"),
                "custom_esg_axis_2_score": axis_value(1, "axis_score"),
                "custom_esg_axis_2_exposure": axis_value(1, "axis_exposure"),
                "custom_esg_axis_2_confidence": axis_value(1, "axis_confidence"),
                "custom_esg_axis_3_label": axis_value(2, "axis_label"),
                "custom_esg_axis_3_score": axis_value(2, "axis_score"),
                "custom_esg_axis_3_exposure": axis_value(2, "axis_exposure"),
                "custom_esg_axis_3_confidence": axis_value(2, "axis_confidence"),
                "metric_version": signal.get("metric_version"),
                "custom_esg_metric_version": comment_row.get("custom_esg_metric_version"),
                "custom_value_dimensions_metric_version": comment_row.get("custom_value_dimensions_metric_version"),
                "real_esg_total_score": real_esg_row.get("total_esg_score"),
                "real_esg_environment_score": real_esg_row.get("environment_score"),
                "real_esg_social_score": real_esg_row.get("social_score"),
                "real_esg_governance_score": real_esg_row.get("governance_score"),
                "real_esg_source": real_esg_row.get("source"),
                "real_esg_as_of_date": real_esg_row.get("as_of_date"),
                "net_margin": fundamentals.get("net_margin"),
                "operating_margin": fundamentals.get("operating_margin"),
                "roe": fundamentals.get("roe"),
                "roa": fundamentals.get("roa"),
                "revenue_growth": fundamentals.get("revenue_growth"),
                "profitability_completeness": fundamentals.get("profitability_completeness"),
                "profitability_metric_count": fundamentals.get("profitability_metric_count"),
                "profitability_score": fundamentals.get("profitability_score"),
                "profitability_metric_version": fundamentals.get("profitability_metric_version"),
                "fundamentals_source": fundamentals.get("source"),
                "fundamentals_as_of_date": fundamentals.get("as_of_date"),
                "momentum_30d": technicals.get("momentum_30d"),
                "momentum_90d": technicals.get("momentum_90d"),
                "volatility_30d": technicals.get("volatility_30d"),
                "drawdown_90d": technicals.get("drawdown_90d"),
                "technical_completeness": technicals.get("technical_completeness"),
                "technical_metric_count": technicals.get("technical_metric_count"),
                "technical_score": technicals.get("technical_score"),
                "technical_metric_version": technicals.get("technical_metric_version"),
                "technicals_source": technicals.get("source"),
                "technicals_as_of_date": technicals.get("as_of_date"),
            }
            jsonl_handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            csv_row = {key: row.get(key) for key in fieldnames}
            writer.writerow(csv_row)
            rows_written += 1
            instrument_key = str(row.get("instrument_universe") or "ambiguous")
            instrument_counts[instrument_key] = instrument_counts.get(instrument_key, 0) + 1

    summary = {
        "input_merged_file": str(MERGED_FLAT_PATH),
        "input_social_features_file": str(social_path),
        "input_comment_esg_file": str(comment_esg_path),
        "input_real_esg_file": str(real_esg_path),
        "input_profitability_features_file": str(profitability_path),
        "input_technical_features_file": str(technical_path),
        "rows_written": rows_written,
        "output_jsonl": str(master_jsonl_path),
        "output_csv": str(master_csv_path),
        "social_features_present": len(social),
        "comment_esg_features_present": len(comment_esg),
        "real_esg_features_present": len(real_esg),
        "profitability_features_present": len(profitability),
        "technical_features_present": len(technical),
        "instrument_universe_counts": instrument_counts,
        "is_sample": args.sample,
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
