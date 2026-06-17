import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm_profiling_lib import build_prompt, load_posts_by_company, PROMPT_TEMPLATE


def test_build_prompt_contains_symbol_and_posts():
    data = {"posts": ["SEC is investigating the CEO over fraud", "lawsuit filed yesterday"],
            "category": "Finance", "industry": "Banks"}
    prompt = build_prompt("ACME", data, max_posts=25)
    assert "ACME" in prompt
    assert "SEC is investigating" in prompt
    assert "Finance" in prompt
    assert "shown_posts" not in prompt  # placeholder został podstawiony


def test_build_prompt_truncates_posts_to_max():
    data = {"posts": [f"post number {i} about governance" for i in range(50)],
            "category": "X", "industry": "Y"}
    prompt = build_prompt("SYM", data, max_posts=25)
    assert "post number 24" in prompt
    assert "post number 25" not in prompt


def test_load_posts_by_company_filters_min_posts(tmp_path):
    import json
    p = tmp_path / "posts.jsonl"
    rows = [{"symbol": "AAA", "text": "governance lawsuit details here", "category": "C", "industry": "I"}] * 3
    rows += [{"symbol": "BBB", "text": "labor strike happening now everywhere", "category": "C", "industry": "I"}] * 6
    with p.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    out = load_posts_by_company(p, min_posts=5)
    assert "BBB" in out
    assert "AAA" not in out  # tylko 3 posty < 5
