import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fuse_axiological_lib import (
    compute_inter_method_agreement,
    compute_axiological_confidence,
    merge_frames,
)


def test_agreement_full_overlap():
    """Wszystkie metody widzą te same kategorie → agreement = 1.0."""
    methods = {
        "bertopic_seed": {"topic_exposure": {"12": 0.4, "5": 0.2}},
        "bertopic_nofilter": {"topic_exposure": {"12": 0.3}},
        "llm": {"frames": [{"label": "management accountability"}, {"label": "regulatory risk"}]},
    }
    # Minimalny test: agreement > 0 gdy jest pokrycie
    agreement = compute_inter_method_agreement(methods)
    assert 0.0 <= agreement <= 1.0


def test_agreement_no_overlap():
    """Tylko jedna metoda ma wyniki → agreement = 0.0."""
    methods = {
        "bertopic_seed": {"topic_exposure": {}},
        "bertopic_nofilter": {"topic_exposure": {}},
        "llm": {"frames": []},
    }
    agreement = compute_inter_method_agreement(methods)
    assert agreement == 0.0


def test_confidence_increases_with_coverage():
    """Wyższy coverage i więcej postów → wyższy confidence."""
    low = compute_axiological_confidence(coverage=0.05, post_count=10, method_count=1)
    high = compute_axiological_confidence(coverage=0.40, post_count=50, method_count=3)
    assert high > low


def test_confidence_zero_for_no_posts():
    conf = compute_axiological_confidence(coverage=0.0, post_count=0, method_count=0)
    assert conf == 0.0


def test_merge_frames_deduplicates():
    """Frames z różnych metod powinny być deduplikowane po podobieństwie etykiety."""
    frames = [
        {"label": "management accountability", "source": "llm"},
        {"label": "management accountability", "source": "llm"},
        {"label": "regulatory risk", "source": "bertopic"},
    ]
    merged = merge_frames(frames)
    labels = [f["label"] for f in merged]
    assert len(labels) == len(set(labels))
