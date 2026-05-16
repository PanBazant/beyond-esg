import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_profiling_lib import validate_llm_result


def test_validate_preserves_valid_sentiment():
    result = {
        "frames": [{"label": "regulatory scrutiny", "evidence": "SEC", "exposure": "high", "sentiment": "negative"}],
        "axiological_coverage": "present",
        "notes": None,
    }
    validated = validate_llm_result(result)
    assert validated["frames"][0]["sentiment"] == "negative"


def test_validate_defaults_missing_sentiment_to_neutral():
    result = {
        "frames": [{"label": "innovation narrative", "evidence": "tech leader", "exposure": "medium"}],
        "axiological_coverage": "marginal",
        "notes": None,
    }
    validated = validate_llm_result(result)
    assert validated["frames"][0]["sentiment"] == "neutral"


def test_validate_rejects_invalid_sentiment():
    result = {
        "frames": [{"label": "foo", "evidence": "bar", "exposure": "low", "sentiment": "very_bad"}],
        "axiological_coverage": "present",
        "notes": None,
    }
    validated = validate_llm_result(result)
    assert validated["frames"][0]["sentiment"] == "neutral"


def test_validate_all_valid_sentiment_values():
    for sentiment in ("positive", "negative", "mixed", "neutral"):
        result = {
            "frames": [{"label": "x", "evidence": "y", "exposure": "low", "sentiment": sentiment}],
            "axiological_coverage": "marginal",
            "notes": None,
        }
        validated = validate_llm_result(result)
        assert validated["frames"][0]["sentiment"] == sentiment


def test_validate_empty_frames():
    result = {"frames": [], "axiological_coverage": "none", "notes": None}
    validated = validate_llm_result(result)
    assert validated["frames"] == []
