// merge_top_cmc_with_stocktwits.js
// Node 18+
// Run: node merge_top_cmc_with_stocktwits.js

const fs = require("fs");

// ========= CONFIG =========
const CMC_CATEGORIES_FILE = "./cmc_out/non_geo_cleaned.json";
const STOCKTWITS_SYMBOLS_FILE = "./symbol_stocks_only.json";

// optional map (if exists)
const MAPPING_FILE = "./cmc_to_stocktwits_symbol_map.json";

const TOP_PER_CATEGORY = 250; // ustaw jak chcesz (np. 100)

// outputs
const OUT_MERGED_CATEGORIES = "./merged_categories_stocktwits.json";
const OUT_MERGED_FLAT_JSONL = "./merged_flat_stocktwits.jsonl";
const OUT_REPORT = "./merge_report.json";

// ========= HELPERS =========
function readJson(p) {
  return JSON.parse(fs.readFileSync(p, "utf8"));
}
function writeJson(p, obj) {
  fs.writeFileSync(p, JSON.stringify(obj, null, 2), "utf8");
}
function writeJsonl(p, rows) {
  const out = rows.map(r => JSON.stringify(r)).join("\n") + "\n";
  fs.writeFileSync(p, out, "utf8");
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
function fileExists(p) {
  try { fs.accessSync(p, fs.constants.F_OK); return true; } catch { return false; }
}
function prefixKeys(obj, prefix) {
  if (!isPlainObject(obj)) return {};
  const out = {};
  for (const [k, v] of Object.entries(obj)) out[`${prefix}${k}`] = v;
  return out;
}

// ========= CMC LOADER (robust formats) =========
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

// wyciąga listę „top” tickerów z kategorii + opcjonalnie rekordy
// obsługuje typowe pola: tickers/symbols/records/dane
function extractTopFromCategory(catObj, topN) {
  if (!catObj || typeof catObj !== "object") return { tickers: [], cmcRecordBySymbol: {} };

  // 1) jeśli masz wprost listę tickerów
  const listCandidates = [
    catObj.tickers,
    catObj.symbols,
    catObj.records,
    catObj.items,
    catObj.entries,
    catObj.coins,
    catObj.assets,
    catObj.data,
  ].filter(Boolean);

  // 2) jeśli masz „dane” jako obiekt { TICKER: {...}, ... }
  // (to jest mega wygodne do merge, bo masz rekord per ticker)
  const cmcRecordBySymbol = {};
  if (isPlainObject(catObj.dane)) {
    for (const [sym, rec] of Object.entries(catObj.dane)) {
      cmcRecordBySymbol[String(sym)] = rec;
    }
  }
  // czasem to może się nazywać "data" jako obiekt
  if (isPlainObject(catObj.data) && !Array.isArray(catObj.data)) {
    // uważaj, bo czasem data to array; tu tylko obiekt
    for (const [sym, rec] of Object.entries(catObj.data)) {
      cmcRecordBySymbol[String(sym)] = rec;
    }
  }

  // zbierz tickery w kolejności (ważne: zachowujemy kolejność top)
  const tickersOrdered = [];

  for (const cont of listCandidates) {
    if (Array.isArray(cont)) {
      for (const item of cont) {
        if (typeof item === "string" && item.trim()) tickersOrdered.push(item.trim());
        else if (isPlainObject(item)) {
          const sym = item.symbol ?? item.ticker ?? item.code ?? item.baseSymbol ?? null;
          if (typeof sym === "string" && sym.trim()) {
            tickersOrdered.push(sym.trim());
            // jeśli to jest rekord, zachowaj go też jako cmc rekord
            cmcRecordBySymbol[sym.trim()] = cmcRecordBySymbol[sym.trim()] ?? item;
          }
        }
      }
      break; // bierzemy pierwszą sensowną listę jako ranking „top”
    }
  }

  // jeśli nie było list, ale jest "dane", to ranking jest nieznany — wtedy bierzemy klucze
  if (tickersOrdered.length === 0 && Object.keys(cmcRecordBySymbol).length) {
    for (const sym of Object.keys(cmcRecordBySymbol)) tickersOrdered.push(sym);
  }

  const tickersTop = tickersOrdered.slice(0, topN);

  return { tickers: tickersTop, cmcRecordBySymbol };
}

// ========= STOCKTWITS INDEX =========
function buildStocktwitsIndex(stRaw) {
  // index: symbol (jak w pliku) -> cały rekord
  const bySymbol = new Map();
  // index URL symbol: to co jest po /symbol/ w symbol_href (często z kropkami)
  const byUrlSymbol = new Map();

  for (const row of (Array.isArray(stRaw) ? stRaw : [])) {
    if (typeof row === "string") {
      const sym = up(row);
      bySymbol.set(sym, { symbol: sym });
      continue;
    }
    if (!isPlainObject(row)) continue;

    const sym = typeof row.symbol === "string" ? up(row.symbol) : null;
    if (!sym) continue;

    bySymbol.set(sym, row);

    const href = row.symbol_href;
    if (typeof href === "string") {
      const m = href.match(/\/symbol\/([^\/?#]+)/i);
      if (m && m[1]) {
        // zostawiamy dokładnie jak w URL (zwykle kropki)
        byUrlSymbol.set(String(m[1]).toUpperCase(), row);
      }
    }
  }

  return { bySymbol, byUrlSymbol };
}

// ========= MAPPING (robust, includes exchange suffix aliases) =========
const EX_ALIAS = {
  NS: ["NSE"],
  BO: ["BSE"],
  TO: ["TSX"],
  V: ["TSXV"],
  L: ["LSE", "LON"],
  LN: ["LSE", "LON"],
  AS: ["AMS", "AEX"],
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

function expandExchangeAliases(ex) {
  const x = up(ex);
  const out = new Set([x]);
  const direct = EX_ALIAS[x];
  if (direct) for (const a of direct) out.add(up(a));
  if (/^[A-Z]{2}$/.test(x)) out.add(x + "E"); // NS->NSE heuristic
  return [...out];
}

function candidatesFromCmcSymbol(raw) {
  const s0 = up(raw);
  if (!s0) return [];

  // unify separators
  const s = s0.replace(/\//g, ".");
  const parts = s.split(".").filter(Boolean);

  const cand = [];
  cand.push(s0);
  cand.push(s);
  cand.push(s.replace(/\./g, "-"));

  if (parts.length === 1) return uniq(cand);

  if (parts.length === 2) {
    const base = parts[0];
    const ex = parts[1];
    for (const ex2 of expandExchangeAliases(ex)) {
      cand.push(`${base}.${ex2}`);
      cand.push(`${base}-${ex2}`);
    }
    cand.push(base);
    return uniq(cand);
  }

  // >=3 : BASE + qualifiers + EX
  const base = parts[0];
  const ex = parts[parts.length - 1];
  const mid = parts.slice(1, -1);

  const midDot = `${base}.${mid.join(".")}`;   // BASE.MID.MID
  const midDash = `${base}-${mid.join("-")}`; // BASE-MID-MID

  for (const ex2 of expandExchangeAliases(ex)) {
    cand.push(`${midDot}-${ex2}`);            // BASE.MID-EX  (częsty pattern ST)
    cand.push(`${midDash}-${ex2}`);           // BASE-MID-EX
    cand.push(`${base}.${mid.join(".")}.${ex2}`); // BASE.MID.EX
    cand.push(`${base}-${mid.join("-")}-${ex2}`); // BASE-MID-EX
  }

  cand.push(midDot);
  cand.push(midDash);
  cand.push(base);

  // aggressive sanitize
  cand.push(
    s0.replace(/[^A-Z0-9\.\-]/g, "-").replace(/\-+/g, "-")
  );

  return uniq(cand);
}

// wybiera najlepszy match w Stocktwits indexach
function mapCmcToStocktwits(raw, stIndex) {
  const cands = candidatesFromCmcSymbol(raw);

  // 1) exact match against "symbol" field (often with dashes)
  for (const c of cands) {
    const rec = stIndex.bySymbol.get(c);
    if (rec) return { st_symbol: c, st_url_symbol: extractUrlSymbol(rec) };
  }

  // 2) try matching against url-symbol form (often with dots)
  for (const c of cands) {
    const rec = stIndex.byUrlSymbol.get(c);
    if (rec) return { st_symbol: up(rec.symbol), st_url_symbol: extractUrlSymbol(rec) };
  }

  return null;
}

function extractUrlSymbol(stocktwitsRow) {
  if (!stocktwitsRow || typeof stocktwitsRow !== "object") return null;
  const href = stocktwitsRow.symbol_href;
  if (typeof href !== "string") return null;
  const m = href.match(/\/symbol\/([^\/?#]+)/i);
  return (m && m[1]) ? m[1] : null; // keep original case from URL
}

// ========= MAIN MERGE =========
(function main() {
  const cmcRaw = readJson(CMC_CATEGORIES_FILE);
  const cmcCats = cmcToCategoryList(cmcRaw);

  const stRaw = readJson(STOCKTWITS_SYMBOLS_FILE);
  const stIndex = buildStocktwitsIndex(stRaw);

  // optional previously computed mapping
  const preMap = fileExists(MAPPING_FILE) ? readJson(MAPPING_FILE) : null;

  console.log("CMC categories:", cmcCats.length);
  console.log("Stocktwits symbols indexed:", stIndex.bySymbol.size);

  const mergedCategories = [];
  const flatRows = [];
  const report = {
    top_per_category: TOP_PER_CATEGORY,
    categories: [],
    totals: { categories: cmcCats.length, requested: 0, matched: 0, dropped: 0 }
  };

  for (const cat of cmcCats) {
    const categoryName = cat.category ?? cat.name ?? cat.title ?? cat.label ?? "UNKNOWN_CATEGORY";
    const { tickers, cmcRecordBySymbol } = extractTopFromCategory(cat, TOP_PER_CATEGORY);

    const items = [];
    let matched = 0;
    let dropped = 0;

    for (let i = 0; i < tickers.length; i++) {
      const cmc_symbol_raw = tickers[i];
      const cmc_rank_in_category = i + 1;

      // prefer precomputed map if present
      let mapped = null;
      if (preMap && preMap[cmc_symbol_raw]) {
        // obsłuż oba formaty mapowania: {st_symbol, st_url_symbol} albo string
        const v = preMap[cmc_symbol_raw];
        if (typeof v === "string") mapped = { st_symbol: v, st_url_symbol: null };
        else if (v && typeof v === "object") mapped = v;
      }
      if (!mapped) mapped = mapCmcToStocktwits(cmc_symbol_raw, stIndex);

      if (!mapped) {
        dropped++;
        continue;
      }

      const stRec = stIndex.bySymbol.get(up(mapped.st_symbol))
        ?? (mapped.st_url_symbol ? stIndex.byUrlSymbol.get(up(mapped.st_url_symbol)) : null);

      if (!stRec) {
        // teoretycznie nie powinno się zdarzyć, ale zostawmy bez wywalenia
        dropped++;
        continue;
      }

      matched++;

      const cmcRec = cmcRecordBySymbol[cmc_symbol_raw]
        ?? cmcRecordBySymbol[up(cmc_symbol_raw)]
        ?? null;

      // final merged record (dwa warianty: zagnieżdżony + spłaszczony prefiksami)
      const mergedNested = {
        category: categoryName,
        cmc_rank_in_category,
        cmc_symbol_raw,
        st_symbol: up(mapped.st_symbol),
        st_url_symbol: mapped.st_url_symbol ?? null,
        cmc: cmcRec,
        stocktwits: stRec
      };

      // spłaszczony rekord: lepszy do analiz tabelarycznych
      const mergedFlat = {
        category: categoryName,
        cmc_rank_in_category,
        cmc_symbol_raw,
        st_symbol: up(mapped.st_symbol),
        st_url_symbol: mapped.st_url_symbol ?? null,
        ...prefixKeys(cmcRec, "cmc_"),
        ...prefixKeys(stRec, "st_")
      };

      items.push(mergedNested);
      flatRows.push(mergedFlat);
    }

    mergedCategories.push({
      category: categoryName,
      requested_top: tickers.length,
      matched_count: matched,
      dropped_count: dropped,
      coverage: tickers.length ? matched / tickers.length : 0,
      items
    });

    report.categories.push({
      category: categoryName,
      requested_top: tickers.length,
      matched,
      dropped,
      coverage: tickers.length ? matched / tickers.length : 0
    });

    report.totals.requested += tickers.length;
    report.totals.matched += matched;
    report.totals.dropped += dropped;
  }

  writeJson(OUT_MERGED_CATEGORIES, mergedCategories);
  writeJsonl(OUT_MERGED_FLAT_JSONL, flatRows);
  writeJson(OUT_REPORT, report);

  console.log("Done.");
  console.log("Wrote:", OUT_MERGED_CATEGORIES, OUT_MERGED_FLAT_JSONL, OUT_REPORT);
  console.log("Totals:", report.totals);
})();