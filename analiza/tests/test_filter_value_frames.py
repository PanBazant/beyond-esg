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
