from __future__ import annotations

import re
from collections import Counter
from typing import Literal


InstrumentUniverseClass = Literal[
    "common_equity",
    "reit",
    "fund_etf_trust",
    "ambiguous",
    "crypto_coin",
]

INSTRUMENT_UNIVERSE_ORDER: list[InstrumentUniverseClass] = [
    "common_equity",
    "reit",
    "fund_etf_trust",
    "ambiguous",
    "crypto_coin",
]

INSTRUMENT_UNIVERSE_LABELS: dict[InstrumentUniverseClass, str] = {
    "common_equity": "Akcje",
    "reit": "REIT-y",
    "fund_etf_trust": "Fundusze / ETF-y / trusty",
    "ambiguous": "Niejednoznaczne",
    "crypto_coin": "Krypto-coiny",
}

INSTRUMENT_UNIVERSE_DESCRIPTIONS: dict[InstrumentUniverseClass, str] = {
    "common_equity": "Zwykle spolki publiczne; REIT-y sa dolaczane do tego samego koszyka akcji.",
    "reit": "Real Estate Investment Trusts oraz spolki bardzo mocno wygladajace na REIT-y.",
    "fund_etf_trust": "ETF-y, fundusze, trusty i podobne instrumenty notowane jak papiery.",
    "ambiguous": "Rekordy, dla ktorych metadane sa sprzeczne albo zbyt slabe, zeby klasyfikowac je agresywnie.",
    "crypto_coin": "Instrumenty krypto ze sciezki /coins/ na StockTwits.",
}

DEFAULT_ALLOWED_INSTRUMENT_UNIVERSES: list[InstrumentUniverseClass] = [
    "common_equity",
]

PORTFOLIO_EXCLUDED_UNIVERSES: set[InstrumentUniverseClass] = {"fund_etf_trust", "crypto_coin"}


def expand_allowed_instrument_universes(
    universes: list[InstrumentUniverseClass] | set[InstrumentUniverseClass],
) -> set[InstrumentUniverseClass]:
    expanded = set(universes)
    if "common_equity" in expanded:
        expanded.add("reit")
    return expanded

FUND_KEYWORD_PATTERN = re.compile(
    r"\b(etf|etn|fund|funds|ucits|index fund|exchange traded fund|mutual fund|closed[- ]end|unit trust)\b",
    re.IGNORECASE,
)
FUND_FAMILY_PATTERN = re.compile(
    r"\b(ishares|vaneck|wisdomtree|proshares|direxion|invesco|spdr|first trust|listed funds trust|grayscale|global x|vistashares|rex )",
    re.IGNORECASE,
)
REIT_INDUSTRY_PATTERN = re.compile(r"real estate investment trust", re.IGNORECASE)
REIT_CATEGORY_PATTERN = re.compile(r"\breits?\b", re.IGNORECASE)
REIT_NAME_PATTERN = re.compile(
    r"\b(reit|realty|properties|property trust|mortgage|commercial real estate|real estate)\b",
    re.IGNORECASE,
)
SPAC_PATTERN = re.compile(r"\b(acquisition corp|acquisition corporation|acquisition holdings|spac)\b", re.IGNORECASE)


def _clean(value: object) -> str:
    return " ".join(str(value or "").split()).strip()


def classify_instrument(
    *,
    company_name: object = None,
    industry: object = None,
    category: object = None,
    symbol_href: object = None,
    company_href: object = None,
) -> tuple[InstrumentUniverseClass, str]:
    company_name_text = _clean(company_name)
    industry_text = _clean(industry)
    category_text = _clean(category)
    symbol_href_text = _clean(symbol_href)
    company_href_text = _clean(company_href)

    name_lower = company_name_text.lower()
    industry_lower = industry_text.lower()
    category_lower = category_text.lower()
    href_text = f"{symbol_href_text} {company_href_text}".lower()

    if "/coins/" in href_text:
        return "crypto_coin", "Link wskazuje na sciezke /coins/ w StockTwits."

    if REIT_INDUSTRY_PATTERN.search(industry_text):
        return "reit", "Branza wskazuje bezposrednio na Real Estate Investment Trust."

    category_looks_like_reit = bool(REIT_CATEGORY_PATTERN.search(category_text))
    name_looks_like_reit = bool(REIT_NAME_PATTERN.search(company_name_text))

    if category_looks_like_reit and name_looks_like_reit:
        return "reit", "Kategoria i nazwa spolki wygladaja na REIT."

    industry_looks_like_fund = "investment trusts or mutual funds" in industry_lower
    name_looks_like_fund = bool(FUND_KEYWORD_PATTERN.search(company_name_text) or FUND_FAMILY_PATTERN.search(company_name_text))

    if industry_looks_like_fund and name_looks_like_fund:
        return "fund_etf_trust", "Branza i nazwa wskazuja na fundusz, ETF albo trust."

    if industry_looks_like_fund and not name_looks_like_fund:
        return "ambiguous", "Branza sugeruje fundusz lub trust, ale nazwa spolki nie daje mocnego potwierdzenia."

    if name_looks_like_fund:
        return "fund_etf_trust", "Nazwa spolki zawiera silne sygnaly ETF/fund/trust."

    if category_looks_like_reit and not name_looks_like_reit:
        return "ambiguous", "Kategoria sugeruje REIT, ale nazwa i branza nie potwierdzaja tego dostatecznie mocno."

    if SPAC_PATTERN.search(company_name_text):
        return "ambiguous", "Spolka wyglada na wehikul akwizycyjny lub SPAC."

    if not industry_text or industry_text == "-" or industry_lower == "unknown":
        return "ambiguous", "Brak wiarygodnej informacji o typie instrumentu w metadanych."

    return "common_equity", "Metadane nie sugeruja funduszu, REIT-u ani krypto-coina."


def build_instrument_universe_catalog(companies: list[dict]) -> list[dict]:
    counts: Counter[str] = Counter()
    for company in companies:
        instrument_universe = str(company.get("instrument_universe") or "ambiguous")
        counts[instrument_universe] += 1

    catalog = []
    for instrument_universe in INSTRUMENT_UNIVERSE_ORDER:
        if instrument_universe == "reit":
            continue
        if instrument_universe in PORTFOLIO_EXCLUDED_UNIVERSES:
            continue
        companies_count = counts.get(instrument_universe, 0)
        if instrument_universe == "common_equity":
            companies_count += counts.get("reit", 0)
        catalog.append(
            {
                "id": instrument_universe,
                "label": INSTRUMENT_UNIVERSE_LABELS[instrument_universe],
                "description": INSTRUMENT_UNIVERSE_DESCRIPTIONS[instrument_universe],
                "companies_count": companies_count,
                "default_selected": instrument_universe in DEFAULT_ALLOWED_INSTRUMENT_UNIVERSES,
            }
        )
    return catalog
