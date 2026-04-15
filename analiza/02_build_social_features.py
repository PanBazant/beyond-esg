from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split


ROOT_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT_DIR / "analiza" / "out"
POSTS_FLAT_PATH = OUT_DIR / "posts_flat.jsonl"
POSTS_SCORED_PATH = OUT_DIR / "posts_scored.jsonl"
SOCIAL_FEATURES_PATH = OUT_DIR / "company_social_features.jsonl"
SUMMARY_PATH = OUT_DIR / "company_social_features_summary.json"
POSTS_SCORED_SAMPLE_PATH = OUT_DIR / "posts_scored_sample.jsonl"
SOCIAL_FEATURES_SAMPLE_PATH = OUT_DIR / "company_social_features_sample.jsonl"
SUMMARY_SAMPLE_PATH = OUT_DIR / "company_social_features_sample_summary.json"

URL_RE = re.compile(r"https?://\S+")
CASHTAG_RE = re.compile(r"\$[A-Za-z][A-Za-z0-9\.\-]*")
MENTION_RE = re.compile(r"@[A-Za-z0-9_]+")
MULTISPACE_RE = re.compile(r"\s+")
NON_ALPHA_RE = re.compile(r"[^a-z\s]")
BULLISH_RE = re.compile(r"\bbullish\b", re.IGNORECASE)
BEARISH_RE = re.compile(r"\bbearish\b", re.IGNORECASE)
TOKEN_RE = re.compile(r"[a-z]{2,}")

LOW_NORM_KEYWORDS = {
    "oil",
    "gas",
    "mining",
    "gambling",
    "alcohol",
    "tobacco",
    "coal",
    "uranium",
    "weapons",
    "defense",
    "casino",
    "betting",
}
HIGH_NORM_KEYWORDS = {
    "software",
    "education",
    "medical",
    "diagnostics",
    "internet",
    "water",
    "recycling",
    "renewable",
    "health",
    "biotech",
}


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def normalize_training_text(text: str) -> str:
    cleaned = text.strip().lower()
    cleaned = URL_RE.sub(" ", cleaned)
    cleaned = CASHTAG_RE.sub(" ", cleaned)
    cleaned = MENTION_RE.sub(" ", cleaned)
    cleaned = BULLISH_RE.sub(" ", cleaned)
    cleaned = BEARISH_RE.sub(" ", cleaned)
    cleaned = NON_ALPHA_RE.sub(" ", cleaned)
    cleaned = MULTISPACE_RE.sub(" ", cleaned).strip()
    return cleaned


def detect_explicit_label(text: str) -> str | None:
    bullish = bool(BULLISH_RE.search(text))
    bearish = bool(BEARISH_RE.search(text))
    if bullish and not bearish:
        return "positive"
    if bearish and not bullish:
        return "negative"
    return None


def category_prior(category: str) -> float:
    lowered = (category or "").lower()
    score = 0.5
    if any(keyword in lowered for keyword in LOW_NORM_KEYWORDS):
        score -= 0.2
    if any(keyword in lowered for keyword in HIGH_NORM_KEYWORDS):
        score += 0.2
    return max(0.0, min(1.0, score))


def fallback_sentiment(cleaned_text: str) -> dict:
    tokens = TOKEN_RE.findall(cleaned_text)
    positive_terms = {
        "profit",
        "growth",
        "strong",
        "up",
        "beat",
        "bull",
        "good",
        "great",
        "win",
        "winner",
    }
    negative_terms = {
        "loss",
        "fraud",
        "weak",
        "down",
        "miss",
        "bad",
        "scam",
        "dilution",
        "dump",
        "bankrupt",
    }
    pos_hits = sum(1 for token in tokens if token in positive_terms)
    neg_hits = sum(1 for token in tokens if token in negative_terms)
    raw_signal = (pos_hits - neg_hits) / (pos_hits + neg_hits + 1)
    confidence = min(1.0, 0.20 + 0.18 * (pos_hits + neg_hits))
    score = raw_signal * confidence
    if score > 0.20:
        label = "positive"
    elif score < -0.20:
        label = "negative"
    else:
        label = "neutral"
    return {
        "sentiment_score": round(score, 4),
        "sentiment_label": label,
        "sentiment_confidence": round(confidence, 4),
        "sentiment_source": "fallback-lexicon",
    }


def train_sentiment_model(rows: list[dict]) -> tuple[dict | None, dict]:
    labeled_rows = []
    for row in rows:
        label = detect_explicit_label(row["text"])
        cleaned = row["cleaned_text"]
        if label is None or len(cleaned.split()) < 2:
            continue
        labeled_rows.append({"text": cleaned, "label": label})

    label_counter = Counter(item["label"] for item in labeled_rows)
    if label_counter["positive"] < 25 or label_counter["negative"] < 25:
        return None, {
            "model_version": "sentiment-v2-distant-logreg",
            "status": "insufficient_labels",
            "training_rows": len(labeled_rows),
            "label_distribution": dict(label_counter),
        }

    texts = [item["text"] for item in labeled_rows]
    labels = [item["label"] for item in labeled_rows]

    vectorizer = TfidfVectorizer(
        ngram_range=(1, 2),
        min_df=3,
        max_df=0.9,
        max_features=25000,
        sublinear_tf=True,
    )
    features = vectorizer.fit_transform(texts)

    model = LogisticRegression(
        max_iter=700,
        class_weight="balanced",
        random_state=42,
    )

    evaluation = {
        "model_version": "sentiment-v2-distant-logreg",
        "status": "trained",
        "training_rows": len(labeled_rows),
        "label_distribution": dict(label_counter),
        "validation_accuracy": None,
        "validation_f1_macro": None,
    }

    if len(labeled_rows) >= 200:
        X_train, X_test, y_train, y_test = train_test_split(
            features,
            labels,
            test_size=0.20,
            random_state=42,
            stratify=labels,
        )
        holdout_model = LogisticRegression(
            max_iter=700,
            class_weight="balanced",
            random_state=42,
        )
        holdout_model.fit(X_train, y_train)
        predicted = holdout_model.predict(X_test)
        evaluation["validation_accuracy"] = round(float(accuracy_score(y_test, predicted)), 4)
        evaluation["validation_f1_macro"] = round(float(f1_score(y_test, predicted, average="macro")), 4)

    model.fit(features, labels)
    return {"vectorizer": vectorizer, "model": model}, evaluation


def score_with_model(model_bundle: dict, cleaned_text: str) -> dict:
    if not cleaned_text or len(cleaned_text.split()) < 2:
        return {
            "sentiment_score": 0.0,
            "sentiment_label": "neutral",
            "sentiment_confidence": 0.0,
            "sentiment_source": "empty-text",
        }

    vectorizer: TfidfVectorizer = model_bundle["vectorizer"]
    model: LogisticRegression = model_bundle["model"]
    probabilities = model.predict_proba(vectorizer.transform([cleaned_text]))[0]
    classes = list(model.classes_)
    positive_probability = float(probabilities[classes.index("positive")]) if "positive" in classes else 0.5
    negative_probability = float(probabilities[classes.index("negative")]) if "negative" in classes else (1 - positive_probability)

    score = positive_probability - negative_probability
    confidence = abs(score)
    if score > 0.20:
        label = "positive"
    elif score < -0.20:
        label = "negative"
    else:
        label = "neutral"

    return {
        "sentiment_score": round(score, 4),
        "sentiment_label": label,
        "sentiment_confidence": round(confidence, 4),
        "sentiment_source": "tfidf-logreg",
        "prob_positive": round(positive_probability, 4),
        "prob_negative": round(negative_probability, 4),
    }


def build_sentiment_payload(model_bundle: dict | None, text: str, cleaned_text: str) -> dict:
    explicit_label = detect_explicit_label(text)
    if model_bundle is None:
        payload = fallback_sentiment(cleaned_text)
    else:
        payload = score_with_model(model_bundle, cleaned_text)

    if explicit_label and payload["sentiment_label"] == "neutral":
        payload["sentiment_label"] = explicit_label
        payload["sentiment_score"] = 0.75 if explicit_label == "positive" else -0.75
        payload["sentiment_confidence"] = max(payload["sentiment_confidence"], 0.75)
        payload["sentiment_source"] = "explicit-marker-override"

    payload["explicit_label"] = explicit_label
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit-posts", type=int, default=None)
    parser.add_argument("--input-file", type=str, default=str(POSTS_FLAT_PATH))
    parser.add_argument("--sample", action="store_true")
    args = parser.parse_args()

    ensure_dir(OUT_DIR)
    input_path = Path(args.input_file)
    posts_scored_path = POSTS_SCORED_SAMPLE_PATH if args.sample else POSTS_SCORED_PATH
    social_features_path = SOCIAL_FEATURES_SAMPLE_PATH if args.sample else SOCIAL_FEATURES_PATH
    summary_path = SUMMARY_SAMPLE_PATH if args.sample else SUMMARY_PATH

    if not input_path.exists():
        raise FileNotFoundError(f"Brak pliku wejściowego: {input_path}")

    source_rows: list[dict] = []
    total_posts = 0
    with input_path.open("r", encoding="utf-8") as in_handle:
        for raw_line in in_handle:
            line = raw_line.strip()
            if not line:
                continue
            row = json.loads(line)
            total_posts += 1
            if args.limit_posts is not None and total_posts > args.limit_posts:
                break
            text = (row.get("text") or "").strip()
            source_rows.append({**row, "text": text, "cleaned_text": normalize_training_text(text)})

    model_bundle, model_summary = train_sentiment_model(source_rows)

    aggregate: dict[str, dict] = {}
    scored_posts = 0
    sentiment_counter = Counter()
    sentiment_source_counter = Counter()
    explicit_counter = Counter()

    with posts_scored_path.open("w", encoding="utf-8") as out_handle:
        for row in source_rows:
            sentiment = build_sentiment_payload(model_bundle, row["text"], row["cleaned_text"])
            enriched = {key: value for key, value in row.items() if key != "cleaned_text"}
            enriched.update(sentiment)
            out_handle.write(json.dumps(enriched, ensure_ascii=False) + "\n")

            scored_posts += 1
            sentiment_counter[enriched["sentiment_label"]] += 1
            sentiment_source_counter[enriched["sentiment_source"]] += 1
            explicit_counter[enriched["explicit_label"] or "none"] += 1

            symbol = row["symbol"]
            company = aggregate.setdefault(
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
                    "authors": set(),
                    "sentiment_sum": 0.0,
                    "positive_count": 0,
                    "negative_count": 0,
                    "neutral_count": 0,
                },
            )

            company["posts_count"] += 1
            if row.get("username"):
                company["authors"].add(row["username"])
            if row["text"]:
                company["text_posts_count"] += 1
            company["sentiment_sum"] += enriched["sentiment_score"]
            company[f"{enriched['sentiment_label']}_count"] += 1

    with social_features_path.open("w", encoding="utf-8") as out_handle:
        for symbol in sorted(aggregate):
            company = aggregate[symbol]
            posts_count = company["posts_count"]
            positive_share = company["positive_count"] / posts_count if posts_count else 0.0
            negative_share = company["negative_count"] / posts_count if posts_count else 0.0
            avg_sentiment = company["sentiment_sum"] / posts_count if posts_count else 0.0
            controversy_score = 4 * positive_share * negative_share
            coverage_score = min(1.0, math.log1p(posts_count) / math.log1p(40))
            authors_count = len(company["authors"])
            author_diversity_score = min(1.0, (authors_count / posts_count) * 3) if posts_count else 0.0
            sector_norm_prior = category_prior(company["category"])
            social_approval = (avg_sentiment + 1) / 2
            stability_score = 1 - controversy_score
            custom_esg_proxy_score = 100 * (
                0.45 * social_approval
                + 0.25 * stability_score
                + 0.20 * sector_norm_prior
                + 0.10 * coverage_score
            )

            feature_row = {
                "symbol": symbol,
                "company_name": company["company_name"],
                "category": company["category"],
                "industry": company["industry"],
                "market_cap": company["market_cap"],
                "rank_in_category": company["rank_in_category"],
                "posts_count": posts_count,
                "text_posts_count": company["text_posts_count"],
                "authors_count": authors_count,
                "avg_sentiment": round(avg_sentiment, 4),
                "positive_share": round(positive_share, 4),
                "negative_share": round(negative_share, 4),
                "neutral_share": round(company["neutral_count"] / posts_count if posts_count else 0.0, 4),
                "controversy_score": round(controversy_score, 4),
                "coverage_score": round(coverage_score, 4),
                "author_diversity_score": round(author_diversity_score, 4),
                "sector_norm_prior": round(sector_norm_prior, 4),
                "custom_esg_proxy_score": round(custom_esg_proxy_score, 2),
                "metric_version": "social-v2-nlp-logreg",
            }
            out_handle.write(json.dumps(feature_row, ensure_ascii=False) + "\n")

    summary = {
        "input_posts_file": str(input_path),
        "output_posts_scored_file": str(posts_scored_path),
        "output_company_features_file": str(social_features_path),
        "posts_scored": scored_posts,
        "companies_scored": len(aggregate),
        "sentiment_distribution": dict(sentiment_counter),
        "sentiment_source_distribution": dict(sentiment_source_counter),
        "explicit_marker_distribution": dict(explicit_counter),
        "sentiment_model": model_summary,
        "metric_version": "social-v2-nlp-logreg",
        "is_sample": args.sample,
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
