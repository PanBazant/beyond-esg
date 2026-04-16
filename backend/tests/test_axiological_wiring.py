import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas import CompanyPreview, MetricAvailability, PortfolioSummary
from app.services.portfolio import _parse_axiological_frames
from app.services.datasets import metric_availability


def test_metric_availability_has_axiological_field():
    m = MetricAvailability()
    assert hasattr(m, "axiological")
    assert m.axiological is False  # default


def test_company_preview_has_axiological_fields():
    company = CompanyPreview(
        symbol="AAPL",
        company_name="Apple",
        category="Technology",
        instrument_universe="common_equity",
        instrument_universe_label="Common Equity",
        posts_count=100,
        selection_score=0.5,
        score_breakdown={
            "base_quality": 0.1,
            "esg_alignment": 0.1,
            "category_match": 0.1,
            "profitability_alignment": 0.1,
            "technical_alignment": 0.1,
            "market_cap_alignment": 0.1,
        },
        explanations=[],
    )
    assert company.axiological_coverage is None
    assert company.axiological_confidence is None
    assert company.axiological_inter_method_agreement is None
    assert company.axiological_frames == []
    assert company.axiological_has_signal is False
    assert company.axiological_profile_null is True


def test_portfolio_summary_has_average_axiological_coverage():
    summary = PortfolioSummary(
        selected_companies=0,
        distinct_categories=0,
        concentration_hhi=0.0,
        max_holding_weight=0.0,
    )
    assert hasattr(summary, "average_axiological_coverage")
    assert summary.average_axiological_coverage is None


def test_parse_frames_from_json_string():
    raw = '[{"label": "governance"}, {"label": "ethics"}]'
    result = _parse_axiological_frames(raw)
    assert result == [{"label": "governance"}, {"label": "ethics"}]


def test_parse_frames_from_list_passthrough():
    raw = [{"label": "governance"}]
    result = _parse_axiological_frames(raw)
    assert result == [{"label": "governance"}]


def test_parse_frames_none_returns_empty():
    assert _parse_axiological_frames(None) == []


def test_parse_frames_empty_string_returns_empty():
    assert _parse_axiological_frames("") == []


def test_parse_frames_invalid_json_returns_empty():
    assert _parse_axiological_frames("not-json") == []


def test_parse_frames_json_dict_returns_empty():
    # Valid JSON but not a list — should return []
    assert _parse_axiological_frames('{"label": "governance"}') == []


def test_metric_availability_detects_axiological():
    assert metric_availability([{"axiological_coverage": 0.8}])["axiological"] is True
    assert metric_availability([{"axiological_coverage": None}])["axiological"] is False
    assert metric_availability([{}])["axiological"] is False
