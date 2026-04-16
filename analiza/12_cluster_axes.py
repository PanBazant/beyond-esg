from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import silhouette_score

ROOT_DIR = Path(__file__).resolve().parents[1]
SUMMARY_PATH = ROOT_DIR / "analiza" / "out" / "comment_esg_axes_summary.json"


def _axis_document(axis: dict) -> str:
    parts = list(axis.get("keywords", [])) + list(axis.get("examples", []))[:3]
    return " ".join(str(p) for p in parts if p)


def _cluster_label(vectorizer: TfidfVectorizer, center: np.ndarray, top_n: int = 3) -> str:
    feature_names = vectorizer.get_feature_names_out()
    top_indices = center.argsort()[::-1][:top_n]
    return " / ".join(feature_names[i] for i in top_indices)


def cluster_axes(axes: list[dict], k_range: range = range(6, 13)) -> list[dict]:
    if len(axes) < 6:
        for i, axis in enumerate(axes):
            axis["cluster_id"] = 0
            axis["cluster_label"] = "ogólne"
        return axes

    docs = [_axis_document(ax) for ax in axes]
    vectorizer = TfidfVectorizer(max_features=200, min_df=1, stop_words="english")
    X = vectorizer.fit_transform(docs).toarray()

    best_k, best_score, best_labels = k_range.start, -1.0, None
    for k in k_range:
        if k >= len(axes):
            break
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = km.fit_predict(X)
        score = silhouette_score(X, labels)
        if not np.isnan(score) and score > best_score:
            best_k, best_score, best_labels = k, score, labels

    km_final = KMeans(n_clusters=best_k, random_state=42, n_init=10)
    km_final.fit(X)
    centers = km_final.cluster_centers_

    cluster_labels = {i: _cluster_label(vectorizer, centers[i]) for i in range(best_k)}
    print(f"Best k={best_k}, silhouette={best_score:.3f}", file=sys.stderr)
    for i, label in cluster_labels.items():
        print(f"  Cluster {i}: {label}", file=sys.stderr)

    for axis, label_id in zip(axes, best_labels):
        axis["cluster_id"] = int(label_id)
        axis["cluster_label"] = cluster_labels[int(label_id)]

    return axes


def main() -> None:
    doc = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    axes = doc.get("axes", [])
    if not axes:
        print("No axes found in summary JSON", file=sys.stderr)
        sys.exit(1)

    axes = cluster_axes(axes)
    doc["axes"] = axes
    SUMMARY_PATH.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Written cluster_id/cluster_label to {len(axes)} axes in {SUMMARY_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
