import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from filter_value_frames_lib import filter_seed


def test_filter_seed_matches_management():
    matched, tokens = filter_seed("The management team is corrupt and hiding losses")
    assert matched is True
    assert "management" in tokens
    assert "corrupt" in tokens


def test_filter_seed_rejects_pure_trading():
    matched, tokens = filter_seed("RSI oversold, bounce incoming, buy the dip")
    assert matched is False
    assert tokens == []


def test_filter_seed_partial_match_stem():
    matched, tokens = filter_seed("They keep diluting shareholders with new share issuance")
    assert matched is True
    assert "dilut" in tokens


def test_filter_seed_empty_text():
    matched, tokens = filter_seed("")
    assert matched is False
    assert tokens == []


def test_filter_embedding_axiological_post_passes():
    """Post o wartościach powinien mieć wyższe similarity niż trading-post."""
    from sentence_transformers import SentenceTransformer
    from filter_value_frames_lib import build_concept_embedding, filter_embedding_batch

    model = SentenceTransformer("all-MiniLM-L6-v2")  # mały model do testów
    concept_emb = build_concept_embedding(model)

    axiological = "The board is systematically diluting shareholders with no accountability"
    trading = "RSI 30, oversold, buy the dip, chart looks bullish"

    results, scores = filter_embedding_batch([axiological, trading], model, concept_emb, threshold=0.0)
    assert scores[0] > scores[1]


def test_filter_embedding_threshold_rejects_low_similarity():
    from sentence_transformers import SentenceTransformer
    from filter_value_frames_lib import build_concept_embedding, filter_embedding_batch

    model = SentenceTransformer("all-MiniLM-L6-v2")
    concept_emb = build_concept_embedding(model)

    results, scores = filter_embedding_batch(
        ["buy buy buy moon lamborghini gains"],
        model, concept_emb, threshold=0.99
    )
    assert results[0] is False
