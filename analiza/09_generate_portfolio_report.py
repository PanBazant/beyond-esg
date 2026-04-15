from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT_DIR / "analiza" / "out"
REPORTS_DIR = OUT_DIR / "reports"
PROFILES_DIR = ROOT_DIR / "analiza" / "profiles"

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.schemas import PortfolioPreviewRequest
from backend.app.services.presets import PRESETS
from backend.app.services.reporting import generate_portfolio_report


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def load_profile_from_preset(preset_id: str) -> dict:
    for preset in PRESETS:
        if preset.id != preset_id:
            continue
        data = preset.model_dump()
        return {
            "profile_name": preset.id,
            "categories": [],
            "custom_esg_mode": data["custom_esg_mode"],
            "profitability_mode": data["profitability_mode"],
            "technical_mode": data["technical_mode"],
            "market_cap_mode": data["market_cap_mode"],
            "weighting_mode": data["weighting_mode"],
            "score_weights": data["score_weights"],
            "min_posts": 30,
            "portfolio_size": 10,
            "max_holding_weight": 0.25,
            "max_companies_per_category": 2,
            "min_distinct_categories": 3,
            "strict_category_limit": False,
        }
    raise ValueError(f"Nie znaleziono presetu o id '{preset_id}'.")


def load_profile_file(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def merge_dict(base: dict, override: dict) -> dict:
    merged = {**base}
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    return merged
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preset-id", type=str, default="balanced_signal")
    parser.add_argument("--profile-file", type=str, default=None)
    parser.add_argument("--output-name", type=str, default=None)
    args = parser.parse_args()

    ensure_dir(OUT_DIR)
    ensure_dir(REPORTS_DIR)
    ensure_dir(PROFILES_DIR)

    payload = load_profile_from_preset(args.preset_id)
    if args.profile_file:
        payload = merge_dict(payload, load_profile_file(Path(args.profile_file)))

    request = PortfolioPreviewRequest(**payload)
    report = generate_portfolio_report(request, output_name=args.output_name or request.profile_name or args.preset_id)

    summary = {
        "preset_id": args.preset_id,
        "profile_file": args.profile_file,
        "output_json": report.json_file,
        "output_markdown": report.markdown_file,
        "selected_companies": report.preview.summary.selected_companies,
        "distinct_categories": report.preview.summary.distinct_categories,
        "matched_companies": report.preview.matched_companies,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
