"""10b_bertopic_discovery.py

BERTopic na każdym z trzech wejść filtrowania.
Dla każdego wejścia:
  - Trenuje BERTopic i odkrywa tematy
  - Klasyfikuje tematy jako aksjologiczne vs trading-noise
  - Oblicza ekspozycję per spółka

Uruchomienie:
  python 10b_bertopic_discovery.py --filter seed
  python 10b_bertopic_discovery.py --filter nofilter
  python 10b_bertopic_discovery.py --filter embed
  python 10b_bertopic_discovery.py --filter all
  python 10b_bertopic_discovery.py --filter seed --sample
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from bertopic import BERTopic
from hdbscan import HDBSCAN
from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from umap import UMAP

ROOT_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT_DIR / "analiza" / "out"

INPUT_PATHS = {
    "seed": OUT_DIR / "posts_valueframed_seed.jsonl",
    "seed_sample": OUT_DIR / "posts_valueframed_seed_sample.jsonl",
    "nofilter": OUT_DIR / "posts_flat.jsonl",
    "nofilter_sample": OUT_DIR / "posts_flat_sample.jsonl",
    "embed": OUT_DIR / "posts_valueframed_embed.jsonl",
    "embed_sample": OUT_DIR / "posts_valueframed_embed_sample.jsonl",
}

AXIOLOGICAL_CONCEPT = (
    "company values ethics practices governance accountability "
    "social impact labor rights environmental footprint regulatory risk "
    "management integrity community corruption"
)
NOISE_CONCEPT = (
    "stock price chart trading buy sell technical analysis RSI "
    "candlestick pattern momentum breakout oversold overbought"
)


def load_filtered_posts(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def build_bertopic_model(n_topics: int = 60) -> BERTopic:
    embedding_model = SentenceTransformer("all-mpnet-base-v2")
    umap_model = UMAP(
        n_neighbors=15, n_components=5, min_dist=0.0,
        metric="cosine", random_state=42
    )
    hdbscan_model = HDBSCAN(
        min_cluster_size=8, metric="euclidean",
        cluster_selection_method="eom", prediction_data=True
    )
    vectorizer = CountVectorizer(
        stop_words="english", min_df=2, ngram_range=(1, 2)
    )
    return BERTopic(
        embedding_model=embedding_model,
        umap_model=umap_model,
        hdbscan_model=hdbscan_model,
        vectorizer_model=vectorizer,
        nr_topics=n_topics,
        calculate_probabilities=True,
        verbose=True,
    )


def classify_topics(topic_words: dict[int, list[tuple[str, float]]], embedding_model) -> dict[int, dict]:
    """Klasyfikuje każdy temat jako aksjologiczny vs noise."""
    concept_embs = embedding_model.encode([AXIOLOGICAL_CONCEPT, NOISE_CONCEPT])

    results = {}
    for topic_id, words in topic_words.items():
        if topic_id == -1:
            results[topic_id] = {
                "is_axiological": False, "axiological_score": 0.0,
                "noise_score": 1.0, "words": "outlier"
            }
            continue
        words_str = " ".join(w for w, _ in words[:10])
        topic_emb = embedding_model.encode([words_str])
        sims = cosine_similarity(topic_emb, concept_embs)[0]
        results[topic_id] = {
            "is_axiological": float(sims[0]) > float(sims[1]),
            "axiological_score": round(float(sims[0]), 4),
            "noise_score": round(float(sims[1]), 4),
            "words": words_str,
            "top_words": [w for w, _ in words[:8]],
        }
    return results


def compute_company_exposure(
    posts: list[dict],
    topic_assignments: list[int],
    topic_classification: dict[int, dict],
) -> dict[str, dict]:
    """Oblicza ekspozycję per spółka na każdy temat aksjologiczny."""
    company_posts: dict[str, list[int]] = defaultdict(list)
    for post, topic_id in zip(posts, topic_assignments):
        symbol = str(post.get("symbol") or "").upper()
        if symbol:
            company_posts[symbol].append(topic_id)

    results = {}
    for symbol, topics in company_posts.items():
        total = len(topics)
        axiological_count = sum(
            1 for t in topics
            if t != -1 and topic_classification.get(t, {}).get("is_axiological", False)
        )
        topic_counts: dict[str, int] = defaultdict(int)
        for t in topics:
            if t != -1 and topic_classification.get(t, {}).get("is_axiological", False):
                topic_counts[str(t)] += 1

        results[symbol] = {
            "symbol": symbol,
            "post_count": total,
            "axiological_count": axiological_count,
            "axiological_coverage": round(axiological_count / total, 4) if total else 0.0,
            "topic_exposure": {
                tid: round(cnt / total, 4)
                for tid, cnt in sorted(topic_counts.items(), key=lambda x: -x[1])
            },
        }
    return results


def run_for_filter(filter_name: str, sample: bool) -> None:
    key = f"{filter_name}_sample" if sample else filter_name
    input_path = INPUT_PATHS.get(key)
    if not input_path or not input_path.exists():
        print(f"SKIP: brak pliku wejściowego dla filter={filter_name} sample={sample}: {input_path}", file=sys.stderr)
        return

    topics_out = OUT_DIR / f"bertopic_topics_{filter_name}{'_sample' if sample else ''}.json"
    exposure_out = OUT_DIR / f"company_bertopic_exposure_{filter_name}{'_sample' if sample else ''}.jsonl"

    print(f"\n=== BERTopic: filter={filter_name} ===")
    posts = load_filtered_posts(input_path)
    texts = [str(p.get("text") or "") for p in posts]
    valid = [(i, t) for i, t in enumerate(texts) if len(t.strip()) > 20]
    if len(valid) < 50:
        print(f"Za mało postów ({len(valid)}) — pomijam.", file=sys.stderr)
        # Zapisz puste pliki żeby fuzja nie crashowała
        topics_out.write_text(json.dumps({"filter": filter_name, "sample": sample, "total_posts": len(posts), "valid_posts": len(valid), "topics_count": 0, "axiological_topics_count": 0, "topics": {}, "note": "insufficient_data"}, indent=2, ensure_ascii=False), encoding="utf-8")
        with exposure_out.open("w", encoding="utf-8") as f:
            pass
        return

    valid_indices, valid_texts = zip(*valid)
    print(f"Trenowanie BERTopic na {len(valid_texts)} postach...")
    model = build_bertopic_model()
    topic_ids, _probs = model.fit_transform(list(valid_texts))

    topic_words = model.get_topics()
    embedding_model = SentenceTransformer("all-mpnet-base-v2")
    topic_classification = classify_topics(topic_words, embedding_model)

    idx_to_topic = {idx: tid for idx, tid in zip(valid_indices, topic_ids)}
    all_topic_ids = [idx_to_topic.get(i, -1) for i in range(len(posts))]

    exposure = compute_company_exposure(posts, all_topic_ids, topic_classification)

    topics_payload = {
        "filter": filter_name,
        "sample": sample,
        "total_posts": len(posts),
        "valid_posts": len(valid_texts),
        "topics_count": len([t for t in topic_classification if t != -1]),
        "axiological_topics_count": sum(1 for t in topic_classification.values() if t.get("is_axiological")),
        "topics": {str(k): v for k, v in topic_classification.items()},
    }
    topics_out.write_text(json.dumps(topics_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Tematów: {topics_payload['topics_count']}, aksjologicznych: {topics_payload['axiological_topics_count']}")
    print(f"Zapisano tematy: {topics_out}")

    with exposure_out.open("w", encoding="utf-8") as f:
        for row in sorted(exposure.values(), key=lambda x: -x["axiological_coverage"]):
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Zapisano ekspozycję: {exposure_out} ({len(exposure)} spółek)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--filter", choices=["seed", "nofilter", "embed", "all"], default="all")
    parser.add_argument("--sample", action="store_true")
    args = parser.parse_args()

    filters = ["seed", "nofilter", "embed"] if args.filter == "all" else [args.filter]
    for f in filters:
        run_for_filter(f, args.sample)


if __name__ == "__main__":
    main()
