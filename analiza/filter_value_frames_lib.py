"""Logika filtrowania postów — importowana przez 10a i testy."""
from __future__ import annotations

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
