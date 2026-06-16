"""10c_llm_profiling.py

LLM per-company axiological profiling.
Dla każdej spółki sklejamy posty w prompt i pytamy model o kategorie percepcji.

Uruchomienie:
  python 10c_llm_profiling.py
  python 10c_llm_profiling.py --sample
  python 10c_llm_profiling.py --base-url http://localhost:1234/v1 --model deepseek-r1
  python 10c_llm_profiling.py --min-posts 5 --max-posts-per-company 30
  python 10c_llm_profiling.py --resume   # kontynuuje po przerwaniu
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

from openai import OpenAI

from llm_profiling_lib import validate_llm_result

# Wymusza strukturę odpowiedzi w LM Studio (response_format json_schema).
LLM_JSON_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "axiological_profile",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "frames": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string"},
                            "evidence": {"type": "string"},
                            "exposure": {"type": "string", "enum": ["low", "medium", "high"]},
                            "sentiment": {"type": "string", "enum": ["positive", "negative", "mixed", "neutral"]},
                        },
                        "required": ["label", "evidence", "exposure", "sentiment"],
                        "additionalProperties": False,
                    },
                },
                "axiological_coverage": {"type": "string", "enum": ["none", "marginal", "present", "dominant"]},
                "notes": {"type": ["string", "null"]},
            },
            "required": ["frames", "axiological_coverage", "notes"],
            "additionalProperties": False,
        },
    },
}

ROOT_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT_DIR / "analiza" / "out"
POSTS_FLAT_PATH = OUT_DIR / "posts_flat.jsonl"
POSTS_FLAT_SAMPLE_PATH = OUT_DIR / "posts_flat_sample.jsonl"
LLM_PROFILES_PATH = OUT_DIR / "llm_axiological_profiles.jsonl"
LLM_PROFILES_SAMPLE_PATH = OUT_DIR / "llm_axiological_profiles_sample.jsonl"

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


def call_llm(client: OpenAI, model: str, prompt: str, retries: int = 2) -> dict | None:
    for attempt in range(retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=1000,
                response_format=LLM_JSON_SCHEMA,
            )
            raw = response.choices[0].message.content.strip()
            # Extract JSON even if the model added text before/after
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start == -1 or end == 0:
                if attempt < retries:
                    time.sleep(1)
                    continue
                return None
            return json.loads(raw[start:end])
        except json.JSONDecodeError as e:
            print(f"  JSON parse failed (attempt {attempt+1}): {e}", file=sys.stderr)
            if attempt < retries:
                time.sleep(1)
                continue
            return None
        except Exception as e:
            print(f"  LLM error: {e}", file=sys.stderr)
            if attempt < retries:
                time.sleep(2)
                continue
            return None
    return None


def load_done_symbols(out_path: Path) -> set[str]:
    done = set()
    if not out_path.exists():
        return done
    with out_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    done.add(json.loads(line)["symbol"])
                except (json.JSONDecodeError, KeyError):
                    pass
    return done


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", action="store_true")
    parser.add_argument("--base-url", type=str, default="http://localhost:1234/v1",
                        help="OpenAI-compatible API base URL (LM Studio / lokalny LLM)")
    parser.add_argument("--model", type=str, default="local-model",
                        help="Nazwa modelu w lokalnym serwerze")
    parser.add_argument("--api-key", type=str, default="not-needed")
    parser.add_argument("--min-posts", type=int, default=5)
    parser.add_argument("--max-posts-per-company", type=int, default=25)
    parser.add_argument("--resume", action="store_true",
                        help="Kontynuuj od miejsca przerwania (pomija juz przetworzone spolki)")
    parser.add_argument("--limit-companies", type=int, default=None,
                        help="Ogranicz liczbe spolek (do testow)")
    parser.add_argument("--output-file", type=str, default=None,
                        help="Nadpisz domyslna sciezke wyjsciowa (przydatne przy ablacji: --output-file analiza/out/llm_axiological_profiles_claude.jsonl)")
    args = parser.parse_args()

    posts_path = POSTS_FLAT_SAMPLE_PATH if args.sample else POSTS_FLAT_PATH
    if args.output_file:
        out_path = Path(args.output_file)
    else:
        out_path = LLM_PROFILES_SAMPLE_PATH if args.sample else LLM_PROFILES_PATH

    if not posts_path.exists():
        print(f"ERROR: brak pliku: {posts_path}", file=sys.stderr)
        sys.exit(1)

    if not args.resume and out_path.exists():
        print(f"WARN: nadpisuję istniejący plik {out_path} (użyj --resume aby kontynuować)", file=sys.stderr)

    print(f"Ładowanie postów: {posts_path}")
    companies = load_posts_by_company(posts_path, min_posts=args.min_posts)
    print(f"Spółek z >= {args.min_posts} postami: {len(companies)}")

    done = set()
    if args.resume:
        done = load_done_symbols(out_path)
        print(f"Wznowienie: pominięto {len(done)} już przetworzonych spółek")

    symbols = sorted(companies.keys())
    if args.limit_companies:
        symbols = symbols[:args.limit_companies]

    client = OpenAI(base_url=args.base_url, api_key=args.api_key)

    mode = "a" if args.resume else "w"
    processed = 0
    errors = 0

    with out_path.open(mode, encoding="utf-8") as f:
        for i, symbol in enumerate(symbols):
            if symbol in done:
                continue

            data = companies[symbol]
            print(f"[{i+1}/{len(symbols)}] {symbol} ({len(data['posts'])} postów)...", end=" ", flush=True)

            prompt = build_prompt(symbol, data, max_posts=args.max_posts_per_company)
            result = call_llm(client, args.model, prompt)

            if result is None:
                errors += 1
                print("BŁĄD")
                row = {
                    "symbol": symbol,
                    "category": data.get("category"),
                    "industry": data.get("industry"),
                    "post_count": len(data["posts"]),
                    "frames": [],
                    "axiological_coverage": "error",
                    "notes": "LLM call failed",
                    "error": True,
                }
            else:
                processed += 1
                validated = validate_llm_result(result)
                print(f"OK ({len(validated['frames'])} frames, coverage={validated['axiological_coverage']})")
                row = {
                    "symbol": symbol,
                    "category": data.get("category"),
                    "industry": data.get("industry"),
                    "post_count": len(data["posts"]),
                    **validated,
                    "error": False,
                }

            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()

    print(f"\nGotowe: {processed} OK, {errors} błędów")
    print(f"Zapisano: {out_path}")


if __name__ == "__main__":
    main()
