from __future__ import annotations

from ..schemas import ProfileCatalogResponse, ProfilePreset, ScoreWeights


PRESETS = [
    ProfilePreset(
        id="anti_esg_contrarian",
        name="Contrarian Anti-ESG",
        description="Profil dla uzytkownika, ktory preferuje spolki bardziej kontrowersyjne lub mniej zgodne z klasycznym ESG, ale nadal chce zachowac sensowna jakosc i skale.",
        custom_esg_mode="prefer_low",
        profitability_mode="neutral",
        technical_mode="neutral",
        market_cap_mode="prefer_large",
        weighting_mode="score_weighted",
        score_weights=ScoreWeights(
            base_quality=0.25,
            esg_alignment=0.30,
            category_match=0.15,
            profitability_alignment=0.15,
            technical_alignment=0.05,
            market_cap_alignment=0.10,
        ),
    ),
    ProfilePreset(
        id="balanced_signal",
        name="Balanced Signal",
        description="Zbalansowany profil do eksploracji rynku, bez silnej normy aksjologicznej i z rownym naciskiem na jakosc oraz sygnal spolecznosciowy.",
        custom_esg_mode="neutral",
        profitability_mode="neutral",
        technical_mode="prefer_high",
        market_cap_mode="neutral",
        weighting_mode="score_weighted",
        score_weights=ScoreWeights(
            base_quality=0.25,
            esg_alignment=0.20,
            category_match=0.20,
            profitability_alignment=0.20,
            technical_alignment=0.15,
            market_cap_alignment=0.15,
        ),
    ),
    ProfilePreset(
        id="classic_esg_defensive",
        name="Classic ESG Defensive",
        description="Profil preferujacy wieksza zgodnosc z klasycznym ESG oraz duze, stabilniejsze spolki.",
        custom_esg_mode="prefer_high",
        profitability_mode="prefer_high",
        technical_mode="prefer_high",
        market_cap_mode="prefer_large",
        weighting_mode="equal",
        score_weights=ScoreWeights(
            base_quality=0.20,
            esg_alignment=0.30,
            category_match=0.15,
            profitability_alignment=0.20,
            technical_alignment=0.15,
            market_cap_alignment=0.15,
        ),
    ),
]


def build_profile_catalog() -> ProfileCatalogResponse:
    return ProfileCatalogResponse(profiles=PRESETS)
