from __future__ import annotations

import argparse
import json
import math
import sys
from typing import Any
from urllib import error, request


DEFAULT_BASE_URL = "http://127.0.0.1:8000/api/v1"


def fetch_json(base_url: str, path: str, payload: dict[str, Any] | None = None, method: str | None = None) -> Any:
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    body = None
    headers = {"Accept": "application/json"}

    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = request.Request(url, data=body, headers=headers, method=method or ("POST" if body else "GET"))
    with request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test for the FastAPI selection backend.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base URL, e.g. http://127.0.0.1:8000/api/v1")
    args = parser.parse_args()

    try:
        health = fetch_json(args.base_url, "/health")
        assert_true(health.get("status") == "ok", "Health endpoint did not return status=ok.")

        catalog = fetch_json(args.base_url, "/catalog")
        categories = catalog.get("categories", [])
        metrics = catalog.get("metrics", {})
        custom_esg_axes = catalog.get("custom_esg_axes", [])
        instrument_universes = catalog.get("instrument_universes", [])
        assert_true(bool(categories), "Catalog returned no categories.")
        assert_true(catalog.get("companies_count", 0) > 0, "Catalog returned zero companies.")
        assert_true(metrics.get("custom_esg") is True, "Custom ESG should already be available in the master dataset.")
        assert_true(bool(custom_esg_axes), "Catalog should expose discovered custom ESG axes.")
        assert_true(bool(instrument_universes), "Catalog should expose instrument universe definitions.")
        assert_true(
            not any(item.get("id") == "fund_etf_trust" for item in instrument_universes),
            "Instrument catalog should no longer expose fund/ETF universe as a selectable portfolio input.",
        )
        assert_true(any(item.get("id") == "common_equity" for item in instrument_universes), "Instrument catalog should expose the stock universe.")

        profiles_doc = fetch_json(args.base_url, "/profiles")
        profiles = profiles_doc.get("profiles", [])
        assert_true(bool(profiles), "Profiles endpoint returned no presets.")
        first_profile = profiles[0]

        data_status = fetch_json(args.base_url, "/data/status")
        assert_true(data_status.get("master_dataset_exists") is True, "Data status should report an existing master dataset.")
        assert_true(isinstance(data_status.get("raw_upload_files", []), list), "Data status should expose upload file list.")
        assert_true(data_status.get("fundamentals", {}).get("template_exists") in {True, False}, "Fundamentals status is malformed.")

        fundamentals_worklist = fetch_json(args.base_url, "/data/worklists/fundamentals?min_posts=30&limit=10&only_missing=true")
        assert_true(isinstance(fundamentals_worklist.get("rows", []), list), "Fundamentals worklist should return a row list.")
        assert_true(fundamentals_worklist.get("output_file"), "Fundamentals worklist should expose output path.")

        saved_profiles_doc = fetch_json(args.base_url, "/profiles/saved")
        saved_profiles_before = saved_profiles_doc.get("saved_profiles", [])

        selected_categories = [item["name"] for item in categories[:3]]
        payload = {
            "profile_name": "smoke-test",
            "categories": selected_categories,
            "allowed_instrument_universes": ["common_equity"],
            "custom_esg_mode": first_profile["custom_esg_mode"],
            "profitability_mode": first_profile["profitability_mode"],
            "technical_mode": first_profile["technical_mode"],
            "market_cap_mode": first_profile["market_cap_mode"],
            "weighting_mode": first_profile["weighting_mode"],
            "max_holding_weight": 0.25,
            "max_companies_per_category": 2,
            "min_distinct_categories": 2,
            "strict_category_limit": False,
            "score_weights": first_profile["score_weights"],
            "axis_preferences": [
                {
                    "axis_id": custom_esg_axes[0]["axis_id"],
                    "axis_label": custom_esg_axes[0]["label"],
                    "mode": "prefer_low",
                    "importance": 0.8,
                }
            ],
            "min_posts": 30,
            "portfolio_size": 10,
        }

        preview = fetch_json(args.base_url, "/portfolio/preview", payload=payload)
        holdings = preview.get("holdings", [])
        companies = preview.get("companies", [])
        summary = preview.get("summary", {})
        score_weights = preview.get("score_weights", {})
        comparison = preview.get("comparison")

        assert_true(bool(holdings), "Portfolio preview returned no holdings.")
        assert_true(bool(companies), "Portfolio preview returned no ranked companies.")
        assert_true(preview.get("matched_companies", 0) >= len(holdings), "Matched companies count is inconsistent.")
        assert_true(summary.get("selected_companies") == len(holdings), "Summary selected_companies does not match holdings length.")
        assert_true("technical_alignment" in score_weights, "Technical alignment weight is missing from response.")
        assert_true(bool(comparison), "Portfolio preview should include benchmark comparison.")
        assert_true(bool(comparison.get("benchmark", {}).get("holdings", [])), "Benchmark comparison should include holdings.")

        weights_sum = sum(item.get("weight", 0.0) for item in holdings)
        assert_true(math.isclose(weights_sum, 1.0, rel_tol=1e-3, abs_tol=1e-3), f"Holdings weights should sum to 1.0, got {weights_sum:.6f}.")

        first_company = companies[0]
        assert_true("score_breakdown" in first_company, "Company preview is missing score_breakdown.")
        assert_true("technical_alignment" in first_company["score_breakdown"], "Company score_breakdown is missing technical_alignment.")
        assert_true(
            str(first_company.get("custom_esg_metric_version") or "").startswith("custom-esg-v"),
            "Company preview is not exposing the current ESG abstraction model version.",
        )
        assert_true(first_company.get("instrument_universe") in {"common_equity", "reit"}, "Preview should surface instrument universe class.")
        assert_true(bool(first_company.get("instrument_universe_label")), "Preview should surface human-readable instrument universe label.")
        assert_true(isinstance(first_company.get("custom_esg_axes"), list), "Company preview is missing custom ESG axes.")
        assert_true(bool(first_company.get("custom_esg_axes")), "Company preview should contain populated custom ESG axes.")
        assert_true(first_company["custom_esg_axes"][0].get("summary"), "Custom ESG axis preview is missing summary metadata.")
        assert_true(first_company["custom_esg_axes"][0].get("label"), "Custom ESG axis preview is missing label.")
        assert_true(isinstance(first_company["custom_esg_axes"][0].get("examples"), list), "Custom ESG axis preview examples should be a list.")
        assert_true(
            any("ETF-y" in warning or "fundusze" in warning or "REIT-y" in warning for warning in preview.get("warnings", [])),
            "Preview should explain that ETF-like instruments are excluded and REITs are folded into the stock universe.",
        )

        report = fetch_json(args.base_url, "/portfolio/report", payload=payload)
        assert_true(bool(report.get("markdown")), "Portfolio report returned empty markdown.")
        assert_true(report.get("file_slug"), "Portfolio report is missing file slug.")
        assert_true(report.get("preview", {}).get("summary", {}).get("selected_companies") == len(holdings), "Report preview summary is inconsistent.")

        temp_profile = fetch_json(
            args.base_url,
            "/profiles/saved",
            payload={
                **payload,
                "profile_id": None,
                "description": "Profil testowy tworzony automatycznie przez smoke test.",
            },
        )
        temp_profile_id = temp_profile.get("profile_id")
        assert_true(bool(temp_profile_id), "Saved profile response is missing profile_id.")

        saved_profiles_after_create = fetch_json(args.base_url, "/profiles/saved")
        found_temp = any(item.get("profile_id") == temp_profile_id for item in saved_profiles_after_create.get("saved_profiles", []))
        assert_true(found_temp, "Saved profile was not visible in catalog after creation.")

        delete_result = fetch_json(args.base_url, f"/profiles/saved/{temp_profile_id}", method="DELETE")
        assert_true(delete_result.get("deleted") is True, "Saved profile delete endpoint did not confirm deletion.")

        saved_profiles_after_delete = fetch_json(args.base_url, "/profiles/saved")
        found_after_delete = any(item.get("profile_id") == temp_profile_id for item in saved_profiles_after_delete.get("saved_profiles", []))
        assert_true(not found_after_delete, "Temporary smoke-test profile still exists after deletion.")

        smoke_report = {
            "status": "ok",
            "base_url": args.base_url,
            "categories_count": catalog.get("categories_count"),
            "companies_count": catalog.get("companies_count"),
            "profiles_count": len(profiles),
            "saved_profiles_before": len(saved_profiles_before),
            "saved_profiles_after": len(saved_profiles_after_delete.get("saved_profiles", [])),
            "matched_companies": preview.get("matched_companies"),
            "selected_companies": len(holdings),
            "report_slug": report.get("file_slug"),
            "warnings": preview.get("warnings", []),
            "metrics": preview.get("metrics", {}),
        }
        print(json.dumps(smoke_report, indent=2, ensure_ascii=False))
        return 0
    except (AssertionError, error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"SMOKE TEST FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
