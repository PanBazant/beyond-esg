import { useEffect, useRef, useState } from "react";
import { createChart, CrosshairMode } from "lightweight-charts";
import { fetchMarketData } from "./api";

const PERIODS = ["1mo", "3mo", "6mo", "1y", "2y", "5y"];
const MA_COLORS = { ma20: "#e8a838", ma50: "#3b82f6", ma200: "#a855f7" };

const CHART_OPTS = {
  layout: { background: { color: "transparent" }, textColor: "#6a6259" },
  grid: { vertLines: { color: "rgba(26,23,20,0.06)" }, horzLines: { color: "rgba(26,23,20,0.06)" } },
  crosshair: { mode: CrosshairMode.Normal },
  rightPriceScale: { borderColor: "rgba(26,23,20,0.12)" },
  timeScale: { borderColor: "rgba(26,23,20,0.12)", timeVisible: true },
};

function fmt(v, decimals = 2) {
  if (v == null) return "n/d";
  if (Math.abs(v) >= 1e12) return (v / 1e12).toFixed(2) + " T";
  if (Math.abs(v) >= 1e9) return (v / 1e9).toFixed(2) + " B";
  if (Math.abs(v) >= 1e6) return (v / 1e6).toFixed(2) + " M";
  return Number(v).toFixed(decimals);
}

function pct(v) {
  if (v == null) return "n/d";
  return (v * 100).toFixed(2) + "%";
}

function FundamentalsPanel({ data }) {
  if (!data) return null;
  const rows = [
    ["Sektor", data.sector],
    ["Branża", data.industry],
    ["P/E", fmt(data.pe)],
    ["P/B", fmt(data.pb)],
    ["ROE", pct(data.roe)],
    ["EPS", fmt(data.eps)],
    ["Dług/Kapital", fmt(data.debt_equity)],
    ["Dywidenda", pct(data.dividend_yield)],
    ["Przychody", fmt(data.revenue, 0)],
    ["Zysk netto", fmt(data.net_income, 0)],
    ["Market cap", fmt(data.market_cap, 0)],
  ];
  return (
    <div className="market-panel">
      <h4 className="market-panel-title">Fundamenty</h4>
      <dl className="market-metrics">
        {rows.filter(([, val]) => val != null && val !== "n/d").map(([label, val]) => (
          <div key={label} className="market-metric">
            <dt>{label}</dt>
            <dd>{val}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function EsgPanel({ data }) {
  if (!data) return (
    <div className="market-panel">
      <h4 className="market-panel-title">ESG (Yahoo Finance)</h4>
      <p className="market-null">Brak danych ESG dla tej spółki</p>
    </div>
  );
  const score = data.total;
  const color = score == null ? "#aaa" : score < 15 ? "#21513f" : score < 30 ? "#e8a838" : "#c0392b";
  return (
    <div className="market-panel">
      <h4 className="market-panel-title">ESG (Yahoo Finance)</h4>
      <div className="esg-total" style={{ color }}>
        {score != null ? score.toFixed(1) : "n/d"}
        <span className="esg-total-label">ryzyko ESG</span>
      </div>
      <dl className="market-metrics">
        {[["Środowisko", data.env], ["Społeczne", data.social], ["Zarządzanie", data.governance], ["Kontrowersje", data.controversy]].map(([label, val]) => (
          <div key={label} className="market-metric">
            <dt>{label}</dt>
            <dd>{val != null ? val.toFixed(1) : "n/d"}</dd>
          </div>
        ))}
      </dl>
      <p className="market-note">Niższy wynik = mniejsze ryzyko ESG</p>
    </div>
  );
}

export default function CompanyChart({ symbol }) {
  const [period, setPeriod] = useState("1y");
  const [chartType, setChartType] = useState("candle");
  const [indicators, setIndicators] = useState(new Set(["ma20", "ma50", "volume"]));
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const priceRef = useRef(null);
  const volumeRef = useRef(null);
  const rsiRef = useRef(null);
  const macdRef = useRef(null);

  // chart instances — destroyed & recreated on data/type/indicator changes
  const charts = useRef({});

  useEffect(() => {
    setLoading(true);
    setError(null);
    setData(null);
    fetchMarketData(symbol, period)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [symbol, period]);

  // Recreate all charts whenever data, chartType or indicators change
  useEffect(() => {
    // Destroy old charts
    Object.values(charts.current).forEach((c) => { try { c.remove(); } catch {} });
    charts.current = {};

    if (!data) return;

    // ── Price chart ──
    if (priceRef.current) {
      const pc = createChart(priceRef.current, { ...CHART_OPTS, height: 300, width: priceRef.current.clientWidth });
      charts.current.price = pc;

      if (chartType === "candle") {
        const s = pc.addCandlestickSeries({
          upColor: "#21513f", downColor: "#c0392b",
          borderUpColor: "#21513f", borderDownColor: "#c0392b",
          wickUpColor: "#21513f", wickDownColor: "#c0392b",
        });
        s.setData(data.candles.map((c) => ({ time: c.t, open: c.o, high: c.h, low: c.l, close: c.c })));
      } else {
        const s = pc.addLineSeries({ color: "#3b82f6", lineWidth: 2 });
        s.setData(data.candles.map((c) => ({ time: c.t, value: c.c })));
      }

      for (const ma of ["ma20", "ma50", "ma200"]) {
        if (indicators.has(ma) && data.indicators[ma]?.length) {
          const s = pc.addLineSeries({ color: MA_COLORS[ma], lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
          s.setData(data.indicators[ma].map((p) => ({ time: p.t, value: p.v })));
        }
      }
      pc.timeScale().fitContent();
    }

    // ── Volume chart ──
    if (volumeRef.current && indicators.has("volume") && data.candles.length) {
      const vc = createChart(volumeRef.current, { ...CHART_OPTS, height: 80, width: volumeRef.current.clientWidth });
      charts.current.volume = vc;
      const s = vc.addHistogramSeries({ priceFormat: { type: "volume" }, priceScaleId: "" });
      s.setData(data.candles.map((c) => ({
        time: c.t, value: c.v,
        color: c.c >= c.o ? "rgba(33,81,63,0.5)" : "rgba(192,57,43,0.5)",
      })));
      vc.timeScale().fitContent();
    }

    // ── RSI chart ──
    if (rsiRef.current && indicators.has("rsi") && data.indicators.rsi?.length) {
      const rc = createChart(rsiRef.current, { ...CHART_OPTS, height: 100, width: rsiRef.current.clientWidth });
      charts.current.rsi = rc;
      const s = rc.addLineSeries({ color: "#a855f7", lineWidth: 1, priceLineVisible: false });
      s.setData(data.indicators.rsi.map((p) => ({ time: p.t, value: p.v })));
      rc.timeScale().fitContent();
    }

    // ── MACD chart ──
    if (macdRef.current && indicators.has("macd") && data.indicators.macd?.length) {
      const mc = createChart(macdRef.current, { ...CHART_OPTS, height: 100, width: macdRef.current.clientWidth });
      charts.current.macd = mc;
      const hist = mc.addHistogramSeries({ priceLineVisible: false });
      hist.setData(data.indicators.macd.map((p) => ({
        time: p.t, value: p.hist,
        color: p.hist >= 0 ? "rgba(33,81,63,0.6)" : "rgba(192,57,43,0.6)",
      })));
      const macdLine = mc.addLineSeries({ color: "#3b82f6", lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      macdLine.setData(data.indicators.macd.map((p) => ({ time: p.t, value: p.macd })));
      const signalLine = mc.addLineSeries({ color: "#e8a838", lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      signalLine.setData(data.indicators.macd.map((p) => ({ time: p.t, value: p.signal })));
      mc.timeScale().fitContent();
    }

    // ResizeObserver for price chart
    const ro = new ResizeObserver(() => {
      Object.values(charts.current).forEach((c) => {
        try { c.applyOptions({ width: priceRef.current?.clientWidth || 600 }); } catch {}
      });
    });
    if (priceRef.current) ro.observe(priceRef.current);

    return () => {
      ro.disconnect();
      Object.values(charts.current).forEach((c) => { try { c.remove(); } catch {} });
      charts.current = {};
    };
  }, [data, chartType, indicators]);

  function toggleIndicator(name) {
    setIndicators((prev) => {
      const next = new Set(prev);
      next.has(name) ? next.delete(name) : next.add(name);
      return next;
    });
  }

  return (
    <div className="company-chart-panel">
      <div className="chart-controls">
        <div className="chart-control-group">
          {PERIODS.map((p) => (
            <button key={p} className={`chart-pill${period === p ? " active" : ""}`} onClick={() => setPeriod(p)}>{p}</button>
          ))}
        </div>
        <div className="chart-control-group">
          <button className={`chart-pill${chartType === "candle" ? " active" : ""}`} onClick={() => setChartType("candle")}>Świece</button>
          <button className={`chart-pill${chartType === "line" ? " active" : ""}`} onClick={() => setChartType("line")}>Linia</button>
        </div>
        <div className="chart-control-group">
          {["ma20", "ma50", "ma200", "volume", "rsi", "macd"].map((ind) => (
            <button
              key={ind}
              className={`chart-pill${indicators.has(ind) ? " active" : ""}`}
              style={indicators.has(ind) && MA_COLORS[ind] ? { borderColor: MA_COLORS[ind], color: MA_COLORS[ind] } : {}}
              onClick={() => toggleIndicator(ind)}
            >
              {ind.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {loading && <p className="chart-status">Ładowanie danych dla {symbol}…</p>}
      {error && <p className="chart-status chart-error">Błąd: {error}</p>}
      {data && data.actual_symbol !== symbol && (
        <p className="chart-status chart-ticker-note">Dane dla {data.actual_symbol} (Yahoo Finance)</p>
      )}

      <div className="chart-panes" style={{ display: data ? "grid" : "none" }}>
        <div className="chart-pane">
          <span className="chart-pane-label">Cena</span>
          <div ref={priceRef} style={{ height: 300 }} />
        </div>
        <div style={{ display: indicators.has("volume") ? "block" : "none" }} className="chart-pane">
          <span className="chart-pane-label">Wolumen</span>
          <div ref={volumeRef} style={{ height: 80 }} />
        </div>
        <div style={{ display: indicators.has("rsi") ? "block" : "none" }} className="chart-pane">
          <span className="chart-pane-label">RSI (14)</span>
          <div ref={rsiRef} style={{ height: 100 }} />
        </div>
        <div style={{ display: indicators.has("macd") ? "block" : "none" }} className="chart-pane">
          <span className="chart-pane-label">MACD (12/26/9)</span>
          <div ref={macdRef} style={{ height: 100 }} />
        </div>
      </div>

      {data && (
        <div className="market-data-row">
          <FundamentalsPanel data={data.fundamentals} />
          <EsgPanel data={data.esg} />
        </div>
      )}
    </div>
  );
}
