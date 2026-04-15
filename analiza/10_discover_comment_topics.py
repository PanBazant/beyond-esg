from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from sklearn.decomposition import NMF
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer


ROOT_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT_DIR / "analiza" / "out"
POSTS_SCORED_PATH = OUT_DIR / "posts_scored.jsonl"
POSTS_SCORED_SAMPLE_PATH = OUT_DIR / "posts_scored_sample.jsonl"
TOPIC_ASSIGNMENTS_PATH = OUT_DIR / "comment_topic_assignments.jsonl"
TOPIC_ASSIGNMENTS_SAMPLE_PATH = OUT_DIR / "comment_topic_assignments_sample.jsonl"
COMPANY_TOPIC_FEATURES_PATH = OUT_DIR / "company_topic_features.jsonl"
COMPANY_TOPIC_FEATURES_SAMPLE_PATH = OUT_DIR / "company_topic_features_sample.jsonl"
TOPIC_SUMMARY_PATH = OUT_DIR / "comment_topic_summary.json"
TOPIC_SUMMARY_SAMPLE_PATH = OUT_DIR / "comment_topic_summary_sample.json"

URL_RE = re.compile(r"https?://\S+")
DOMAIN_RE = re.compile(r"\b(?:[a-z0-9-]+\.)+(?:com|net|org|io|co|ai|gov|edu|biz|info|me|ca|uk|de|fr|jp|cn|ly|gg)\b(?:/\S*)?", re.IGNORECASE)
CASHTAG_RE = re.compile(r"\$[A-Za-z][A-Za-z0-9\.\-]*")
MENTION_RE = re.compile(r"@[A-Za-z0-9_]+")
NON_WORD_RE = re.compile(r"[^a-z\s]")
MULTISPACE_RE = re.compile(r"\s+")
NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
TOKEN_RE = re.compile(r"[a-z]{3,}")

DOMAIN_STOP_WORDS = {
    "bullish",
    "bearish",
    "stock",
    "stocks",
    "share",
    "shares",
    "trading",
    "trade",
    "trader",
    "market",
    "price",
    "chart",
    "charts",
    "watch",
    "watching",
    "hold",
    "holding",
    "buy",
    "sell",
    "long",
    "short",
    "calls",
    "puts",
    "option",
    "options",
    "today",
    "tomorrow",
    "week",
    "daily",
    "swing",
    "position",
    "entry",
    "exit",
    "target",
    "stop",
    "support",
    "resistance",
    "breakout",
    "break",
    "float",
    "green",
    "red",
    "lol",
    "lmao",
    "imo",
    "imho",
    "fomo",
    "news",
    "nice",
    "good",
    "great",
    "bad",
    "thanks",
    "pump",
    "dump",
    "moon",
    "mooning",
    "bro",
    "guys",
    "company",
    "companies",
    "com",
    "net",
    "org",
    "www",
    "article",
    "articles",
    "press",
    "release",
    "releases",
    "newsfilecorp",
    "stocksrunner",
    "seekingalpha",
    "stocktitan",
    "linkedin",
    "tipranks",
    "yahoo",
    "finance",
    "year",
    "new",
    "growth",
    "strong",
    "cash",
    "million",
    "reported",
    "results",
    "recap",
    "eps",
    "gaap",
    "report",
    "time",
    "going",
    "higher",
    "lower",
    "like",
    "looks",
    "look",
    "feels",
    "just",
    "got",
    "dont",
    "did",
    "know",
    "think",
    "day",
    "days",
    "soon",
    "coming",
    "big",
    "small",
    "watchlist",
    "ride",
    "close",
    "volume",
    "average",
    "momentum",
    "morning",
    "afternoon",
    "tonight",
    "weekend",
    "lets",
    "let",
    "gonna",
    "wow",
    "wtf",
    "maybe",
    "guess",
    "ready",
    "started",
    "start",
    "hope",
    "hoping",
    "thing",
    "things",
    "people",
    "really",
    "happened",
    "happens",
}
STOP_WORDS = sorted(set(ENGLISH_STOP_WORDS).union(DOMAIN_STOP_WORDS))
BOILERPLATE_PATTERNS = (
    "not a financial advisor",
    "for educational purposes",
    "contract selected",
    "current stock price",
    "shared as daily free alerts",
    "potential upside",
    "time to expiration",
    "results recap",
    "wall st is expecting",
    "setting the rating",
    "target price",
    "price target",
    "quantumstockalerts",
    "marketbeat",
    "estimize",
    "abnnewswire",
    "newsletter.",
    "x.com/",
    "stocktwits.com/",
    "investing.com",
    "zacks.com",
    "whatsapp",
    "youtube.com",
    "talkmarkets",
    "macroaxis",
    "wallstreetwaves.com",
    "dragonalgo",
    "signal contract",
    "premium tp",
    "expiry strike",
    "updates rating for",
    "target set at",
    "relative strength index",
    "overbought rsi",
    "oversold rsi",
    "give him a follow",
    "caught a few of",
    "plays over the last few weeks",
)

AUTO_FEED_PATTERNS = (
    "filed form",
    "delayed filed",
    "filed sec",
    "sec.gov/archives",
    "sec.gov/ix",
    "updated risk factors",
    "sharpens risks",
    "earnings results recap",
    "reported gaap eps",
    "reported revenue",
    "expects full year",
    "ceo purchased",
    "for a total of",
    "now owns",
    "ceo-buys.com",
    "class action",
    "agreed to settle",
    "reached a settlement with investors",
    "shareholder vote",
    "mergerbrief",
    "claim deadline",
    "materially false and misleading statements",
    "quarterlyresults",
    "otcmarkets",
    "otcstocks",
    "briefing.com",
    "newsfilecorp",
    "globenewswire",
)

AUTO_FEED_HINTS = {
    "filed",
    "form",
    "sec",
    "delayed",
    "settlement",
    "investors",
    "claim",
    "claims",
    "merger",
    "vote",
    "shareholder",
    "shareholders",
    "purchased",
    "owns",
    "total",
    "ceo",
    "reported",
    "guidance",
    "recap",
    "risk",
    "factors",
}

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def normalize_text(text: str) -> str:
    lowered = text.lower()
    lowered = URL_RE.sub(" ", lowered)
    lowered = DOMAIN_RE.sub(" ", lowered)
    lowered = CASHTAG_RE.sub(" ", lowered)
    lowered = MENTION_RE.sub(" ", lowered)
    lowered = NON_WORD_RE.sub(" ", lowered)
    lowered = MULTISPACE_RE.sub(" ", lowered).strip()
    return lowered


def template_text(text: str) -> str:
    lowered = text.lower()
    lowered = URL_RE.sub(" ", lowered)
    lowered = DOMAIN_RE.sub(" ", lowered)
    lowered = CASHTAG_RE.sub(" ", lowered)
    lowered = MENTION_RE.sub(" ", lowered)
    lowered = NUMBER_RE.sub(" ", lowered)
    lowered = NON_WORD_RE.sub(" ", lowered)
    lowered = MULTISPACE_RE.sub(" ", lowered).strip()
    return lowered


def is_boilerplate(text: str, template: str, template_frequency: int, threshold: int) -> bool:
    lowered = text.lower()
    if any(pattern in lowered for pattern in BOILERPLATE_PATTERNS):
        return True
    if any(pattern in lowered for pattern in AUTO_FEED_PATTERNS):
        return True

    template_tokens = set(TOKEN_RE.findall(template))
    if len(template_tokens & AUTO_FEED_HINTS) >= 4 and len(template_tokens) <= 18:
        return True

    template_words = template.split()
    if template_frequency >= threshold and len(template_words) >= 5:
        return True
    return False


def trim_text(text: str, limit: int = 180) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def informative_text(text: str) -> str:
    tokens = [token for token in TOKEN_RE.findall(text) if token not in STOP_WORDS]
    return " ".join(tokens)


def normalize_rows(topic_matrix: np.ndarray) -> np.ndarray:
    row_sums = topic_matrix.sum(axis=1, keepdims=True)
    safe_sums = np.where(row_sums <= 0, 1.0, row_sums)
    return topic_matrix / safe_sums


def choose_topic_count(doc_count: int, requested_topics: int) -> int:
    if doc_count <= 0:
        return 0
    lower_bound = 12 if doc_count >= 5_000 else 6
    upper_bound = 72 if doc_count >= 20_000 else 56 if doc_count >= 10_000 else 24
    return max(lower_bound, min(requested_topics, upper_bound, doc_count - 1 if doc_count > 1 else 1))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-file", type=str, default=None)
    parser.add_argument("--topics", type=int, default=64)
    parser.add_argument("--max-features", type=int, default=9000)
    parser.add_argument("--min-df", type=int, default=10)
    parser.add_argument("--max-df", type=float, default=0.22)
    parser.add_argument("--template-frequency-threshold", type=int, default=12)
    parser.add_argument("--limit-posts", type=int, default=None)
    parser.add_argument("--sample", action="store_true")
    args = parser.parse_args()

    ensure_dir(OUT_DIR)
    input_path = Path(args.input_file) if args.input_file else (POSTS_SCORED_SAMPLE_PATH if args.sample else POSTS_SCORED_PATH)
    assignments_path = TOPIC_ASSIGNMENTS_SAMPLE_PATH if args.sample else TOPIC_ASSIGNMENTS_PATH
    company_features_path = COMPANY_TOPIC_FEATURES_SAMPLE_PATH if args.sample else COMPANY_TOPIC_FEATURES_PATH
    topic_summary_path = TOPIC_SUMMARY_SAMPLE_PATH if args.sample else TOPIC_SUMMARY_PATH

    if not input_path.exists():
        raise FileNotFoundError(f"Brak pliku wejściowego: {input_path}")

    candidate_rows: list[dict] = []
    template_counter: Counter[str] = Counter()

    with input_path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            row = json.loads(line)
            text = (row.get("text") or "").strip()
            if not text:
                continue
            normalized = normalize_text(text)
            informative = informative_text(normalized)
            if len(informative.split()) < 3:
                continue
            template = template_text(text)
            candidate_rows.append({"row": row, "normalized": informative, "template": template})
            template_counter[template] += 1
            if args.limit_posts is not None and len(candidate_rows) >= args.limit_posts:
                break

    documents: list[str] = []
    doc_rows: list[dict] = []
    skipped_boilerplate = 0
    for item in candidate_rows:
        row = item["row"]
        template = item["template"]
        if is_boilerplate(str(row.get("text") or ""), template, template_counter[template], args.template_frequency_threshold):
            skipped_boilerplate += 1
            continue
        documents.append(item["normalized"])
        doc_rows.append(row)

    if len(doc_rows) < 25:
        raise RuntimeError("Za mało tekstowych komentarzy do odkrywania tematów.")

    min_df = min(args.min_df, max(2, len(doc_rows) // 50))
    vectorizer = TfidfVectorizer(
        stop_words=STOP_WORDS,
        lowercase=False,
        ngram_range=(1, 2),
        min_df=min_df,
        max_df=args.max_df,
        max_features=args.max_features,
        sublinear_tf=True,
    )
    matrix = vectorizer.fit_transform(documents)
    topic_count = choose_topic_count(matrix.shape[0], args.topics)

    nmf = NMF(
        n_components=topic_count,
        init="nndsvda",
        random_state=42,
        max_iter=400,
    )
    doc_topic_weights = nmf.fit_transform(matrix)
    doc_topic_shares = normalize_rows(doc_topic_weights)

    feature_names = vectorizer.get_feature_names_out()
    components = nmf.components_

    topic_examples: dict[int, list[tuple[float, str, str]]] = defaultdict(list)
    topic_sentiment_sum = np.zeros(topic_count, dtype=float)
    topic_weight_sum = np.zeros(topic_count, dtype=float)
    topic_post_count = np.zeros(topic_count, dtype=int)
    company_buckets: dict[str, dict] = {}

    with assignments_path.open("w", encoding="utf-8") as assignments_handle:
        for row, topic_distribution in zip(doc_rows, doc_topic_shares, strict=False):
            dominant_topic = int(np.argmax(topic_distribution))
            top_indices = np.argsort(topic_distribution)[::-1][:3]
            topic_hits = []
            for topic_id in top_indices:
                weight = float(topic_distribution[topic_id])
                if weight < 0.08:
                    continue
                topic_hits.append({"topic_id": int(topic_id), "weight": round(weight, 4)})
                topic_sentiment_sum[topic_id] += weight * float(row.get("sentiment_score") or 0.0)
                topic_weight_sum[topic_id] += weight
                topic_post_count[topic_id] += 1
                topic_examples[topic_id].append(
                    (
                        weight,
                        str(row.get("message_id") or ""),
                        trim_text(str(row.get("text") or "")),
                    )
                )

            assignment_row = {
                "message_id": row.get("message_id"),
                "symbol": row.get("symbol"),
                "sentiment_score": row.get("sentiment_score"),
                "dominant_topic_id": dominant_topic,
                "dominant_topic_weight": round(float(topic_distribution[dominant_topic]), 4),
                "top_topics": topic_hits,
            }
            assignments_handle.write(json.dumps(assignment_row, ensure_ascii=False) + "\n")

            symbol = str(row.get("symbol") or "").upper()
            bucket = company_buckets.setdefault(
                symbol,
                {
                    "symbol": symbol,
                    "company_name": row.get("company_name") or symbol,
                    "category": row.get("category") or "Unknown",
                    "industry": row.get("industry"),
                    "market_cap": row.get("market_cap"),
                    "rank_in_category": row.get("rank_in_category"),
                    "posts_count": 0,
                    "text_posts_count": 0,
                    "topic_weight_sum_total": 0.0,
                    "topics": defaultdict(lambda: {"weight_sum": 0.0, "weighted_sentiment_sum": 0.0, "posts_with_topic": 0}),
                },
            )
            bucket["posts_count"] += 1
            bucket["text_posts_count"] += 1

            for topic_id, weight in enumerate(topic_distribution):
                weight = float(weight)
                if weight < 0.05:
                    continue
                topic_bucket = bucket["topics"][int(topic_id)]
                topic_bucket["weight_sum"] += weight
                topic_bucket["weighted_sentiment_sum"] += weight * float(row.get("sentiment_score") or 0.0)
                topic_bucket["posts_with_topic"] += 1
                bucket["topic_weight_sum_total"] += weight

    topic_rows = []
    for topic_id in range(topic_count):
        term_indices = np.argsort(components[topic_id])[::-1][:10]
        top_terms = [str(feature_names[index]) for index in term_indices]
        avg_sentiment = topic_sentiment_sum[topic_id] / topic_weight_sum[topic_id] if topic_weight_sum[topic_id] > 0 else 0.0
        examples = [
            {"message_id": message_id, "snippet": snippet, "weight": round(weight, 4)}
            for weight, message_id, snippet in sorted(topic_examples[topic_id], key=lambda item: item[0], reverse=True)[:3]
        ]
        topic_rows.append(
            {
                "topic_id": topic_id,
                "label_hint": " / ".join(top_terms[:3]),
                "top_terms": top_terms,
                "corpus_weight": round(float(topic_weight_sum[topic_id]), 4),
                "posts_with_topic": int(topic_post_count[topic_id]),
                "average_sentiment": round(float(avg_sentiment), 4),
                "example_messages": examples,
            }
        )

    with company_features_path.open("w", encoding="utf-8") as handle:
        for symbol in sorted(company_buckets):
            bucket = company_buckets[symbol]
            total_weight = bucket["topic_weight_sum_total"] or 1.0
            topics = []
            for topic_id, topic_bucket in bucket["topics"].items():
                avg_sentiment = (
                    topic_bucket["weighted_sentiment_sum"] / topic_bucket["weight_sum"]
                    if topic_bucket["weight_sum"] > 0
                    else 0.0
                )
                topic_share = topic_bucket["weight_sum"] / total_weight
                topics.append(
                    {
                        "topic_id": int(topic_id),
                        "topic_share": round(topic_share, 4),
                        "topic_weight_sum": round(topic_bucket["weight_sum"], 4),
                        "posts_with_topic": int(topic_bucket["posts_with_topic"]),
                        "avg_sentiment": round(float(avg_sentiment), 4),
                        "signed_topic_score": round(float(topic_share * avg_sentiment), 4),
                    }
                )

            topics.sort(key=lambda item: item["topic_share"], reverse=True)
            dominant_topics = [topic["topic_id"] for topic in topics[:5]]
            row = {
                "symbol": bucket["symbol"],
                "company_name": bucket["company_name"],
                "category": bucket["category"],
                "industry": bucket["industry"],
                "market_cap": bucket["market_cap"],
                "rank_in_category": bucket["rank_in_category"],
                "posts_count": bucket["posts_count"],
                "text_posts_count": bucket["text_posts_count"],
                "dominant_topic_ids": dominant_topics,
                "topics": topics,
                "topic_model_version": "topics-v2-nmf",
            }
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    topic_summary = {
        "input_file": str(input_path),
        "output_assignments_file": str(assignments_path),
        "output_company_features_file": str(company_features_path),
        "documents_used": len(doc_rows),
        "documents_skipped_as_boilerplate": skipped_boilerplate,
        "topics_count": topic_count,
        "vectorizer": {
            "min_df": min_df,
            "max_df": args.max_df,
            "max_features": args.max_features,
            "ngram_range": [1, 2],
        },
        "model_version": "topics-v2-nmf",
        "topics": topic_rows,
        "is_sample": args.sample,
    }
    topic_summary_path.write_text(json.dumps(topic_summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(topic_summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
