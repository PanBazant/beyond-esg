from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from ..schemas import PortfolioPreviewRequest, PortfolioPreviewResponse, PortfolioReportResponse
from .portfolio import build_portfolio_preview


ROOT_DIR = Path(__file__).resolve().parents[3]
REPORTS_DIR = ROOT_DIR / "analiza" / "out" / "reports"
SLUG_RE = re.compile(r"[^a-z0-9]+")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def slugify(value: str) -> str:
    return SLUG_RE.sub("-", value.strip().lower()).strip("-") or "portfolio-report"


def _build_report_payload(
    request: PortfolioPreviewRequest,
    preview: PortfolioPreviewResponse,
    generated_at: str,
) -> dict:
    return {
        "generated_at": generated_at,
        "profile": request.model_dump(),
        "matched_companies": preview.matched_companies,
        "metrics": preview.metrics.model_dump(),
        "score_weights": preview.score_weights.model_dump(),
        "weighting_mode": preview.weighting_mode,
        "warnings": preview.warnings,
        "summary": preview.summary.model_dump(),
        "category_allocations": [item.model_dump() for item in preview.category_allocations],
        "holdings": [item.model_dump() for item in preview.holdings],
        "companies": [item.model_dump() for item in preview.companies],
        "comparison": preview.comparison.model_dump() if preview.comparison else None,
    }


def build_markdown(report: dict) -> str:
    profile = report["profile"]
    summary = report["summary"]
    warnings = report["warnings"]
    holdings = report["holdings"]
    allocations = report["category_allocations"]
    companies = report["companies"]
    metrics = report["metrics"]
    comparison = report.get("comparison")

    def fmt(value: object) -> str:
        return "n/d" if value is None else str(value)

    lines: list[str] = []
    lines.append(f"# Raport Portfela: {profile['profile_name']}")
    lines.append("")
    lines.append(f"- Wygenerowano: {report['generated_at']}")
    lines.append(f"- Profil: `{profile['profile_name']}`")
    lines.append(f"- Wazenie portfela: `{report['weighting_mode']}`")
    lines.append("")
    lines.append("## Parametry")
    lines.append("")
    lines.append(f"- `custom_esg_mode`: `{profile['custom_esg_mode']}`")
    lines.append(f"- `profitability_mode`: `{profile['profitability_mode']}`")
    lines.append(f"- `technical_mode`: `{profile['technical_mode']}`")
    lines.append(f"- `market_cap_mode`: `{profile['market_cap_mode']}`")
    lines.append(f"- `min_posts`: `{profile['min_posts']}`")
    lines.append(f"- `portfolio_size`: `{profile['portfolio_size']}`")
    lines.append(f"- `max_holding_weight`: `{profile['max_holding_weight']}`")
    lines.append(f"- `max_companies_per_category`: `{profile['max_companies_per_category']}`")
    lines.append(f"- `min_distinct_categories`: `{profile['min_distinct_categories']}`")
    lines.append(
        f"- `allowed_instrument_universes`: `{', '.join(profile.get('allowed_instrument_universes', [])) or 'all'}`"
    )
    active_axis_preferences = [
        preference
        for preference in profile.get("axis_preferences", [])
        if preference.get("mode") != "neutral" and float(preference.get("importance") or 0) > 0
    ]
    if active_axis_preferences:
        lines.append("- `axis_preferences`:")
        for preference in active_axis_preferences:
            label = preference.get("axis_label") or f"axis_{preference.get('axis_id')}"
            lines.append(
                f"  - `{label}`: mode `{preference.get('mode')}`, importance `{preference.get('importance')}`"
            )
    lines.append("")
    lines.append("## Dostepnosc Metryk")
    lines.append("")
    for key, value in metrics.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")

    if warnings:
        lines.append("## Uwagi")
        lines.append("")
        for warning in warnings:
            lines.append(f"- {warning}")
        lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Spolki po filtracji: `{report['matched_companies']}`")
    lines.append(f"- Wybrane spolki: `{summary['selected_companies']}`")
    lines.append(f"- Rozne kategorie: `{summary['distinct_categories']}`")
    lines.append(f"- Sredni custom ESG: `{fmt(summary['average_custom_esg'])}`")
    lines.append(f"- Srednia rentownosc: `{fmt(summary['average_profitability'])}`")
    lines.append(f"- Srednia technika: `{fmt(summary['average_technical'])}`")
    lines.append(f"- Sredni sentyment: `{fmt(summary['average_sentiment'])}`")
    lines.append(f"- HHI koncentracji: `{summary['concentration_hhi']}`")
    lines.append(f"- Najwieksza waga: `{summary['max_holding_weight']}`")
    lines.append(f"- Dominujaca kategoria: `{fmt(summary['top_category'])}`")
    lines.append("")

    lines.append("## Holdings")
    lines.append("")
    lines.append("| Symbol | Spolka | Kategoria | Klasa instrumentu | Waga | Score |")
    lines.append("|---|---|---|---|---:|---:|")
    for holding in holdings:
        lines.append(
            f"| {holding['symbol']} | {holding['company_name']} | {holding['category']} | {holding.get('instrument_universe_label', 'n/d')} | {holding['weight']:.4f} | {holding['selection_score']:.4f} |"
        )
    lines.append("")

    lines.append("## Alokacja Kategorii")
    lines.append("")
    lines.append("| Kategoria | Liczba Spolek | Laczna Waga | Sredni Score |")
    lines.append("|---|---:|---:|---:|")
    for allocation in allocations:
        lines.append(
            f"| {allocation['category']} | {allocation['holdings_count']} | {allocation['total_weight']:.4f} | {allocation['average_selection_score']:.4f} |"
        )
    lines.append("")

    if comparison:
        benchmark = comparison["benchmark"]
        metrics_delta = comparison["metrics"]
        lines.append("## Porownanie Z Portfelem Referencyjnym")
        lines.append("")
        lines.append(f"- Benchmark: `{benchmark['label']}`")
        lines.append(f"- Overlap spolki: `{metrics_delta['overlap_count']}`")
        lines.append(f"- Overlap ratio: `{metrics_delta['overlap_ratio']}`")
        lines.append(f"- Delta custom ESG: `{fmt(metrics_delta['custom_esg_delta'])}`")
        lines.append(f"- Delta rentownosci: `{fmt(metrics_delta['profitability_delta'])}`")
        lines.append(f"- Delta techniki: `{fmt(metrics_delta['technical_delta'])}`")
        lines.append(f"- Delta sentymentu: `{fmt(metrics_delta['sentiment_delta'])}`")
        lines.append(f"- Delta liczby kategorii: `{fmt(metrics_delta['distinct_categories_delta'])}`")
        lines.append("")
        lines.append("| Benchmark Holding | Kategoria | Klasa instrumentu | Waga | Score |")
        lines.append("|---|---|---|---:|---:|")
        for holding in benchmark["holdings"]:
            lines.append(
                f"| {holding['symbol']} | {holding['category']} | {holding.get('instrument_universe_label', 'n/d')} | {holding['weight']:.4f} | {holding['selection_score']:.4f} |"
            )
        lines.append("")

    lines.append("## Wybrane Spolki")
    lines.append("")
    for company in companies:
        lines.append(f"### {company['symbol']} - {company['company_name']}")
        lines.append("")
        lines.append(f"- Kategoria: `{company['category']}`")
        lines.append(f"- Klasa instrumentu: `{company.get('instrument_universe_label', 'n/d')}`")
        if company.get("instrument_universe_reason"):
            lines.append(f"- Uzasadnienie klasy instrumentu: `{company['instrument_universe_reason']}`")
        lines.append(f"- Score: `{company['selection_score']}`")
        lines.append(f"- Custom ESG: `{fmt(company['custom_esg_proxy_score'])}`")
        if company.get("custom_esg_metric_version"):
            lines.append(f"- Model ESG: `{company['custom_esg_metric_version']}`")
        lines.append(f"- Profitability: `{fmt(company['profitability_score'])}`")
        lines.append(f"- Technical: `{fmt(company['technical_score'])}`")
        lines.append(f"- Sentyment: `{fmt(company['avg_sentiment'])}`")
        if company.get("custom_esg_axes"):
            lines.append("- Osi komentarzowego ESG:")
            for axis in company["custom_esg_axes"]:
                lines.append(
                    f"  - {axis['label']}: score `{fmt(axis.get('score'))}`, ekspozycja `{fmt(axis.get('exposure'))}`, confidence `{fmt(axis.get('confidence'))}`"
                )
                if axis.get("family_label"):
                    lines.append(f"    - rodzina: {axis['family_label']}")
                if axis.get("summary"):
                    lines.append(f"    - opis: {axis['summary']}")
                for example in axis.get("examples", [])[:2]:
                    lines.append(f"    - przyklad: {example}")
        lines.append("- Uzasadnienia:")
        for explanation in company["explanations"]:
            lines.append(f"  - {explanation['title']}: {explanation['detail']}")
        lines.append("")

    lines.append("## Notatka Metodologiczna")
    lines.append("")
    lines.append(
        "Raport zostal wygenerowany na podstawie danych pozyskanych w warstwie `scrapper/`, "
        "cech spolecznych policzonych w `analiza/` oraz aktualnej konfiguracji silnika selekcji w backendzie."
    )
    lines.append(
        "Wynik ma charakter eksperymentalnego preview portfela ETF-opodobnego i odzwierciedla aktualna dostepnosc metryk."
    )
    lines.append("")
    return "\n".join(lines)


def generate_portfolio_report(
    request: PortfolioPreviewRequest,
    output_name: str | None = None,
) -> PortfolioReportResponse:
    ensure_dir(REPORTS_DIR)

    preview = build_portfolio_preview(request)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_payload = _build_report_payload(request, preview, generated_at)
    markdown = build_markdown(report_payload)

    file_slug = slugify(output_name or request.profile_name)
    json_path = REPORTS_DIR / f"{file_slug}.json"
    markdown_path = REPORTS_DIR / f"{file_slug}.md"

    json_path.write_text(json.dumps(report_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    markdown_path.write_text(markdown, encoding="utf-8")

    return PortfolioReportResponse(
        profile_name=request.profile_name,
        generated_at=generated_at,
        file_slug=file_slug,
        markdown_file=str(markdown_path),
        json_file=str(json_path),
        markdown=markdown,
        preview=preview,
    )
