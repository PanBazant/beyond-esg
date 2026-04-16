import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from app.schemas import AxisPreference
from app.services.scoring import perception_score


def _company(axes):
    return {"custom_esg_axes": axes}


def test_no_prefs_returns_half():
    result = perception_score(_company([{"axis_id": 0, "label": "a", "exposure": 0.8, "score": 80.0, "confidence": 0.9}]), [], {})
    assert result == 0.5


def test_high_exposure_positive_sentiment():
    company = _company([{"axis_id": 0, "label": "a", "exposure": 0.9, "score": 90.0, "confidence": 0.9}])
    prefs = [AxisPreference(axis_id=0, importance=1.0)]
    result = perception_score(company, prefs, {0: {"average_sentiment": 1.0}})
    assert result > 0.8


def test_zero_exposure_returns_low():
    company = _company([{"axis_id": 0, "label": "a", "exposure": 0.0, "score": 0.0, "confidence": 0.0}])
    prefs = [AxisPreference(axis_id=0, importance=1.0)]
    result = perception_score(company, prefs, {0: {"average_sentiment": 1.0}})
    assert result < 0.1


def test_zero_importance_skipped():
    company = _company([{"axis_id": 0, "label": "a", "exposure": 1.0, "score": 100.0, "confidence": 1.0}])
    prefs = [AxisPreference(axis_id=0, importance=0.0)]
    result = perception_score(company, prefs, {0: {"average_sentiment": 1.0}})
    assert result == 0.5  # no active prefs → returns 0.5
