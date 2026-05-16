"""Logika fuzji wyników BERTopic + LLM — importowana przez 11 i testy."""
from __future__ import annotations
import math


SENTIMENT_SCORE_MAP: dict[str, float] = {
    "positive": 1.0,
    "negative": -1.0,
    "mixed": 0.0,
    "neutral": 0.0,
}


def sentiment_to_score(sentiment: str) -> float:
    """Mapuje etykietę sentymentu na liczbę: positive→+1, negative→-1, reszta→0."""
    return SENTIMENT_SCORE_MAP.get(sentiment, 0.0)


def compute_inter_method_agreement(methods: dict[str, dict]) -> float:
    """Oblicza stopień zgodności między metodami (0.0–1.0).

    methods: {"bertopic_seed": {...}, "bertopic_nofilter": {...}, "llm": {...}}
    Prosta metryka: ile metod ma niezerowy sygnał / ile metod ogółem.
    """
    active = 0
    total = len(methods)
    if total == 0:
        return 0.0

    for name, data in methods.items():
        if name == "llm":
            if data.get("frames"):
                active += 1
        else:
            if data.get("topic_exposure"):
                active += 1

    return round(active / total, 4)


def compute_axiological_confidence(
    coverage: float,
    post_count: int,
    method_count: int,
) -> float:
    """Oblicza confidence profilu aksjologicznego.

    coverage: axiological_coverage (0.0–1.0)
    post_count: liczba postów spółki
    method_count: ile metod dało niezerowy sygnał (0–3)

    Formuła: sigmoid-like normalizacja na coverage × log(posts) × method_weight
    """
    if post_count == 0 or coverage == 0.0:
        return 0.0

    post_factor = min(math.log10(max(post_count, 1)) / 2.0, 1.0)  # log10(100)=2 → 1.0
    method_factor = method_count / 3.0
    raw = coverage * post_factor * (0.4 + 0.6 * method_factor)
    return round(min(raw, 1.0), 4)


def merge_frames(frames: list[dict]) -> list[dict]:
    """Deduplikuje frames po identycznej etykiecie (case-insensitive).

    Zachowuje pierwsze wystąpienie każdej etykiety.
    """
    seen: set[str] = set()
    merged: list[dict] = []
    for frame in frames:
        label = str(frame.get("label") or "").strip().lower()
        if label and label not in seen:
            seen.add(label)
            merged.append(frame)
    return merged
