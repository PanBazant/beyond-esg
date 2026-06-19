from __future__ import annotations

import math

from ..schemas import AxisPreference, CompanyExplanation, ScoreBreakdown, ScoreWeights


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def normalize_weights(weights: ScoreWeights) -> ScoreWeights:
    total = (
        weights.base_quality
        + weights.esg_alignment
        + weights.category_match
        + weights.profitability_alignment
        + weights.technical_alignment
        + weights.market_cap_alignment
    )
    if total <= 0:
        return ScoreWeights()

    return ScoreWeights(
        base_quality=weights.base_quality / total,
        esg_alignment=weights.esg_alignment / total,
        category_match=weights.category_match / total,
        profitability_alignment=weights.profitability_alignment / total,
        technical_alignment=weights.technical_alignment / total,
        market_cap_alignment=weights.market_cap_alignment / total,
    )


def category_match(company: dict, selected_categories: list[str]) -> float:
    if not selected_categories:
        return 1.0
    return 1.0 if company.get("category") in set(selected_categories) else 0.0


def _align_normalized_score(normalized: float, mode: str) -> float:
    if mode == "prefer_low":
        return 1 - normalized
    if mode == "prefer_high":
        return normalized
    return 0.5


def _extract_company_axes(company: dict) -> list[dict]:
    axes: list[dict] = []
    raw_axes = company.get("custom_esg_axes")
    if isinstance(raw_axes, list):
        for index, axis in enumerate(raw_axes):
            label = axis.get("axis_label") or axis.get("label")
            if not label:
                continue
            axes.append(
                {
                    "axis_id": int(axis.get("axis_id", index)),
                    "label": str(label),
                    "score": _safe_float(axis.get("axis_score", axis.get("score")), None),
                    "exposure": _safe_float(axis.get("axis_exposure", axis.get("exposure")), 0.0),
                    "confidence": _safe_float(axis.get("axis_confidence", axis.get("confidence")), 0.0),
                }
            )
        return axes

    for index in range(1, 4):
        label = company.get(f"custom_esg_axis_{index}_label")
        if not label:
            continue
        axes.append(
            {
                "axis_id": index - 1,
                "label": str(label),
                "score": _safe_float(company.get(f"custom_esg_axis_{index}_score"), None),
                "exposure": _safe_float(company.get(f"custom_esg_axis_{index}_exposure"), 0.0),
                "confidence": _safe_float(company.get(f"custom_esg_axis_{index}_confidence"), 0.0),
            }
        )
    return axes


def perception_score(
    company: dict,
    axis_preferences: list[AxisPreference] | None,
    axis_info_map: dict[int, dict],
) -> float:
    """
    Compute a 0-1 perception score for a company.
    axis_info_map: {axis_id: {corpus_weight, average_sentiment}} from catalog.
    Formula: Σ(exposure × sentiment_factor × weight) / max_possible
    where weight = preference.importance * 2  (slider 0→1 maps to effective weight 0→2)
    and sentiment_factor = 0.5 + 0.5 * clamp(average_sentiment, -1, 1)
    """
    company_axes = _extract_company_axes(company)
    prefs = list(axis_preferences or [])
    if not company_axes or not prefs:
        return 0.5

    axis_by_id = {ax["axis_id"]: ax for ax in company_axes}

    total = 0.0
    max_possible = 0.0

    for pref in prefs:
        axis_company = axis_by_id.get(pref.axis_id)
        if axis_company is None:
            continue
        axis_catalog = axis_info_map.get(pref.axis_id, {})
        exposure = _clamp(_safe_float(axis_company.get("exposure"), 0.0))
        avg_sent = float(axis_catalog.get("average_sentiment") or 0.0)
        avg_sent = max(-1.0, min(1.0, avg_sent))
        sentiment_factor = 0.5 + 0.5 * avg_sent
        user_weight = _clamp(pref.importance) * 2.0  # importance 0-1 → effective weight 0-2
        if user_weight <= 0:
            continue
        total += exposure * sentiment_factor * user_weight
        max_possible += sentiment_factor * user_weight  # max exposure = 1

    if max_possible <= 0:
        return 0.5
    return round(_clamp(total / max_possible), 4)


def esg_alignment(company: dict, mode: str, axis_preferences: list[AxisPreference] | None = None) -> tuple[float, dict]:
    score = company.get("custom_esg_proxy_score")
    if score is None:
        base_alignment = 0.5 if mode == "neutral" else 0.0
    else:
        normalized = _clamp(_safe_float(score) / 100.0)
        base_alignment = _align_normalized_score(normalized, mode)

    active_preferences = [
        preference
        for preference in (axis_preferences or [])
        if preference.mode != "neutral" and preference.importance > 0
    ]
    company_axes = _extract_company_axes(company)
    if not active_preferences or not company_axes:
        return round(base_alignment, 4), {
            "base_alignment": round(base_alignment, 4),
            "axis_alignment": None,
            "axis_blend": 0.0,
            "active_axis_labels": [],
        }

    axis_by_id = {axis["axis_id"]: axis for axis in company_axes}
    weighted_alignment = 0.0
    total_weight = 0.0
    matched_preferences = 0
    active_axis_labels: list[str] = []

    for preference in active_preferences:
        axis = axis_by_id.get(preference.axis_id)
        if not axis:
            continue
        axis_score = axis.get("score")
        if axis_score is None:
            continue

        matched_preferences += 1
        axis_alignment = _align_normalized_score(_clamp(_safe_float(axis_score) / 100.0), preference.mode)
        confidence = _clamp(_safe_float(axis.get("confidence"), 0.0))
        exposure = _clamp(_safe_float(axis.get("exposure"), 0.0))
        signal_weight = preference.importance * (0.25 + (0.75 * confidence)) * (0.20 + (0.80 * exposure))
        if signal_weight <= 0:
            continue

        weighted_alignment += axis_alignment * signal_weight
        total_weight += signal_weight
        active_axis_labels.append(
            f"{axis['label']} [{preference.mode}, {preference.importance:.2f}]"
        )

    if total_weight <= 0:
        return round(base_alignment, 4), {
            "base_alignment": round(base_alignment, 4),
            "axis_alignment": None,
            "axis_blend": 0.0,
            "active_axis_labels": active_axis_labels,
        }

    axis_component = weighted_alignment / total_weight
    preference_strength = _clamp(sum(preference.importance for preference in active_preferences) / len(active_preferences))
    match_ratio = matched_preferences / len(active_preferences) if active_preferences else 0.0
    axis_blend = min(0.80, 0.20 + (0.60 * preference_strength * match_ratio))
    final_alignment = ((1 - axis_blend) * base_alignment) + (axis_blend * axis_component)

    return round(final_alignment, 4), {
        "base_alignment": round(base_alignment, 4),
        "axis_alignment": round(axis_component, 4),
        "axis_blend": round(axis_blend, 4),
        "active_axis_labels": active_axis_labels,
    }


def market_cap_alignment(company: dict, mode: str) -> float:
    market_cap = company.get("market_cap_numeric")
    if market_cap is None:
        return 0.5 if mode == "neutral" else 0.0

    normalized = _clamp(math.log10(max(_safe_float(market_cap, 1.0), 1.0)) / 12.0)
    if mode == "prefer_large":
        return normalized
    if mode == "prefer_small":
        return 1 - normalized
    return 0.5


def profitability_alignment(company: dict, mode: str) -> float:
    score = company.get("profitability_score")
    if score is None:
        return 0.5 if mode == "neutral" else 0.0

    normalized = _clamp(_safe_float(score) / 100.0)
    if mode == "prefer_high":
        return normalized
    if mode == "prefer_low":
        return 1 - normalized
    return 0.5


def technical_alignment(company: dict, mode: str) -> float:
    score = company.get("technical_score")
    if score is None:
        return 0.5 if mode == "neutral" else 0.0

    normalized = _clamp(_safe_float(score) / 100.0)
    if mode == "prefer_high":
        return normalized
    if mode == "prefer_low":
        return 1 - normalized
    return 0.5


def base_quality(company: dict) -> tuple[float, list[CompanyExplanation]]:
    rank = company.get("rank_in_category") or 999
    posts_count = _safe_float(company.get("posts_count"))
    market_cap = company.get("market_cap_numeric")

    rank_score = 1 / math.sqrt(rank)
    coverage = min(posts_count / 40, 1.0)

    if market_cap and market_cap > 0:
        scale_score = min(math.log10(market_cap) / 12, 1.0)
    else:
        scale_score = 0.0

    quality = (0.45 * rank_score) + (0.35 * coverage) + (0.20 * scale_score)
    explanations = [
        CompanyExplanation(
            title="Pozycja w kategorii",
            detail=f"Spolka ma pozycje {rank} w swojej kategorii, co wzmacnia komponent bazowej jakosci.",
        ),
        CompanyExplanation(
            title="Pokrycie danymi spolecznosciowymi",
            detail=f"Dla spolki zebrano {posts_count} postow w najnowszym snapshotcie.",
        ),
    ]

    if market_cap:
        explanations.append(
            CompanyExplanation(
                title="Skala rynkowa",
                detail=f"Zidentyfikowana kapitalizacja rynkowa to {company.get('market_cap_label')}.",
            )
        )

    return round(quality, 4), explanations


def score_company(
    company: dict,
    *,
    selected_categories: list[str],
    custom_esg_mode: str,
    axis_preferences: list[AxisPreference] | None,
    profitability_mode: str,
    technical_mode: str,
    market_cap_mode: str,
    weights: ScoreWeights,
) -> tuple[float, ScoreBreakdown, list[CompanyExplanation]]:
    normalized_weights = normalize_weights(weights)
    quality, explanations = base_quality(company)
    category = category_match(company, selected_categories)
    esg, esg_meta = esg_alignment(company, custom_esg_mode, axis_preferences)
    profitability = profitability_alignment(company, profitability_mode)
    technical = technical_alignment(company, technical_mode)
    market = market_cap_alignment(company, market_cap_mode)

    selection_score = round(
        (normalized_weights.base_quality * quality)
        + (normalized_weights.esg_alignment * esg)
        + (normalized_weights.category_match * category)
        + (normalized_weights.profitability_alignment * profitability)
        + (normalized_weights.technical_alignment * technical)
        + (normalized_weights.market_cap_alignment * market),
        4,
    )

    explanations.append(
        CompanyExplanation(
            title="Dopasowanie wartości (aksjologia)",
            detail=(
                f"Dopasowanie do wybranego profilu wartości wynosi {esg:.2f}, "
                f"przy surowym proxy-score {company.get('custom_esg_proxy_score')} "
                f"i bazowym dopasowaniu {esg_meta['base_alignment']:.2f}."
            ),
        )
    )
    if company.get("custom_esg_metric_version"):
        explanations.append(
            CompanyExplanation(
                title="Profil wartości z komentarzy",
                detail=(
                    f"Spolka korzysta z metryki {company.get('custom_esg_metric_version')}, "
                    "zbudowanej z wielu organicznych osi wartosci odkrytych w komentarzach inwestorow, "
                    "pogrupowanych w rodziny wartosci — oddolnie z dyskursu, nie z gotowych norm ESG."
                ),
            )
        )
    if esg_meta.get("axis_alignment") is not None:
        axis_labels = ", ".join(esg_meta.get("active_axis_labels", [])[:3]) or "brak"
        explanations.append(
            CompanyExplanation(
                title="Sterowanie osiami wartości",
                detail=(
                    f"Aktywne preferencje osiowe zmienily dopasowanie wartości do {esg_meta['axis_alignment']:.2f} "
                    f"z blendingiem {esg_meta['axis_blend']:.2f}. Osie: {axis_labels}."
                ),
            )
        )
    explanations.append(
        CompanyExplanation(
            title="Dopasowanie kategorii",
            detail=f"Poziom dopasowania do wybranych kategorii wynosi {category:.2f}.",
        )
    )
    explanations.append(
        CompanyExplanation(
            title="Rentownosc",
            detail=(
                "Alignment do preferencji rentownosci wynosi "
                f"{profitability:.2f}, przy profitability score {company.get('profitability_score')}."
            ),
        )
    )
    explanations.append(
        CompanyExplanation(
            title="Technikalia",
            detail=(
                "Alignment do preferencji technicznych wynosi "
                f"{technical:.2f}, przy technical score {company.get('technical_score')}."
            ),
        )
    )
    explanations.append(
        CompanyExplanation(
            title="Wagi profilu",
            detail=(
                "Finalny score sklada sie z wag: "
                f"jakosc={normalized_weights.base_quality:.2f}, "
                f"wartosci={normalized_weights.esg_alignment:.2f}, "
                f"kategoria={normalized_weights.category_match:.2f}, "
                f"rentownosc={normalized_weights.profitability_alignment:.2f}, "
                f"technika={normalized_weights.technical_alignment:.2f}, "
                f"kapitalizacja={normalized_weights.market_cap_alignment:.2f}."
            ),
        )
    )

    breakdown = ScoreBreakdown(
        base_quality=round(quality, 4),
        esg_alignment=round(esg, 4),
        category_match=round(category, 4),
        profitability_alignment=round(profitability, 4),
        technical_alignment=round(technical, 4),
        market_cap_alignment=round(market, 4),
    )
    return selection_score, breakdown, explanations


def build_holding_weights(companies: list[dict], weighting_mode: str, max_holding_weight: float) -> list[float]:
    if not companies:
        return []

    total = len(companies)
    if weighting_mode == "equal":
        return [round(1 / total, 4) for _ in companies]

    if max_holding_weight * total < 1:
        return [round(1 / total, 4) for _ in companies]

    scores = [max(_safe_float(company.get("selection_score")), 0.0001) for company in companies]
    score_total = sum(scores)
    if score_total <= 0:
        return [round(1 / total, 4) for _ in companies]

    weights = [score / score_total for score in scores]
    capped = [False] * total

    while True:
        overflow = [index for index, weight in enumerate(weights) if weight > max_holding_weight + 1e-9 and not capped[index]]
        if not overflow:
            break

        for index in overflow:
            weights[index] = max_holding_weight
            capped[index] = True

        remaining_indices = [index for index in range(total) if not capped[index]]
        remaining_weight = max(0.0, 1.0 - sum(weights[index] for index in range(total) if capped[index]))
        if not remaining_indices:
            break

        remaining_score_total = sum(scores[index] for index in remaining_indices)
        if remaining_score_total <= 0:
            split_weight = remaining_weight / len(remaining_indices)
            for index in remaining_indices:
                weights[index] = split_weight
            break

        for index in remaining_indices:
            weights[index] = remaining_weight * (scores[index] / remaining_score_total)

    rounded = [round(weight, 4) for weight in weights]
    difference = round(1.0 - sum(rounded), 4)
    if rounded and difference != 0:
        rounded[0] = round(rounded[0] + difference, 4)
    return rounded
