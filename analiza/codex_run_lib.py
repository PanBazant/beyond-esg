"""Logika runu 2 (Codex via OpenClaw) — importowana przez 13_* i testy."""
from __future__ import annotations

import json
import random
from collections import defaultdict


def select_stratified_sample(run1_rows: list[dict], target_n: int = 90, seed: int = 42) -> list[str]:
    """Warstwowy dobór ~target_n symboli z runu 1.

    Warstwy = category; w obrębie warstwy mieszamy coverage. Pomija wiersze error.
    Deterministyczne przy stałym seed. Zwraca posortowaną listę symboli.
    """
    rng = random.Random(seed)
    by_cat: dict[str, list[str]] = defaultdict(list)
    for row in run1_rows:
        if row.get("error"):
            continue
        if row.get("axiological_coverage") == "error":
            continue
        symbol = row.get("symbol")
        if not symbol:
            continue
        by_cat[row.get("category") or "Unknown"].append(symbol)

    if not by_cat:
        return []

    # przetasuj w każdej warstwie deterministycznie
    for cat in by_cat:
        by_cat[cat].sort()
        rng.shuffle(by_cat[cat])

    total = sum(len(v) for v in by_cat.values())
    target_n = min(target_n, total)

    # round-robin po warstwach aż zbierzemy target_n
    selected: list[str] = []
    cats = sorted(by_cat.keys())
    idx = {cat: 0 for cat in cats}
    while len(selected) < target_n:
        progressed = False
        for cat in cats:
            if len(selected) >= target_n:
                break
            i = idx[cat]
            if i < len(by_cat[cat]):
                selected.append(by_cat[cat][i])
                idx[cat] = i + 1
                progressed = True
        if not progressed:
            break

    return sorted(selected)
