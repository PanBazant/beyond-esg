"""Pobiera fundamenty (5 wskaznikow) i technikalia (z historii cen) z Yahoo Finance
przez yfinance (bez klucza API) i zapisuje company_fundamentals.csv + company_technicals.csv
w formacie, ktory czytaja 04_build_profitability_features.py i 07_build_technical_features.py.

Przyklady:
  python analiza/16_fetch_yfinance_financials.py --symbols PM,KO,MMM,TMO,TSM,WM,CRH,SAP,CSCO,MCD
  python analiza/16_fetch_yfinance_financials.py --from-master --limit 100 --sleep 0.8
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import time
from datetime import date
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
INPUT_DIR = ROOT_DIR / "analiza" / "input"
OUT_DIR = ROOT_DIR / "analiza" / "out"
MASTER_PATH = OUT_DIR / "company_master_dataset.jsonl"
FUNDAMENTALS_CSV = INPUT_DIR / "company_fundamentals.csv"
TECHNICALS_CSV = INPUT_DIR / "company_technicals.csv"

FUND_FIELDS = ["symbol", "company_name", "category", "industry",
               "net_margin", "operating_margin", "roe", "roa", "revenue_growth",
               "source", "as_of_date"]
TECH_FIELDS = ["symbol", "company_name", "category", "industry",
               "momentum_30d", "momentum_90d", "volatility_30d", "drawdown_90d",
               "source", "as_of_date"]

# mapowanie sufiksow z naszego universe na konwencje yfinance
_SUFFIX_MAP = {".NSE": ".NS", ".TSX": ".TO", ".AX": ".AX"}
_TRY_SUFFIXES = [".US", ".TO", ".L", ".DE", ".PA", ".AS", ".MC", ".MI", ".SW", ".HK", ".AX", ".NS"]


def _candidates(symbol: str) -> list[str]:
    cands = [symbol]
    for raw, mapped in _SUFFIX_MAP.items():
        if symbol.endswith(raw):
            base = symbol[: -len(raw)]
            cands.insert(0, base + mapped)
            cands.append(base)
    return list(dict.fromkeys(cands))


def _resolve(yf, symbol: str, period: str):
    for cand in _candidates(symbol):
        try:
            t = yf.Ticker(cand)
            hist = t.history(period=period, auto_adjust=True)
            if not hist.empty:
                return t, hist, cand
        except Exception:
            continue
    try:
        for quote in yf.Search(symbol).quotes[:3]:
            cand = quote.get("symbol", "")
            if not cand:
                continue
            t = yf.Ticker(cand)
            hist = t.history(period=period, auto_adjust=True)
            if not hist.empty:
                return t, hist, cand
    except Exception:
        pass
    return None, None, None


def _technicals(closes: list[float]) -> dict:
    out = {"momentum_30d": None, "momentum_90d": None, "volatility_30d": None, "drawdown_90d": None}
    if len(closes) >= 31 and closes[-31]:
        out["momentum_30d"] = round(closes[-1] / closes[-31] - 1, 6)
    if len(closes) >= 91 and closes[-91]:
        out["momentum_90d"] = round(closes[-1] / closes[-91] - 1, 6)
    rets = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes)) if closes[i - 1]]
    if len(rets) >= 30:
        window = rets[-30:]
        mean = sum(window) / len(window)
        var = sum((x - mean) ** 2 for x in window) / len(window)
        out["volatility_30d"] = round(var ** 0.5, 6)
    window = closes[-90:] if len(closes) >= 90 else closes
    if window:
        peak = window[0]
        max_dd = 0.0
        for c in window:
            peak = max(peak, c)
            if peak:
                max_dd = max(max_dd, 1 - c / peak)
        out["drawdown_90d"] = round(max_dd, 6)
    return out


def _fundamentals(info: dict) -> dict:
    def f(key):
        v = info.get(key)
        try:
            return round(float(v), 6) if v is not None else None
        except (TypeError, ValueError):
            return None
    return {
        "net_margin": f("profitMargins"),
        "operating_margin": f("operatingMargins"),
        "roe": f("returnOnEquity"),
        "roa": f("returnOnAssets"),
        "revenue_growth": f("revenueGrowth"),
    }


def _load_existing(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return {r["symbol"]: r for r in csv.DictReader(fh) if r.get("symbol")}


def _write(path: Path, fields: list[str], rows: dict[str, dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for sym in sorted(rows):
            w.writerow({k: rows[sym].get(k, "") for k in fields})


def _symbols_from_master(limit: int | None) -> list[dict]:
    out = []
    with MASTER_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            out.append({"symbol": row.get("symbol"), "company_name": row.get("company_name"),
                        "category": row.get("category"), "industry": row.get("industry")})
            if limit and len(out) >= limit:
                break
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", type=str, default="")
    ap.add_argument("--from-master", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--period", type=str, default="1y")
    ap.add_argument("--sleep", type=float, default=0.6)
    ap.add_argument("--resume", action="store_true", help="pomin symbole juz obecne w obu CSV")
    args = ap.parse_args()

    import yfinance as yf

    if args.symbols:
        targets = [{"symbol": s.strip().upper(), "company_name": s.strip().upper(),
                    "category": "", "industry": ""} for s in args.symbols.split(",") if s.strip()]
    elif args.from_master:
        targets = _symbols_from_master(args.limit)
    else:
        targets = [{"symbol": s, "company_name": s, "category": "", "industry": ""}
                   for s in ["PM", "KO", "MMM", "TMO", "TSM", "WM", "CRH", "SAP", "CSCO", "MCD"]]

    fund_rows = _load_existing(FUNDAMENTALS_CSV)
    tech_rows = _load_existing(TECHNICALS_CSV)
    today = date.today().isoformat()
    stats = {"ok_price": 0, "ok_fund_any": 0, "unresolved": 0, "total": len(targets)}

    processed = 0
    for i, tgt in enumerate(targets, 1):
        sym = tgt["symbol"]
        if args.resume and sym in fund_rows and sym in tech_rows:
            stats["skipped"] = stats.get("skipped", 0) + 1
            continue
        t, hist, actual = _resolve(yf, sym, args.period)
        if t is None:
            stats["unresolved"] += 1
            print(f"[{i}/{stats['total']}] {sym}: BRAK danych cenowych")
            time.sleep(args.sleep)
            continue
        closes = [v for v in (float(c) for c in hist["Close"].tolist() if c is not None) if v == v]
        tech = _technicals(closes)
        try:
            info = t.info or {}
        except Exception:
            info = {}
        fund = _fundamentals(info)
        name = tgt.get("company_name") or info.get("shortName") or sym
        base = {"symbol": sym, "company_name": name, "category": tgt.get("category", ""),
                "industry": tgt.get("industry") or info.get("industry") or "",
                "source": f"yfinance:{actual}", "as_of_date": today}
        tech_rows[sym] = {**base, **{k: ("" if v is None else v) for k, v in tech.items()}}
        fund_rows[sym] = {**base, **{k: ("" if v is None else v) for k, v in fund.items()}}
        stats["ok_price"] += 1
        if any(v is not None for v in fund.values()):
            stats["ok_fund_any"] += 1
        got_f = sum(v is not None for v in fund.values())
        print(f"[{i}/{stats['total']}] {sym} -> {actual} | tech ok | fund {got_f}/5", flush=True)
        processed += 1
        if processed % 25 == 0:  # checkpoint, zeby dlugi run nie tracil postepu
            _write(FUNDAMENTALS_CSV, FUND_FIELDS, fund_rows)
            _write(TECHNICALS_CSV, TECH_FIELDS, tech_rows)
        time.sleep(args.sleep)

    _write(FUNDAMENTALS_CSV, FUND_FIELDS, fund_rows)
    _write(TECHNICALS_CSV, TECH_FIELDS, tech_rows)
    print("\n=== PODSUMOWANIE ===")
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    print(f"zapisano: {FUNDAMENTALS_CSV.name} ({len(fund_rows)} wierszy), {TECHNICALS_CSV.name} ({len(tech_rows)} wierszy)")


if __name__ == "__main__":
    main()
