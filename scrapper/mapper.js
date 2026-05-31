// mapper.js
// Node 18+
// Run: node mapper.js

const fs = require("fs");

// ========= CONFIG =========
const STOCKTWITS_SYMBOLS_FILE = "./symbol_stocks_only.json"; // :contentReference[oaicite:2]{index=2}
const CMC_CATEGORIES_FILE = "./cmc_out//non_geo_cleaned.json";        // :contentReference[oaicite:3]{index=3}

// output
const OUT_MAP = "./cmc_to_stocktwits_symbol_map.json";
const OUT_UNMATCHED = "./cmc_unmatched_symbols.json";
const OUT_AMBIGUOUS = "./cmc_ambiguous_symbols.json";
const OUT_STATS = "./cmc_to_stocktwits_symbol_stats.json";

// ========= HELPERS =========
function readJson(p) {
  return JSON.parse(fs.readFileSync(p, "utf8"));
}
function writeJson(p, obj) {
  fs.writeFileSync(p, JSON.stringify(obj, null, 2), "utf8");
}
function isPlainObject(x) {
  return x && typeof x === "object" && !Array.isArray(x);
}
function up(s) {
  return String(s ?? "").trim().toUpperCase();
}
function uniq(arr) {
  return [...new Set(arr.filter(Boolean))];
}

// ========= LOADERS (robust CMC formats) =========
function cmcToCategoryList(cmcRaw) {
  if (Array.isArray(cmcRaw)) return cmcRaw;
  if (cmcRaw && Array.isArray(cmcRaw.categories)) return cmcRaw.categories;
  if (isPlainObject(cmcRaw)) {
    return Object.entries(cmcRaw).map(([category, payload]) => {
      if (isPlainObject(payload)) return { category, ...payload };
      return { category, payload };
    });
  }
  return [];
}

function extractTickersFromCategory(catObj) {
  if (!catObj || typeof catObj !== "object") return [];

  const containers = [
    catObj.tickers,
    catObj.symbols,
    catObj.records,
    catObj.coins,
    catObj.assets,
    catObj.entries,
    catObj.items,
    catObj.data,
    catObj.dane, // w Twoim pliku jest "dane": { TICKER: {...} } :contentReference[oaicite:4]{index=4}
  ].filter(Boolean);

  const out = [];

  for (const cont of containers) {
    if (Array.isArray(cont)) {
      for (const item of cont) {
        if (typeof item === "string" && item.trim()) out.push(item.trim());
        else if (isPlainObject(item)) {
          const sym = item.symbol ?? item.ticker ?? item.code ?? item.baseSymbol ?? item.id ?? null;
          if (typeof sym === "string" && sym.trim()) out.push(sym.trim());
        }
      }
    } else if (typeof cont === "string") {
      if (cont.trim()) out.push(cont.trim());
    } else if (isPlainObject(cont)) {
      // np. dane: { "CBOE": {...}, "POONAWALLA.NS": {...} } :contentReference[oaicite:5]{index=5}
      for (const key of Object.keys(cont)) {
        if (typeof key === "string" && key.trim()) out.push(key.trim());
      }
    }
  }

  return out;
}

// ========= STOCKTWITS INDEX =========
// budujemy:
// - set symboli "jak w pliku" (często z myślnikami: A2ZINFRA-NSE) :contentReference[oaicite:6]{index=6}
// - mapowanie symbol -> urlSymbol (z symbol_href: A2ZINFRA.NSE) :contentReference[oaicite:7]{index=7}
function buildStocktwitsIndex(stRaw) {
  const stSymbols = new Set();
  const stSymbolToUrlSymbol = new Map();

  for (const row of (Array.isArray(stRaw) ? stRaw : [])) {
    let sym = null;
    let href = null;

    if (typeof row === "string") {
      sym = up(row);
    } else if (isPlainObject(row)) {
      if (typeof row.symbol === "string") sym = up(row.symbol);
      if (typeof row.symbol_href === "string") href = row.symbol_href;
    }

    if (!sym) continue;
    stSymbols.add(sym);

    if (href) {
      // symbol_href wygląda jak https://stocktwits.com/symbol/A2ZINFRA.NSE :contentReference[oaicite:8]{index=8}
      const m = href.match(/\/symbol\/([^\/?#]+)/i);
      if (m && m[1]) stSymbolToUrlSymbol.set(sym, m[1]); // zostawiamy oryginalną kropkową postać
    }
  }

  return { stSymbols, stSymbolToUrlSymbol };
}

// ========= EXCHANGE / SUFFIX NORMALIZATION =========
// kluczowe mapowania wynikające z realnych różnic CMC↔Stocktwits (przykład NS→NSE) 
const EX_ALIAS = {
  // India
  NS: ["NSE"],
  BO: ["BSE"],

  // Kanada (CMC/Yahoo często: .TO / .V)
  TO: ["TSX"],
  V: ["TSXV"],

  // UK / Euronext – bywa różnie w danych, zostawiamy jako dodatkowe próby
  L: ["LSE", "LON"],
  LN: ["LSE", "LON"],
  AS: ["AMS", "AEX"],

  // kilka częstych (jeśli trafisz, pomoże; jak nie, nie szkodzi)
  SW: ["SIX"],
  HK: ["HKEX"],
  SI: ["SGX"],
  AX: ["ASX"],
  T: ["TSE", "TYO"],

  SS: ["SSE"],
  SZ: ["SZSE"],
  KS: ["KRX"],
  KQ: ["KOSDAQ"],
  TW: ["TWSE"],
};

// jeśli nie mamy wpisu, robimy jeszcze „heurystykę”: NS -> NSE (dodaj E) itp.
function expandExchangeAliases(ex) {
  const x = up(ex);
  const out = new Set([x]);

  const direct = EX_ALIAS[x];
  if (direct) for (const a of direct) out.add(up(a));

  // heurystyka: jeśli ex ma 2 litery, spróbuj dodać "E" (NS->NSE, BO->BOE? itd.)
  if (/^[A-Z]{2}$/.test(x)) out.add(x + "E");

  return [...out];
}

// ========= CANDIDATE GENERATOR =========
// cel: wygenerować możliwe formy Stocktwits SYMBOL (z myślnikami / kropkami / miks)
// Działa dla:
// - BASE
// - BASE.EX
// - BASE.CLASS.EX
// - BASE.CLASS.SUBCLASS.EX  (np. coś typu A.B.CSE – rzadkie, ale spotykane w ST)
function candidatesFromCmc(raw) {
  const s0 = up(raw);
  if (!s0) return [];

  // najpierw standaryzujemy separatory: / -> .
  const s = s0.replace(/\//g, ".");

  const parts = s.split(".").filter(Boolean);

  const cand = [];

  // 0) raw i proste warianty
  cand.push(s0);
  cand.push(s);
  cand.push(s.replace(/\./g, "-")); // wszystko na '-'

  // 1) BASE
  if (parts.length === 1) {
    // jeszcze klasy: BRK.B bywa bezpośrednio w CMC jako BRK.B -> w ST może być BRK-B
    // ale to ogarnia replace(/\./g,"-") powyżej
    return uniq(cand);
  }

  // 2) BASE + EXCHANGE (2 segmenty)
  if (parts.length === 2) {
    const base = parts[0];
    const ex = parts[1];

    for (const ex2 of expandExchangeAliases(ex)) {
      // formy dot i dash
      cand.push(`${base}.${ex2}`);
      cand.push(`${base}-${ex2}`);
    }

    // fallback: bez sufiksu
    cand.push(base);

    return uniq(cand);
  }

  // 3+) BASE + QUALIFIERS + EXCHANGE (>=3 segmenty)
  // np. AAWH.U.CSE -> w pliku ST jest "AAWH.U-CSE" :contentReference[oaicite:10]{index=10}
  // albo ABK.A.TSX -> w pliku ST bywa "ABK-A-TSX" :contentReference[oaicite:11]{index=11}
  const base = parts[0];
  const ex = parts[parts.length - 1];
  const mid = parts.slice(1, -1); // klasy/serie

  const midDot = mid.length ? `${base}.${mid.join(".")}` : base;   // base.mid.mid
  const midDash = mid.length ? `${base}-${mid.join("-")}` : base;  // base-mid-mid

  for (const ex2 of expandExchangeAliases(ex)) {
    // A) stocktwits-mix: BASE.MID-EX
    cand.push(`${midDot}-${ex2}`);
    // B) wszystko w dash: BASE-MID-EX
    cand.push(`${midDash}-${ex2}`);
    // C) czysty dot: BASE.MID.EX
    cand.push(`${base}.${mid.join(".")}.${ex2}`);
    // D) czysty dash: BASE-MID-EX (już jest), ale dodajmy też "BASE.MIDEX"? nie.
  }

  // fallbacki:
  cand.push(midDot);
  cand.push(midDash);
  cand.push(base);

  // agresywny sanitize (zostaw alnum + . -)
  cand.push(
    s0.replace(/[^A-Z0-9\.\-]/g, "-")
      .replace(/\-+/g, "-")
  );

  return uniq(cand);
}

// ========= MATCH =========
function matchOne(raw, stSymbols) {
  const cands = candidatesFromCmc(raw);

  const hits = [];
  for (const c of cands) {
    if (stSymbols.has(c)) hits.push(c);
  }

  if (hits.length === 0) return { chosen: null, hits: [], candidates: cands };
  return { chosen: hits[0], hits: uniq(hits), candidates: cands };
}

// ========= MAIN =========
(function main() {
  const stRaw = readJson(STOCKTWITS_SYMBOLS_FILE);
  const { stSymbols, stSymbolToUrlSymbol } = buildStocktwitsIndex(stRaw);

  const cmcRaw = readJson(CMC_CATEGORIES_FILE);
  const cmcCats = cmcToCategoryList(cmcRaw);

  console.log("Stocktwits symbols:", stSymbols.size);
  console.log("CMC categories:", cmcCats.length);

  // zbierz unikalne tickery z CMC
  const allCmc = new Set();
  for (const cat of cmcCats) {
    const arr = extractTickersFromCategory(cat);
    for (const t of arr) if (t && String(t).trim()) allCmc.add(String(t).trim());
  }

  console.log("CMC unique tickers:", allCmc.size);

  const mapping = {};   // raw -> { st_symbol, st_url_symbol } | null
  const unmatched = []; // { raw, candidates }
  const ambiguous = []; // { raw, chosen, hits, candidates }

  let matched = 0;

  for (const raw of allCmc) {
    const r = matchOne(raw, stSymbols);

    if (!r.chosen) {
      mapping[raw] = null;
      unmatched.push({ raw, candidates: r.candidates.slice(0, 25) });
      continue;
    }

    matched++;

    const st_symbol = r.chosen;
    // url symbol: preferuj to co wynika z symbol_href (to jest „prawda” dla scrapera) :contentReference[oaicite:12]{index=12}
    const st_url_symbol = stSymbolToUrlSymbol.get(st_symbol) || null;

    mapping[raw] = { st_symbol, st_url_symbol };

    if (r.hits.length > 1) {
      ambiguous.push({
        raw,
        chosen: st_symbol,
        hits: r.hits,
        candidates: r.candidates.slice(0, 35),
      });
    }
  }

  const stats = {
    cmc_unique_symbols: allCmc.size,
    stocktwits_symbols: stSymbols.size,
    matched,
    unmatched: allCmc.size - matched,
    ambiguous: ambiguous.length,
    match_rate: allCmc.size ? matched / allCmc.size : 0,
    outputs: { OUT_MAP, OUT_UNMATCHED, OUT_AMBIGUOUS, OUT_STATS },
  };

  writeJson(OUT_MAP, mapping);
  writeJson(OUT_UNMATCHED, unmatched);
  writeJson(OUT_AMBIGUOUS, ambiguous);
  writeJson(OUT_STATS, stats);

  console.log("Done.");
  console.log(stats);
})();