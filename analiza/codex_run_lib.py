"""Logika runu 2 (Codex via OpenClaw) — importowana przez 13_* i testy."""
from __future__ import annotations

import json
import random
from collections import defaultdict

OPENCLAW_BIN = "/home/macie/.npm-global/bin/openclaw"
WSL_DISTRO = "Ubuntu-24.04"


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


def parse_openclaw_response(stdout: str) -> dict | None:
    """Z surowego stdout `openclaw agent --json` wyciąga JSON profilu aksjologicznego.

    Ścieżka: stdout(JSON) -> result.payloads[0].text -> wyłuskanie {...} -> json.loads.
    Zwraca dict profilu (frames/axiological_coverage/notes) albo None przy każdym błędzie.
    """
    try:
        envelope = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return None
    try:
        payloads = envelope["result"]["payloads"]
    except (KeyError, TypeError):
        return None
    if not payloads:
        return None
    text = payloads[0].get("text")
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        return None
    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError:
        return None


def build_openclaw_cmd(symbol: str, prompt: str, agent: str = "profiler",
                       distro: str = WSL_DISTRO, openclaw_bin: str = OPENCLAW_BIN,
                       timeout_s: int = 300) -> list[str]:
    """Lista argv dla subprocess: wsl -> openclaw agent ... --json.

    Unikatowy --session-id codex-<SYMBOL> izoluje kontekst każdej spółki.
    """
    return [
        "wsl", "-d", distro, openclaw_bin, "agent",
        "--agent", agent,
        "--session-id", f"codex-{symbol}",
        "--message", prompt,
        "--json",
        "--timeout", str(timeout_s),
    ]
