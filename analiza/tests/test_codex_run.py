import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from codex_run_lib import select_stratified_sample


def _row(symbol, category, coverage, error=False):
    return {"symbol": symbol, "category": category,
            "axiological_coverage": coverage, "error": error}


def test_sample_is_deterministic_with_seed():
    rows = [_row(f"S{i}", f"Cat{i % 4}", "present" if i % 2 else "none") for i in range(200)]
    a = select_stratified_sample(rows, target_n=40, seed=42)
    b = select_stratified_sample(rows, target_n=40, seed=42)
    assert a == b
    assert len(a) == 40


def test_sample_skips_error_rows():
    rows = [_row(f"E{i}", "Cat0", "error", error=True) for i in range(10)]
    rows += [_row(f"G{i}", "Cat0", "present") for i in range(10)]
    sample = select_stratified_sample(rows, target_n=10, seed=1)
    assert all(s.startswith("G") for s in sample)


def test_sample_spans_multiple_categories():
    rows = [_row(f"A{i}", "CatA", "present") for i in range(50)]
    rows += [_row(f"B{i}", "CatB", "none") for i in range(50)]
    sample = select_stratified_sample(rows, target_n=20, seed=7)
    cats = {s[0] for s in sample}  # 'A' lub 'B'
    assert cats == {"A", "B"}  # obie warstwy reprezentowane


def test_sample_returns_all_when_target_exceeds_population():
    rows = [_row(f"S{i}", "Cat0", "present") for i in range(5)]
    sample = select_stratified_sample(rows, target_n=100, seed=1)
    assert len(sample) == 5
