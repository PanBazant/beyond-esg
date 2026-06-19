"""Logika runu 2 (Codex via OpenClaw) — importowana przez 13_* i testy."""
from __future__ import annotations

import json
import random
import re
import subprocess
import sys
import time
from collections import defaultdict

# Znaki kontrolne C0 (poza \t i \n) psują argv subprocess na Windows
# (CreateProcess odrzuca embedded null) — niektóre posty zawierają \x00.
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
# Backtick w --message bywa interpretowany przez powłokę w WSL → `bash: unexpected
# EOF` i call pada. Posty bywają w markdownie z backtickami; usuwamy je z promptu.
_SHELL_BREAK_RE = re.compile(r"`")


def sanitize_prompt(prompt: str) -> str:
    """Usuwa znaki, które psują przekazanie promptu przez subprocess->wsl->powłoka."""
    return _SHELL_BREAK_RE.sub("'", _CTRL_RE.sub("", prompt))

OPENCLAW_BIN = "/home/macie/.npm-global/bin/openclaw"
WSL_DISTRO = "Ubuntu-24.04"
# Katalog stanu sesji agenta (parametryzowany po nazwie agenta). Czyszczony przed
# każdym wywołaniem, by wymusić izolację spółek (patrz build_wipe_cmd).
SESSIONS_DIR_TMPL = "/home/macie/.openclaw/agents/{agent}/sessions"


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
    if not isinstance(stdout, str):
        return None
    try:
        envelope = json.loads(stdout)
    except json.JSONDecodeError:
        # stdout bywa poprzedzony szumem (np. ostrzeżenia gatewaya) — dekoduj od pierwszego {
        start = stdout.find("{")
        if start == -1:
            return None
        try:
            envelope, _ = json.JSONDecoder().raw_decode(stdout[start:])
        except json.JSONDecodeError:
            return None
    if not isinstance(envelope, dict):
        return None
    # struktura zależy od ścieżki OpenClaw: gateway zawija w "result",
    # embedded fallback zwraca płaskie "payloads".
    payloads = None
    result = envelope.get("result")
    if isinstance(result, dict):
        payloads = result.get("payloads")
    if payloads is None:
        payloads = envelope.get("payloads")
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


def build_wipe_cmd(agent: str = "profiler", distro: str = WSL_DISTRO) -> list[str]:
    """argv: kasuje stan sesji agenta w WSL, wymuszając świeżą sesję na następnym callu.

    Konieczne do izolacji: `--agent X` wymusza klucz `agent:X:main`, więc wszystkie
    spółki lądują w jednej sesji (--session-id jest ignorowane). Czyszczenie katalogu
    sesji przed callem sprawia, że embedded run startuje bez historii innych spółek.
    """
    sess = SESSIONS_DIR_TMPL.format(agent=agent)
    return [
        "wsl", "-d", distro, "bash", "-lc",
        f"rm -f {sess}/*.jsonl {sess}/sessions.json",
    ]


def build_openclaw_cmd(symbol: str, prompt: str, agent: str = "profiler",
                       distro: str = WSL_DISTRO, openclaw_bin: str = OPENCLAW_BIN,
                       timeout_s: int = 300, thinking: str = "low") -> list[str]:
    """Lista argv dla subprocess: wsl -> openclaw agent ... --json.

    Izolację spółek daje wcześniejszy build_wipe_cmd (nie --session-id — był ignorowany
    przy podanym --agent). `--thinking` pinujemy jawnie, bo wipe kasuje ustawiony
    thinkingLevel sesji; bez tego effort wróciłby do domyślnego.
    """
    safe_prompt = sanitize_prompt(prompt)
    return [
        "wsl", "-d", distro, openclaw_bin, "agent",
        "--agent", agent,
        "--thinking", thinking,
        "--message", safe_prompt,
        "--json",
        "--timeout", str(timeout_s),
    ]


def call_codex(symbol: str, prompt: str, agent: str = "profiler", thinking: str = "low",
               retries: int = 2) -> dict | None:
    """Jedno profilowanie spółki przez Codex/OpenClaw z izolacją sesji.

    Przed każdą próbą kasuje stan sesji agenta (build_wipe_cmd) → świeży kontekst,
    spółka nie widzi poprzednich. Zwraca sparsowany profil albo None po wyczerpaniu prób.
    """
    cmd = build_openclaw_cmd(symbol, prompt, agent=agent, thinking=thinking)
    wipe_cmd = build_wipe_cmd(agent=agent)
    for attempt in range(retries + 1):
        try:
            subprocess.run(wipe_cmd, capture_output=True, text=True,
                           encoding="utf-8", timeout=30)
        except subprocess.TimeoutExpired:
            pass
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  encoding="utf-8", timeout=360)
        except subprocess.TimeoutExpired:
            print(f"  timeout (attempt {attempt+1})", file=sys.stderr)
            continue
        if proc.returncode != 0:
            print(f"  exit {proc.returncode}: {proc.stderr[:200]}", file=sys.stderr)
            time.sleep(2)
            continue
        parsed = parse_openclaw_response(proc.stdout)
        if parsed is not None:
            return parsed
        print(f"  unparsable response (attempt {attempt+1})", file=sys.stderr)
        time.sleep(1)
    return None
