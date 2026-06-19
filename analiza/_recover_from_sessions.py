"""Odzysk runu 2 (Codex) z historii sesji OpenClaw.

Cały dialog (prompty + odpowiedzi JSON) wpadł do jednej sesji agent:profiler:main
(izolacja per --session-id nie zadziałała). Tu wyłuskujemy z plików sesji + checkpointów
sparowane user->assistant (po parentId), parsujemy profil aksjologiczny i odtwarzamy
wiersze identyczne ze schematem 13_profile_via_codex.py — BEZ nowych wywołań Codexa.

Użycie: python3 _recover_from_sessions.py <sessions_dir> <out_jsonl>
"""
import json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from llm_profiling_lib import validate_llm_result

SESS_DIR = Path(sys.argv[1])
OUT = Path(sys.argv[2])

COMPANY_RE = re.compile(r"Company:\s*(\S+)\s*\|\s*Category:\s*(.*?)\s*\|\s*Industry:\s*(.*?)\s*\n", re.S)
TOTAL_RE = re.compile(r"Total posts collected:\s*(\d+)")


def msg_text(d):
    """Sklej tekst z content[] wiadomości."""
    msg = d.get("message")
    if not isinstance(msg, dict):
        return ""
    content = msg.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict) and c.get("type") == "text" and c.get("text"):
                parts.append(c["text"])
            elif isinstance(c, str):
                parts.append(c)
        return "\n".join(parts)
    return ""


def extract_json(text):
    """Wyłuskaj {...} profilu z tekstu asystenta."""
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        return None
    blob = text[start:end]
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        # spróbuj raw_decode od pierwszego {
        try:
            obj, _ = json.JSONDecoder().raw_decode(text[start:])
            return obj
        except json.JSONDecodeError:
            return None


# pliki sesji posortowane po mtime (starsze pierwsze -> nowsze nadpisują)
files = sorted(SESS_DIR.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
print(f"Plików sesji: {len(files)}")

# id_użytkownika -> meta z promptu
user_meta = {}
# symbol -> wiersz (ostatni wygrywa)
recovered = {}
seen_user = 0
seen_asst = 0

for fp in files:
    with fp.open(encoding="utf-8") as f:
        # pierwsze przejście pliku: zbierz user meta
        lines = [l for l in f if l.strip()]
    # pass 1: users
    for l in lines:
        try:
            d = json.loads(l)
        except json.JSONDecodeError:
            continue
        if d.get("type") != "message":
            continue
        msg = d.get("message") or {}
        if msg.get("role") != "user":
            continue
        txt = msg_text(d)
        m = COMPANY_RE.search(txt)
        if not m:
            continue
        seen_user += 1
        symbol = m.group(1).strip()
        category = m.group(2).strip()
        industry = m.group(3).strip()
        tm = TOTAL_RE.search(txt)
        total = int(tm.group(1)) if tm else None
        user_meta[d.get("id")] = {
            "symbol": symbol, "category": category,
            "industry": industry, "post_count": total,
        }
    # pass 2: assistants paired by parentId
    for l in lines:
        try:
            d = json.loads(l)
        except json.JSONDecodeError:
            continue
        if d.get("type") != "message":
            continue
        msg = d.get("message") or {}
        if msg.get("role") != "assistant":
            continue
        meta = user_meta.get(d.get("parentId"))
        if not meta:
            continue
        parsed = extract_json(msg_text(d))
        if parsed is None or not isinstance(parsed, dict):
            continue
        if "axiological_coverage" not in parsed and "frames" not in parsed:
            continue
        seen_asst += 1
        validated = validate_llm_result(parsed)
        recovered[meta["symbol"]] = {
            "symbol": meta["symbol"],
            "category": meta["category"],
            "industry": meta["industry"],
            "post_count": meta["post_count"],
            **validated,
            "error": False,
            "_recovered": True,
        }

print(f"Sparowanych user-promptów: {seen_user}, odpowiedzi z JSON: {seen_asst}")
print(f"Unikalnych odzyskanych spółek: {len(recovered)}")

with OUT.open("w", encoding="utf-8") as f:
    for sym in sorted(recovered):
        f.write(json.dumps(recovered[sym], ensure_ascii=False) + "\n")
print(f"Zapisano -> {OUT}")

# krótka diagnostyka pokrycia
from collections import Counter
cov = Counter(r["axiological_coverage"] for r in recovered.values())
print("Rozkład coverage:", dict(cov))
