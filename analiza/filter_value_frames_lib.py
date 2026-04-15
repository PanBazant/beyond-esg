"""Logika filtrowania postów — importowana przez 10a i testy."""
from __future__ import annotations

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

SEED_WORDS: frozenset[str] = frozenset({
    # Zarządzanie i ład
    "management", "board", "ceo", "cfo", "coo", "insider", "insiders",
    "accountability", "transparency", "corrupt", "dilut", "restructur",
    "activist", "proxy", "shareholder",
    # Praca i społeczeństwo
    "workers", "employees", "employee", "labor", "community", "harm",
    "exploit", "rights", "fair", "trust", "union", "strike", "layoff",
    # Środowisko i zasoby
    "emissions", "carbon", "footprint", "renewable", "clean", "waste",
    "pollut", "sustainab", "climate", "fossil",
    # Etyka produktu i praktyki
    "scam", "fraud", "mislead", "predatory", "ethics", "ethical",
    "responsible", "integrity", "misconduct", "manipulat",
    # Regulacje i prawo
    "lawsuit", "investigation", "settlement", "regulatory", "compliance",
    "fine", "sec", "probe", "litigation", "claims",
    # Narracje wpływu
    "impact", "society", "social", "governance", "esg",
})


def filter_seed(text: str) -> tuple[bool, list[str]]:
    """Zwraca (czy_przeszedł_filtr, lista_dopasowanych_tokenów_seed).

    Dopasowanie przez prefix: token 'diluting' pasuje do seed 'dilut'.
    """
    if not text or not text.strip():
        return False, []

    lower = text.lower()
    tokens = lower.split()
    matched: list[str] = []
    for seed in SEED_WORDS:
        if any(t.startswith(seed) for t in tokens):
            matched.append(seed)
    return bool(matched), matched


AXIOLOGICAL_CONCEPT = (
    "company values ethics practices governance accountability "
    "social impact labor rights environmental footprint regulatory risk "
    "management integrity community"
)


def build_concept_embedding(model) -> np.ndarray:
    """Zwraca embedding wektora konceptu aksjologicznego."""
    return model.encode([AXIOLOGICAL_CONCEPT])[0]


def filter_embedding_batch(
    texts: list[str],
    model,
    concept_embedding: np.ndarray,
    threshold: float = 0.30,
) -> tuple[list[bool], list[float]]:
    """Filtruje posty przez cosine similarity do konceptu aksjologicznego.

    Zwraca (lista_bool_czy_przeszedł, lista_float_scores).
    Puste posty zawsze odrzucane (score=0.0).
    """
    if not texts:
        return [], []

    results: list[bool] = []
    scores: list[float] = []

    non_empty = [(i, t) for i, t in enumerate(texts) if t and t.strip()]
    if not non_empty:
        return [False] * len(texts), [0.0] * len(texts)

    indices, valid_texts = zip(*non_empty)
    embeddings = model.encode(list(valid_texts), batch_size=64, show_progress_bar=False)
    sims = cosine_similarity(embeddings, concept_embedding.reshape(1, -1)).flatten()

    score_map = {idx: float(sim) for idx, sim in zip(indices, sims)}
    for i in range(len(texts)):
        score = score_map.get(i, 0.0)
        scores.append(score)
        results.append(score >= threshold)

    return results, scores
