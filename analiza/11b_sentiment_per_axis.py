"""11b_sentiment_per_axis.py (opcjonalny)

VADER sentiment per (spółka, kategoria aksjologiczna).
Wzbogaca company_axiological_profile.jsonl o pole sentiment_by_frame.

Uruchomienie:
  python 11b_sentiment_per_axis.py
  python 11b_sentiment_per_axis.py --sample
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

ROOT_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT_DIR / "analiza" / "out"
POSTS_FLAT_PATH = OUT_DIR / "posts_flat.jsonl"
POSTS_FLAT_SAMPLE_PATH = OUT_DIR / "posts_flat_sample.jsonl"
PROFILE_PATH = OUT_DIR / "company_axiological_profile.jsonl"
PROFILE_SAMPLE_PATH = OUT_DIR / "company_axiological_profile_sample.jsonl"


def compute_sentiment_per_frame(
    posts: list[str],
    frames: list[dict],
    analyzer: SentimentIntensityAnalyzer,
) -> dict[str, float]:
    """Dla każdego frame: oblicza średni VADER compound score postów zawierających słowa kluczowe frame'u."""
    if not posts or not frames:
        return {}

    result = {}
    for frame in frames:
        label = str(frame.get("label") or "").strip().lower()
        if not label:
            continue
        keywords = set(label.split())
        matched_scores = []
        for post in posts:
            post_lower = post.lower()
            if any(kw in post_lower for kw in keywords):
                score = analyzer.polarity_scores(post)["compound"]
                matched_scores.append(score)

        if matched_scores:
            result[label] = round(sum(matched_scores) / len(matched_scores), 4)

    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", action="store_true")
    args = parser.parse_args()

    posts_path = POSTS_FLAT_SAMPLE_PATH if args.sample else POSTS_FLAT_PATH
    profile_path = PROFILE_SAMPLE_PATH if args.sample else PROFILE_PATH

    # Wczytaj posty per spółka
    posts_by_symbol: dict[str, list[str]] = defaultdict(list)
    with posts_path.open("r", encoding="utf-8") as f:
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
            if symbol and text:
                posts_by_symbol[symbol].append(text)

    analyzer = SentimentIntensityAnalyzer()

    if not profile_path.exists():
        print(f"ERROR: brak pliku profili: {profile_path}", file=sys.stderr)
        sys.exit(1)

    # Wczytaj profil, wzbogać, nadpisz
    profiles = []
    with profile_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                profile = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"WARN: skipping malformed profile line: {e}", file=sys.stderr)
                continue
            symbol = str(profile.get("symbol") or "").upper()
            frames = profile.get("frames") or []
            posts = posts_by_symbol.get(symbol, [])
            profile["sentiment_by_frame"] = compute_sentiment_per_frame(posts, frames, analyzer)
            profiles.append(profile)

    with profile_path.open("w", encoding="utf-8") as f:
        for p in profiles:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    with_sentiment = sum(1 for p in profiles if p.get("sentiment_by_frame"))
    print(f"Zaktualizowano {len(profiles)} profili, {with_sentiment} ma sentiment per frame.")
    print(f"Zapisano: {profile_path}")


if __name__ == "__main__":
    main()
