from __future__ import annotations

import math


def _safe(v: object, decimals: int = 4) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, decimals)


def _rolling_mean(values: list[float], period: int) -> list[float | None]:
    result: list[float | None] = []
    for i in range(len(values)):
        if i < period - 1:
            result.append(None)
        else:
            result.append(sum(values[i - period + 1 : i + 1]) / period)
    return result


def _ema(values: list[float], period: int) -> list[float]:
    k = 2.0 / (period + 1)
    result: list[float] = []
    for i, v in enumerate(values):
        result.append(v if i == 0 else v * k + result[-1] * (1 - k))
    return result


def _rsi(closes: list[float], period: int = 14) -> list[float | None]:
    result: list[float | None] = [None] * len(closes)
    if len(closes) <= period:
        return result

    gains = [max(closes[i] - closes[i - 1], 0.0) for i in range(1, len(closes))]
    losses = [max(closes[i - 1] - closes[i], 0.0) for i in range(1, len(closes))]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(closes)):
        if avg_loss == 0:
            result[i] = 100.0
        else:
            result[i] = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
        if i < len(closes) - 1:
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    return result


def _macd_series(
    closes: list[float], fast: int = 12, slow: int = 26, signal_period: int = 9
) -> list[dict | None]:
    if len(closes) < slow:
        return [None] * len(closes)

    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = _ema(macd_line, signal_period)

    result: list[dict | None] = []
    for i, (m, sig) in enumerate(zip(macd_line, signal_line)):
        if i < slow - 1:
            result.append(None)
        else:
            result.append({"macd": m, "signal": sig, "hist": m - sig})
    return result


_EXCHANGE_SUFFIXES = [".WA", ".L", ".DE", ".PA", ".AS", ".MC", ".MI", ".SW", ".HK", ".AX", ".TO"]


def _resolve_ticker(yf: object, symbol: str, period: str):
    """Try symbol directly, then with exchange suffixes, then via Search.
    Returns (ticker, hist, actual_symbol) or raises ValueError."""
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period=period, auto_adjust=True)
    if not hist.empty:
        return ticker, hist, symbol

    # Try common exchange suffixes
    for suffix in _EXCHANGE_SUFFIXES:
        candidate = symbol + suffix
        t = yf.Ticker(candidate)
        h = t.history(period=period, auto_adjust=True)
        if not h.empty:
            return t, h, candidate

    # Last resort: yfinance Search
    try:
        results = yf.Search(symbol).quotes
        for quote in results[:3]:
            candidate = quote.get("symbol", "")
            if not candidate or candidate == symbol:
                continue
            t = yf.Ticker(candidate)
            h = t.history(period=period, auto_adjust=True)
            if not h.empty:
                return t, h, candidate
    except Exception:
        pass

    raise ValueError(f"No price data for symbol: {symbol!r}")


def fetch_market_data(symbol: str, period: str = "1y") -> dict:
    try:
        import yfinance as yf
    except ImportError as e:
        raise RuntimeError("yfinance is not installed") from e

    ticker, hist, actual_symbol = _resolve_ticker(yf, symbol, period)

    timestamps = [int(dt.timestamp()) for dt in hist.index]
    closes = hist["Close"].tolist()

    candles = [
        {
            "t": ts,
            "o": _safe(row.Open),
            "h": _safe(row.High),
            "l": _safe(row.Low),
            "c": _safe(row.Close),
            "v": int(row.Volume) if row.Volume else 0,
        }
        for ts, row in zip(timestamps, hist.itertuples())
    ]

    ma20 = _rolling_mean(closes, 20)
    ma50 = _rolling_mean(closes, 50)
    ma200 = _rolling_mean(closes, 200)
    rsi_vals = _rsi(closes)
    macd_vals = _macd_series(closes)

    def line_series(values: list) -> list[dict]:
        return [
            {"t": t, "v": _safe(v)}
            for t, v in zip(timestamps, values)
            if v is not None
        ]

    def macd_series_out(values: list) -> list[dict]:
        out = []
        for t, v in zip(timestamps, values):
            if v is None:
                continue
            out.append({
                "t": t,
                "macd": _safe(v["macd"], 6),
                "signal": _safe(v["signal"], 6),
                "hist": _safe(v["hist"], 6),
            })
        return out

    try:
        info = ticker.info or {}
    except Exception:
        info = {}

    def g(key: str) -> float | None:
        return _safe(info.get(key))

    fundamentals = {
        "pe": g("trailingPE"),
        "pb": g("priceToBook"),
        "roe": g("returnOnEquity"),
        "debt_equity": g("debtToEquity"),
        "revenue": g("totalRevenue"),
        "net_income": g("netIncomeToCommon"),
        "market_cap": g("marketCap"),
        "dividend_yield": g("dividendYield"),
        "eps": g("trailingEps"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
    }

    esg = None
    try:
        sust = ticker.sustainability
        if sust is not None and not sust.empty:
            def sv(key: str) -> float | None:
                try:
                    return _safe(float(sust.loc[key, "Value"]))
                except Exception:
                    return None

            esg = {
                "total": sv("totalEsg"),
                "env": sv("environmentScore"),
                "social": sv("socialScore"),
                "governance": sv("governanceScore"),
                "controversy": sv("highestControversy"),
            }
    except Exception:
        esg = None

    return {
        "symbol": symbol,
        "actual_symbol": actual_symbol,
        "period": period,
        "candles": candles,
        "indicators": {
            "ma20": line_series(ma20),
            "ma50": line_series(ma50),
            "ma200": line_series(ma200),
            "rsi": line_series(rsi_vals),
            "macd": macd_series_out(macd_vals),
        },
        "fundamentals": fundamentals,
        "esg": esg,
    }
