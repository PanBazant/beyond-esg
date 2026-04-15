"""10a_filter_value_frames.py

Trzy równoległe filtry postów dla ekstrakcji aksjologicznej:
  A: seed-word matching
  B: brak filtrowania (passthrough z adnotacją)
  C: embedding cosine similarity

Uruchomienie:
  python 10a_filter_value_frames.py
  python 10a_filter_value_frames.py --sample
  python 10a_filter_value_frames.py --embed-threshold 0.28 --embed-model all-mpnet-base-v2
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT_DIR / "analiza" / "out"
POSTS_FLAT_PATH = OUT_DIR / "posts_flat.jsonl"
POSTS_FLAT_SAMPLE_PATH = OUT_DIR / "posts_flat_sample.jsonl"

SEED_OUT_PATH = OUT_DIR / "posts_valueframed_seed.jsonl"
EMBED_OUT_PATH = OUT_DIR / "posts_valueframed_embed.jsonl"
SEED_SAMPLE_OUT_PATH = OUT_DIR / "posts_valueframed_seed_sample.jsonl"
EMBED_SAMPLE_OUT_PATH = OUT_DIR / "posts_valueframed_embed_sample.jsonl"
FILTER_SUMMARY_PATH = OUT_DIR / "filter_summary.json"

sys.path.insert(0, str(ROOT_DIR / "analiza"))
from filter_value_frames_lib import (
    AXIOLOGICAL_CONCEPT,
    build_concept_embedding,
    filter_embedding_batch,
    filter_seed,
)


def load_posts(path: Path, limit: int | None = None) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
            if limit and len(rows) >= limit:
                break
    return rows


def run_seed_filter(posts: list[dict], out_path: Path) -> dict:
    passed = 0
    with out_path.open("w", encoding="utf-8") as f:
        for post in posts:
            text = str(post.get("text") or "")
            matched, tokens = filter_seed(text)
            row = {**post, "filter_seed": matched, "filter_seed_tokens": tokens}
            if matched:
                passed += 1
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {"total": len(posts), "passed": passed, "coverage": round(passed / len(posts), 4) if posts else 0.0}


def run_embed_filter(posts: list[dict], out_path: Path, model, concept_emb, threshold: float) -> dict:
    texts = [str(p.get("text") or "") for p in posts]
    results, scores = filter_embedding_batch(texts, model, concept_emb, threshold=threshold)
    passed = 0
    with out_path.open("w", encoding="utf-8") as f:
        for post, result, score in zip(posts, results, scores):
            row = {**post, "filter_embed": result, "filter_embed_score": round(score, 4)}
            if result:
                passed += 1
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {"total": len(posts), "passed": passed, "coverage": round(passed / len(posts), 4) if posts else 0.0, "threshold": threshold}


def main() -> None:
    parser = argparse.ArgumentParser(description="Trzy filtry postów aksjologicznych")
    parser.add_argument("--sample", action="store_true", help="Tryb sample")
    parser.add_argument("--input-file", type=str, default=None)
    parser.add_argument("--embed-threshold", type=float, default=0.28,
                        help="Próg cosine similarity dla filtra C (default: 0.28)")
    parser.add_argument("--embed-model", type=str, default="all-mpnet-base-v2",
                        help="Model sentence-transformers dla filtra C")
    parser.add_argument("--skip-embed", action="store_true",
                        help="Pomiń filtr C (szybsze uruchomienie)")
    args = parser.parse_args()

    posts_path = (
        Path(args.input_file) if args.input_file
        else (POSTS_FLAT_SAMPLE_PATH if args.sample else POSTS_FLAT_PATH)
    )
    seed_out = SEED_SAMPLE_OUT_PATH if args.sample else SEED_OUT_PATH
    embed_out = EMBED_SAMPLE_OUT_PATH if args.sample else EMBED_OUT_PATH

    if not posts_path.exists():
        print(f"ERROR: Plik wejściowy nie istnieje: {posts_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Ładowanie postów z: {posts_path}")
    posts = load_posts(posts_path)
    print(f"Załadowano {len(posts)} postów")

    # Filtr A
    print("\n=== Filtr A: seed-word ===")
    seed_stats = run_seed_filter(posts, seed_out)
    print(f"Przeszło: {seed_stats['passed']}/{seed_stats['total']} ({seed_stats['coverage']*100:.1f}%)")
    print(f"Zapisano: {seed_out}")

    embed_stats = None
    if not args.skip_embed:
        # Filtr C
        print(f"\n=== Filtr C: embedding (model={args.embed_model}, threshold={args.embed_threshold}) ===")
        from sentence_transformers import SentenceTransformer
        print("Ładowanie modelu embedding...")
        model = SentenceTransformer(args.embed_model)
        concept_emb = build_concept_embedding(model)
        embed_stats = run_embed_filter(posts, embed_out, model, concept_emb, args.embed_threshold)
        print(f"Przeszło: {embed_stats['passed']}/{embed_stats['total']} ({embed_stats['coverage']*100:.1f}%)")
        print(f"Zapisano: {embed_out}")

    # Filtr B jest posts_flat.jsonl bez zmian — oznaczony w summary
    summary = {
        "input_file": str(posts_path),
        "total_posts": len(posts),
        "filter_a_seed": seed_stats,
        "filter_b_nofilter": {"total": len(posts), "passed": len(posts), "coverage": 1.0, "note": "passthrough - używa posts_flat.jsonl bezpośrednio"},
        "filter_c_embed": embed_stats,
        "embed_concept": AXIOLOGICAL_CONCEPT,
    }
    FILTER_SUMMARY_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSummary zapisano: {FILTER_SUMMARY_PATH}")


if __name__ == "__main__":
    main()
