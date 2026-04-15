from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from .instrument_universe import (
    INSTRUMENT_UNIVERSE_LABELS,
    build_instrument_universe_catalog,
    classify_instrument,
)


ROOT_DIR = Path(__file__).resolve().parents[3]
SCRAPPER_DIR = ROOT_DIR / "scrapper"
ANALYSIS_DIR = ROOT_DIR / "analiza" / "out"
NON_GEO_INDEX_PATH = SCRAPPER_DIR / "cmc_out" / "non_geo_cleaned_index.json"
MERGED_FLAT_PATH = SCRAPPER_DIR / "merged_flat_stocktwits.jsonl"
MEDIA_SAMPLE_DIR = SCRAPPER_DIR / "media_sample"
MASTER_DATASET_PATH = ANALYSIS_DIR / "company_master_dataset.jsonl"
COMMENT_ESG_SUMMARY_PATH = ANALYSIS_DIR / "comment_esg_axes_summary.json"

MONEY_PATTERN = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*([KMBT])?", re.IGNORECASE)
LEADING_NOISE_PATTERN = re.compile(r"^[^A-Za-z0-9]+")
MULTISPACE_PATTERN = re.compile(r"\s+")
SUFFIX_MULTIPLIER = {
    "K": 1_000,
    "M": 1_000_000,
    "B": 1_000_000_000,
    "T": 1_000_000_000_000,
}

_CACHE: dict[str, dict[str, Any]] = {}


def _path_signature(path: Path) -> tuple[int, int] | None:
    if not path.exists():
        return None
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_size


def _cache_get(cache_key: str, signature: object) -> Any | None:
    entry = _CACHE.get(cache_key)
    if not entry:
        return None
    if entry.get("signature") != signature:
        return None
    return entry.get("value")


def _cache_set(cache_key: str, signature: object, value: Any) -> Any:
    _CACHE[cache_key] = {"signature": signature, "value": value}
    return value


def _symbol_key(row: dict) -> str:
    symbol = row.get("st_url_symbol") or row.get("st_symbol") or ""
    return str(symbol).strip().upper().replace("-", ".")


def _parse_market_cap(value: str | None) -> float | None:
    if not value:
        return None

    match = MONEY_PATTERN.search(str(value).replace(",", "").upper())
    if not match:
        return None

    base = float(match.group(1))
    suffix = (match.group(2) or "").upper()
    multiplier = SUFFIX_MULTIPLIER.get(suffix, 1)
    return base * multiplier


def _normalize_label(value: str | None) -> str:
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


def load_category_catalog() -> list[dict]:
    if not NON_GEO_INDEX_PATH.exists():
        return []

    signature = _path_signature(NON_GEO_INDEX_PATH)
    cached = _cache_get("category_catalog", signature)
    if cached is not None:
        return cached

    doc = json.loads(NON_GEO_INDEX_PATH.read_text(encoding="utf-8"))
    raw_categories = doc.get("categories", [])
    categories = []
    for item in raw_categories:
        slug = str(item.get("slug", "")).strip()
        name = _normalize_label(item.get("name", slug))
        if slug and name:
            categories.append({"slug": slug, "name": name})
    return _cache_set("category_catalog", signature, sorted(categories, key=lambda item: item["name"].lower()))


def load_post_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    if not MEDIA_SAMPLE_DIR.exists():
        return counts

    for symbol_dir in MEDIA_SAMPLE_DIR.iterdir():
        if not symbol_dir.is_dir():
            continue

        runs_dir = symbol_dir / "runs"
        if not runs_dir.exists():
            counts[symbol_dir.name.upper()] = 0
            continue

        run_dirs = [entry for entry in runs_dir.iterdir() if entry.is_dir()]
        if not run_dirs:
            counts[symbol_dir.name.upper()] = 0
            continue

        latest_run = sorted(run_dirs, key=lambda item: item.name)[-1]
        messages_dir = latest_run / "messages"
        if not messages_dir.exists():
            counts[symbol_dir.name.upper()] = 0
            continue

        counts[symbol_dir.name.upper()] = sum(1 for item in messages_dir.iterdir() if item.is_dir())

    return counts


def load_comment_esg_axes_catalog() -> list[dict]:
    if not COMMENT_ESG_SUMMARY_PATH.exists():
        return []

    signature = _path_signature(COMMENT_ESG_SUMMARY_PATH)
    cached = _cache_get("comment_esg_axes_catalog", signature)
    if cached is not None:
        return cached

    doc = json.loads(COMMENT_ESG_SUMMARY_PATH.read_text(encoding="utf-8"))
    axes = []
    for item in doc.get("axes", []):
        axis_id = int(item.get("axis_id", len(axes)))
        label = str(item.get("axis_display_label") or item.get("axis_label") or f"Axis {axis_id + 1}").strip()
        summary = str(item.get("axis_summary") or "").strip() or None
        keywords = [str(keyword).strip() for keyword in item.get("keywords", []) if str(keyword).strip()]
        topic_labels = [str(topic_label).strip() for topic_label in item.get("topic_labels", []) if str(topic_label).strip()]
        examples = [str(example).strip() for example in item.get("examples", []) if str(example).strip()]
        axes.append(
            {
                "axis_id": axis_id,
                "label": label,
                "family_id": item.get("axis_family_id"),
                "family_label": item.get("axis_family_label"),
                "summary": summary,
                "keywords": keywords,
                "topic_labels": topic_labels,
                "examples": examples,
                "topic_count": int(item.get("topic_count", len(topic_labels))),
            }
        )

    return _cache_set("comment_esg_axes_catalog", signature, sorted(axes, key=lambda item: item["axis_id"]))


def load_comment_esg_family_catalog() -> list[dict]:
    if not COMMENT_ESG_SUMMARY_PATH.exists():
        return []

    signature = _path_signature(COMMENT_ESG_SUMMARY_PATH)
    cached = _cache_get("comment_esg_family_catalog", signature)
    if cached is not None:
        return cached

    doc = json.loads(COMMENT_ESG_SUMMARY_PATH.read_text(encoding="utf-8"))
    families = []
    for index, item in enumerate(doc.get("families", [])):
        family_id = str(item.get("family_id") or f"family-{index}").strip()
        if not family_id:
            continue
        label = str(item.get("family_label") or family_id).strip()
        if not label:
            continue
        families.append(
            {
                "family_id": family_id,
                "label": label,
                "summary": str(item.get("family_summary") or "").strip() or None,
                "dominant_axis_code": str(item.get("dominant_axis_code") or "").strip() or None,
                "dominant_axis_label": str(item.get("dominant_axis_label") or "").strip() or None,
                "keywords": [str(keyword).strip() for keyword in item.get("keywords", []) if str(keyword).strip()],
                "examples": [str(example).strip() for example in item.get("examples", []) if str(example).strip()],
                "topic_labels": [str(topic_label).strip() for topic_label in item.get("topic_labels", []) if str(topic_label).strip()],
                "member_axis_ids": [int(axis_id) for axis_id in item.get("member_axis_ids", [])],
                "member_dimensions_count": int(item.get("member_dimensions_count", 0)),
                "esg_relevance": float(item.get("esg_relevance", 0.0) or 0.0),
            }
        )

    families.sort(key=lambda item: (-(item["esg_relevance"]), item["label"].lower()))
    return _cache_set("comment_esg_family_catalog", signature, families)


def load_company_records() -> list[dict]:
    if MASTER_DATASET_PATH.exists():
        signature = _path_signature(MASTER_DATASET_PATH)
        cached = _cache_get("company_records_master", signature)
        if cached is not None:
            return cached

        rows = []
        with MASTER_DATASET_PATH.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
        for row in rows:
            row["category"] = _normalize_label(row.get("category"))
            if not row.get("instrument_universe"):
                instrument_universe, instrument_reason = classify_instrument(
                    company_name=row.get("company_name"),
                    industry=row.get("industry"),
                    category=row.get("category"),
                    symbol_href=row.get("st_symbol_href"),
                    company_href=row.get("company_href"),
                )
                row["instrument_universe"] = instrument_universe
                row["instrument_universe_label"] = INSTRUMENT_UNIVERSE_LABELS[instrument_universe]
                row["instrument_universe_reason"] = instrument_reason
        return _cache_set("company_records_master", signature, sorted(rows, key=lambda item: item["symbol"]))

    if not MERGED_FLAT_PATH.exists():
        return []

    post_counts = load_post_counts()
    by_symbol: dict[str, dict] = {}

    with MERGED_FLAT_PATH.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue

            row = json.loads(line)
            symbol = _symbol_key(row)
            if not symbol:
                continue

            rank = row.get("cmc_rank_in_category")
            current = by_symbol.get(symbol)
            if current is not None:
                current_rank = current.get("rank_in_category") or math.inf
                next_rank = rank or math.inf
                if next_rank >= current_rank:
                    continue

            by_symbol[symbol] = {
                "symbol": symbol,
                "company_name": row.get("st_company_name") or row.get("cmc_company_name") or symbol,
                "category": _normalize_label(row.get("category")),
                "industry": row.get("st_industry"),
                "market_cap_label": row.get("cmc_market_cap") or row.get("st_market_cap"),
                "market_cap_numeric": _parse_market_cap(row.get("cmc_market_cap") or row.get("st_market_cap")),
                "rank_in_category": rank,
                "posts_count": post_counts.get(symbol, 0),
            }
            instrument_universe, instrument_reason = classify_instrument(
                company_name=by_symbol[symbol]["company_name"],
                industry=by_symbol[symbol]["industry"],
                category=by_symbol[symbol]["category"],
                symbol_href=row.get("st_symbol_href"),
                company_href=row.get("st_company_href"),
            )
            by_symbol[symbol]["instrument_universe"] = instrument_universe
            by_symbol[symbol]["instrument_universe_label"] = INSTRUMENT_UNIVERSE_LABELS[instrument_universe]
            by_symbol[symbol]["instrument_universe_reason"] = instrument_reason

    signature = (
        _path_signature(MERGED_FLAT_PATH),
        _path_signature(MEDIA_SAMPLE_DIR) if MEDIA_SAMPLE_DIR.exists() else None,
    )
    return _cache_set("company_records_fallback", signature, sorted(by_symbol.values(), key=lambda item: item["symbol"]))


def load_instrument_universe_catalog() -> list[dict]:
    companies = load_company_records()
    signature = tuple(
        (
            company.get("instrument_universe"),
            company.get("symbol"),
        )
        for company in companies
    )
    cached = _cache_get("instrument_universe_catalog", signature)
    if cached is not None:
        return cached
    return _cache_set("instrument_universe_catalog", signature, build_instrument_universe_catalog(companies))


def metric_availability(companies: list[dict] | None = None) -> dict[str, bool]:
    companies = companies if companies is not None else (load_company_records() if MASTER_DATASET_PATH.exists() else [])
    has_custom_esg = any(company.get("custom_esg_proxy_score") is not None for company in companies)
    has_profitability = any(company.get("profitability_score") is not None for company in companies)
    has_technicals = any(company.get("technical_score") is not None for company in companies)
    return {
        "categories": True,
        "market_cap": True,
        "posts_count": True,
        "custom_esg": has_custom_esg,
        "profitability": has_profitability,
        "technicals": has_technicals,
    }
