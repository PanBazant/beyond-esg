"""Wspólna logika LLM profiling — walidacja, prompt, ładowanie postów. Importowana przez 10c, 13 i testy."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

VALID_COVERAGE_VALUES = {"none", "marginal", "present", "dominant"}
VALID_SENTIMENT_VALUES = {"positive", "negative", "mixed", "neutral"}


def validate_llm_result(result: dict) -> dict:
    coverage = result.get("axiological_coverage", "none")
    if coverage not in VALID_COVERAGE_VALUES:
        coverage = "none"

    frames = result.get("frames") or []
    validated_frames = []
    for frame in frames:
        sentiment = frame.get("sentiment", "neutral")
        if sentiment not in VALID_SENTIMENT_VALUES:
            sentiment = "neutral"
        validated_frames.append({**frame, "sentiment": sentiment})

    return {
        "frames": validated_frames,
        "axiological_coverage": coverage,
        "notes": result.get("notes"),
    }


PROMPT_TEMPLATE = """\
You are analyzing investor commentary about publicly traded companies.
Your task: identify PERCEPTUAL FRAMES and VALUE LENSES in investor discourse.

Company: {symbol} | Category: {category} | Industry: {industry}
Total posts collected: {total_posts} | Posts shown below: {shown_posts}

--- POSTS ---
{posts_text}
--- END POSTS ---

Question: Through which value lenses or perceptual frames do investors discuss this company?
Do NOT rate sentiment (liked/not liked). Focus on CATEGORIES OF PERCEPTION.
For each frame, also assess the overall sentiment direction of the discourse around it: positive (investors discuss it favorably), negative (unfavorably), mixed (both positive and negative signals present), or neutral (factual, no clear direction).

Examples of valid frames:
- "regulatory scrutiny" (investors talk about SEC, lawsuits, compliance)
- "management accountability" (investors question CEO decisions, board actions)
- "environmental footprint" (investors mention oil, emissions, resource extraction)
- "labor practices" (investors mention workers, strikes, layoffs)
- "financial opacity" (investors question accounting, debt transparency)
- "innovation narrative" (investors frame company as tech disruptor)

These are NOT frames — never output them. They are pure trading chatter, not value lenses:
- price moves / "it keeps crashing" / "fell off the cliff" / market volatility / momentum
- volume, liquidity, "no volume"
- short interest, short squeeze, price targets, valuation, market cap
If the posts contain ONLY this kind of trading chatter, return an empty frames list with axiological_coverage "none".
Only cite evidence from posts that actually mention the company {symbol}; ignore quotes about other tickers.

For axiological_coverage, judge how much the discourse is about value lenses vs plain trading talk. Be strict and discriminate — do NOT default to "present":
- "none": posts are entirely trading chatter (price, volume, technical analysis, RSI/MACD, price targets) with no value lens. Return frames: [].
- "marginal": overwhelmingly trading talk; at most one weak, incidental value frame.
- "present": value frames are a clear, recurring part of the discussion alongside trading talk.
- "dominant": value lenses (regulation, governance, labor, ethics, environment, accountability) are the main thing investors discuss about this company.
If posts are mostly RSI/MACD/support-resistance/price-target chatter, the answer is "none" or "marginal", never "present".

Respond with valid JSON only, no extra text:
{{
  "frames": [
    {{"label": "short descriptive label (2-4 words)", "evidence": "brief quote or paraphrase from posts", "exposure": "low|medium|high", "sentiment": "positive|negative|mixed|neutral"}},
    ...
  ],
  "axiological_coverage": "none|marginal|present|dominant",
  "notes": "brief observation or null"
}}

If no value frames are detectable, return: {{"frames": [], "axiological_coverage": "none", "notes": null}}
"""


def load_posts_by_company(path: Path, min_posts: int = 5) -> dict[str, dict]:
    """Ładuje posty zgrupowane per spółka. Pomija spółki z < min_posts."""
    by_company: dict[str, list[str]] = defaultdict(list)
    meta: dict[str, dict] = {}

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"WARN: skipping malformed line: {e}", file=sys.stderr)
                continue
            symbol = str(row.get("symbol") or "").upper()
            text = str(row.get("text") or "").strip()
            if not symbol or not text or len(text) < 15:
                continue
            by_company[symbol].append(text)
            if symbol not in meta:
                meta[symbol] = {
                    "category": str(row.get("category") or "Unknown"),
                    "industry": str(row.get("industry") or "Unknown"),
                }

    return {
        symbol: {"posts": posts, **meta.get(symbol, {})}
        for symbol, posts in by_company.items()
        if len(posts) >= min_posts
    }


def build_prompt(symbol: str, data: dict, max_posts: int = 25) -> str:
    posts = data["posts"][:max_posts]
    posts_text = "\n".join(f"- {p[:200]}" for p in posts)
    return PROMPT_TEMPLATE.format(
        symbol=symbol,
        category=data.get("category", "Unknown"),
        industry=data.get("industry", "Unknown"),
        total_posts=len(data["posts"]),
        shown_posts=len(posts),
        posts_text=posts_text,
    )
