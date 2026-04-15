from __future__ import annotations

from collections import Counter, defaultdict

from ..schemas import (
    BenchmarkPortfolio,
    CategoryAllocation,
    CompanyPreview,
    PortfolioComparison,
    PortfolioComparisonMetrics,
    CustomEsgAxisPreview,
    CustomEsgFamilyPreview,
    MetricAvailability,
    PortfolioHolding,
    PortfolioPreviewRequest,
    PortfolioPreviewResponse,
    PortfolioSummary,
    ScoreWeights,
)
from .datasets import load_comment_esg_axes_catalog, load_company_records, metric_availability
from .instrument_universe import PORTFOLIO_EXCLUDED_UNIVERSES, expand_allowed_instrument_universes
from .scoring import build_holding_weights, normalize_weights, score_company


def _build_warnings(payload: PortfolioPreviewRequest, metrics: dict[str, bool]) -> list[str]:
    warnings: list[str] = []
    allowed_universes = set(payload.allowed_instrument_universes)

    if payload.custom_esg_mode != "neutral" and not metrics["custom_esg"]:
        warnings.append(
            "Custom ESG orientation jest juz czescia modelu domenowego, ale jeszcze nie zostala podpieta do finalnych metryk spolek."
        )

    if payload.profitability_mode != "neutral" and not metrics["profitability"]:
        warnings.append(
            "Warstwa fundamentalna jest juz podpieta architektonicznie, ale w master datasecie nie ma jeszcze zaladowanych metryk rentownosci."
        )

    if payload.technical_mode != "neutral" and not metrics["technicals"]:
        warnings.append(
            "Warstwa techniczna jest juz podpieta architektonicznie, ale w master datasecie nie ma jeszcze zaladowanych metryk technicznych."
        )

    warnings.append(
        "Fundusze, ETF-y i trusty sa trwale wyciete z universe wejsciowego. REIT-y sa wlaczone do ogolnego koszyka akcji."
    )
    if "ambiguous" in allowed_universes:
        warnings.append(
            "W universe zostawiono tez rekordy niejednoznaczne, zeby nie wyciac agresywnie spolek z mylacymi metadanymi."
        )

    return warnings


def _safe_float(value: object, default: float | None = 0.0) -> float | None:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _append_company(selected: list[CompanyPreview], company: CompanyPreview, selected_symbols: set[str], category_counts: Counter) -> None:
    selected.append(company)
    selected_symbols.add(company.symbol)
    category_counts[company.category] += 1


def _extract_custom_esg_axes(company: dict, axis_lookup: dict[int, dict]) -> list[CustomEsgAxisPreview]:
    raw_axes = company.get("custom_esg_axes")
    if isinstance(raw_axes, list) and raw_axes:
        axes: list[CustomEsgAxisPreview] = []
        for axis in raw_axes:
            axis_id = int(axis.get("axis_id", len(axes)))
            axis_definition = axis_lookup.get(axis_id, {})
            axes.append(
                CustomEsgAxisPreview(
                    axis_id=axis_id,
                    label=str(axis_definition.get("label") or axis.get("axis_label") or axis.get("label") or f"Axis {axis_id + 1}"),
                    family_label=axis_definition.get("family_label"),
                    summary=axis_definition.get("summary") or axis.get("axis_summary"),
                    keywords=list(axis_definition.get("keywords") or axis.get("axis_keywords") or []),
                    examples=list(axis_definition.get("examples") or axis.get("axis_examples") or []),
                    score=_safe_float(axis.get("axis_score", axis.get("score")), None),
                    exposure=_safe_float(axis.get("axis_exposure", axis.get("exposure")), None),
                    confidence=_safe_float(axis.get("axis_confidence", axis.get("confidence")), None),
                )
            )
        return axes

    axes: list[CustomEsgAxisPreview] = []
    for index in range(1, 4):
        label = company.get(f"custom_esg_axis_{index}_label")
        if not label:
            continue
        axis_id = index - 1
        axis_definition = axis_lookup.get(axis_id, {})
        axes.append(
            CustomEsgAxisPreview(
                axis_id=axis_id,
                label=str(axis_definition.get("label") or label),
                family_label=axis_definition.get("family_label"),
                summary=axis_definition.get("summary"),
                keywords=list(axis_definition.get("keywords", [])),
                examples=list(axis_definition.get("examples", [])),
                score=_safe_float(company.get(f"custom_esg_axis_{index}_score"), None),
                exposure=_safe_float(company.get(f"custom_esg_axis_{index}_exposure"), None),
                confidence=_safe_float(company.get(f"custom_esg_axis_{index}_confidence"), None),
            )
        )
    return axes


def _extract_custom_esg_families(company: dict) -> list[CustomEsgFamilyPreview]:
    raw_families = company.get("custom_esg_families")
    if not isinstance(raw_families, list) or not raw_families:
        return []

    families: list[CustomEsgFamilyPreview] = []
    for family in raw_families:
        family_id = str(family.get("family_id") or "").strip()
        if not family_id:
            continue
        families.append(
            CustomEsgFamilyPreview(
                family_id=family_id,
                label=str(family.get("family_label") or family_id),
                summary=family.get("family_summary"),
                dominant_axis_code=family.get("dominant_axis_code"),
                dominant_axis_label=family.get("dominant_axis_label"),
                keywords=list(family.get("family_keywords") or []),
                examples=list(family.get("family_examples") or []),
                score=_safe_float(family.get("family_score"), None),
                exposure=_safe_float(family.get("family_exposure"), None),
                confidence=_safe_float(family.get("family_confidence"), None),
                esg_relevance=_safe_float(family.get("family_esg_relevance"), None),
            )
        )

    families.sort(
        key=lambda item: (
            float(item.esg_relevance or 0.0),
            float(item.exposure or 0.0),
            float(item.confidence or 0.0),
        ),
        reverse=True,
    )
    return families


def _select_diversified_companies(scored: list[CompanyPreview], payload: PortfolioPreviewRequest) -> tuple[list[CompanyPreview], list[str]]:
    warnings: list[str] = []
    selected: list[CompanyPreview] = []
    selected_symbols: set[str] = set()
    category_counts: Counter = Counter()

    target_distinct = min(payload.min_distinct_categories, payload.portfolio_size)
    available_categories = {company.category for company in scored}
    if target_distinct > len(available_categories):
        warnings.append(
            f"Zadano minimum {target_distinct} kategorii, ale po filtracji dostepnych jest tylko {len(available_categories)}."
        )
        target_distinct = len(available_categories)

    if target_distinct > 1:
        seeded_categories: set[str] = set()
        for company in scored:
            if len(selected) >= payload.portfolio_size or len(seeded_categories) >= target_distinct:
                break
            if company.symbol in selected_symbols or company.category in seeded_categories:
                continue
            if payload.max_companies_per_category and category_counts[company.category] >= payload.max_companies_per_category:
                continue
            _append_company(selected, company, selected_symbols, category_counts)
            seeded_categories.add(company.category)

        if len(seeded_categories) < target_distinct:
            warnings.append(
                f"Nie udalo sie zaszczepic {target_distinct} roznych kategorii w pierwszym kroku; osiagnieto {len(seeded_categories)}."
            )

    for company in scored:
        if len(selected) >= payload.portfolio_size:
            break
        if company.symbol in selected_symbols:
            continue
        if payload.max_companies_per_category and category_counts[company.category] >= payload.max_companies_per_category:
            continue
        _append_company(selected, company, selected_symbols, category_counts)

    if len(selected) < payload.portfolio_size:
        if payload.strict_category_limit:
            warnings.append(
                "Zastosowano scisly limit na liczbe spolek w kategorii, dlatego portfel ma mniej pozycji niz zadano."
            )
            return selected, warnings

        warnings.append(
            "Aby domknac liczbe pozycji w portfelu, poluzowano limit liczby spolek na kategorie."
        )
        for company in scored:
            if len(selected) >= payload.portfolio_size:
                break
            if company.symbol in selected_symbols:
                continue
            _append_company(selected, company, selected_symbols, category_counts)

    return selected, warnings


def _weighted_average(selected: list[CompanyPreview], holdings_by_symbol: dict[str, PortfolioHolding], field_name: str) -> float | None:
    numerator = 0.0
    denominator = 0.0

    for company in selected:
        value = getattr(company, field_name)
        holding = holdings_by_symbol.get(company.symbol)
        if value is None or holding is None:
            continue
        numerator += float(value) * holding.weight
        denominator += holding.weight

    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def _build_summary(selected: list[CompanyPreview], holdings: list[PortfolioHolding]) -> tuple[PortfolioSummary, list[CategoryAllocation]]:
    if not selected or not holdings:
        return (
            PortfolioSummary(
                selected_companies=0,
                distinct_categories=0,
                concentration_hhi=0.0,
                max_holding_weight=0.0,
            ),
            [],
        )

    holdings_by_symbol = {holding.symbol: holding for holding in holdings}
    category_totals: dict[str, dict] = defaultdict(lambda: {"weight": 0.0, "count": 0, "score_sum": 0.0})

    for company in selected:
        holding = holdings_by_symbol[company.symbol]
        bucket = category_totals[company.category]
        bucket["weight"] += holding.weight
        bucket["count"] += 1
        bucket["score_sum"] += company.selection_score

    allocations = [
        CategoryAllocation(
            category=category,
            holdings_count=payload["count"],
            total_weight=round(payload["weight"], 4),
            average_selection_score=round(payload["score_sum"] / payload["count"], 4),
        )
        for category, payload in category_totals.items()
    ]
    allocations.sort(key=lambda item: item.total_weight, reverse=True)

    concentration_hhi = round(sum(holding.weight**2 for holding in holdings), 4)
    max_weight = round(max(holding.weight for holding in holdings), 4)
    top_category = allocations[0].category if allocations else None

    summary = PortfolioSummary(
        selected_companies=len(selected),
        distinct_categories=len(category_totals),
        average_custom_esg=_weighted_average(selected, holdings_by_symbol, "custom_esg_proxy_score"),
        average_profitability=_weighted_average(selected, holdings_by_symbol, "profitability_score"),
        average_technical=_weighted_average(selected, holdings_by_symbol, "technical_score"),
        average_sentiment=_weighted_average(selected, holdings_by_symbol, "avg_sentiment"),
        average_posts_count=_weighted_average(selected, holdings_by_symbol, "posts_count"),
        concentration_hhi=concentration_hhi,
        max_holding_weight=max_weight,
        top_category=top_category,
    )
    return summary, allocations


def _build_benchmark_payload(payload: PortfolioPreviewRequest) -> PortfolioPreviewRequest:
    return PortfolioPreviewRequest(
        **{
            **payload.model_dump(),
            "profile_name": f"{payload.profile_name}-esg-reference",
            "custom_esg_mode": "prefer_high",
            "axis_preferences": [],
            "score_weights": {
                "base_quality": 0.20,
                "esg_alignment": 0.45,
                "category_match": 0.15,
                "profitability_alignment": 0.10,
                "technical_alignment": 0.05,
                "market_cap_alignment": 0.05,
            },
        }
    )


def _safe_delta(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return round(left - right, 4)


def _build_comparison(
    base_summary: PortfolioSummary,
    base_holdings: list[PortfolioHolding],
    benchmark_summary: PortfolioSummary,
    benchmark_allocations: list[CategoryAllocation],
    benchmark_holdings: list[PortfolioHolding],
) -> PortfolioComparison:
    base_symbols = {holding.symbol for holding in base_holdings}
    benchmark_symbols = {holding.symbol for holding in benchmark_holdings}
    overlap_count = len(base_symbols.intersection(benchmark_symbols))
    overlap_ratio = round(overlap_count / len(base_holdings), 4) if base_holdings else 0.0

    benchmark = BenchmarkPortfolio(
        label="ESG-like reference portfolio",
        custom_esg_mode="prefer_high",
        summary=benchmark_summary,
        category_allocations=benchmark_allocations,
        holdings=benchmark_holdings,
    )
    metrics = PortfolioComparisonMetrics(
        overlap_count=overlap_count,
        overlap_ratio=overlap_ratio,
        custom_esg_delta=_safe_delta(base_summary.average_custom_esg, benchmark_summary.average_custom_esg),
        profitability_delta=_safe_delta(base_summary.average_profitability, benchmark_summary.average_profitability),
        technical_delta=_safe_delta(base_summary.average_technical, benchmark_summary.average_technical),
        sentiment_delta=_safe_delta(base_summary.average_sentiment, benchmark_summary.average_sentiment),
        distinct_categories_delta=base_summary.distinct_categories - benchmark_summary.distinct_categories,
    )
    return PortfolioComparison(benchmark=benchmark, metrics=metrics)


def _run_preview(payload: PortfolioPreviewRequest) -> tuple[int, list[str], ScoreWeights, list[CompanyPreview], list[PortfolioHolding], PortfolioSummary, list[CategoryAllocation]]:
    companies = load_company_records()
    metrics = metric_availability(companies)
    warnings = _build_warnings(payload, metrics)
    normalized_weights = normalize_weights(payload.score_weights)
    axis_lookup = {axis["axis_id"]: axis for axis in load_comment_esg_axes_catalog()}

    if payload.categories:
        allowed_categories = set(payload.categories)
        companies = [company for company in companies if company.get("category") in allowed_categories]

    companies = [
        company
        for company in companies
        if str(company.get("instrument_universe") or "ambiguous") not in PORTFOLIO_EXCLUDED_UNIVERSES
    ]

    allowed_instrument_universes = expand_allowed_instrument_universes(set(payload.allowed_instrument_universes))
    if not allowed_instrument_universes:
        warnings.append("Nie wybrano zadnej klasy instrumentu, wiec po filtracji nie ma kandydatow do portfela.")
        companies = []
    else:
        companies = [
            company for company in companies if str(company.get("instrument_universe") or "ambiguous") in allowed_instrument_universes
        ]

    companies = [company for company in companies if (company.get("posts_count") or 0) >= payload.min_posts]

    scored: list[CompanyPreview] = []
    for company in companies:
        selection_score, breakdown, explanations = score_company(
            company,
            selected_categories=payload.categories,
            custom_esg_mode=payload.custom_esg_mode,
            axis_preferences=payload.axis_preferences,
            profitability_mode=payload.profitability_mode,
            technical_mode=payload.technical_mode,
            market_cap_mode=payload.market_cap_mode,
            weights=normalized_weights,
        )

        scored.append(
            CompanyPreview(
                symbol=company["symbol"],
                company_name=company["company_name"],
                category=company["category"],
                industry=company.get("industry"),
                instrument_universe=str(company.get("instrument_universe") or "ambiguous"),
                instrument_universe_label=str(company.get("instrument_universe_label") or "Niejednoznaczne"),
                instrument_universe_reason=company.get("instrument_universe_reason"),
                posts_count=int(_safe_float(company["posts_count"])),
                market_cap_label=company.get("market_cap_label"),
                market_cap_numeric=_safe_float(company.get("market_cap_numeric"), None),
                rank_in_category=company.get("rank_in_category"),
                custom_esg_proxy_score=_safe_float(company.get("custom_esg_proxy_score"), None),
                custom_esg_confidence=_safe_float(company.get("custom_esg_confidence"), None),
                custom_esg_metric_version=company.get("custom_esg_metric_version"),
                real_esg_total_score=_safe_float(company.get("real_esg_total_score"), None),
                real_esg_environment_score=_safe_float(company.get("real_esg_environment_score"), None),
                real_esg_social_score=_safe_float(company.get("real_esg_social_score"), None),
                real_esg_governance_score=_safe_float(company.get("real_esg_governance_score"), None),
                real_esg_source=company.get("real_esg_source"),
                custom_esg_axes=_extract_custom_esg_axes(company, axis_lookup),
                custom_esg_families=_extract_custom_esg_families(company),
                profitability_score=_safe_float(company.get("profitability_score"), None),
                technical_score=_safe_float(company.get("technical_score"), None),
                avg_sentiment=_safe_float(company.get("avg_sentiment"), None),
                coverage_score=_safe_float(company.get("coverage_score"), None),
                selection_score=selection_score,
                score_breakdown=breakdown,
                explanations=explanations,
            )
        )

    scored.sort(key=lambda item: item.selection_score, reverse=True)
    selected, diversification_warnings = _select_diversified_companies(scored, payload)
    warnings.extend(diversification_warnings)

    holdings: list[PortfolioHolding] = []
    if selected:
        holding_weights = build_holding_weights(
            [company.model_dump() for company in selected],
            payload.weighting_mode,
            payload.max_holding_weight,
        )
        for company, weight in zip(selected, holding_weights):
            holdings.append(
                PortfolioHolding(
                    symbol=company.symbol,
                    company_name=company.company_name,
                    weight=weight,
                    selection_score=company.selection_score,
                    category=company.category,
                    instrument_universe=company.instrument_universe,
                    instrument_universe_label=company.instrument_universe_label,
                )
            )

    summary, category_allocations = _build_summary(selected, holdings)
    return len(scored), warnings, normalized_weights, selected, holdings, summary, category_allocations


def build_portfolio_preview(payload: PortfolioPreviewRequest) -> PortfolioPreviewResponse:
    companies = load_company_records()
    metrics = metric_availability(companies)
    matched_companies, warnings, normalized_weights, selected, holdings, summary, category_allocations = _run_preview(payload)

    comparison = None
    if metrics["custom_esg"]:
        benchmark_payload = _build_benchmark_payload(payload)
        (
            _benchmark_matched,
            _benchmark_warnings,
            _benchmark_weights,
            _benchmark_selected,
            benchmark_holdings,
            benchmark_summary,
            benchmark_allocations,
        ) = _run_preview(benchmark_payload)
        comparison = _build_comparison(
            summary,
            holdings,
            benchmark_summary,
            benchmark_allocations,
            benchmark_holdings,
        )

    return PortfolioPreviewResponse(
        profile_name=payload.profile_name,
        matched_companies=matched_companies,
        metrics=MetricAvailability(**metrics),
        score_weights=normalized_weights,
        weighting_mode=payload.weighting_mode,
        warnings=warnings,
        summary=summary,
        category_allocations=category_allocations,
        companies=selected,
        holdings=holdings,
        comparison=comparison,
    )
