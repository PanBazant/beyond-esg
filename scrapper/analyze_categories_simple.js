// analyze_categories_to_files.js
// Node 18+
// Run: node analyze_categories_to_files.js

const fs = require("fs");

// === CONFIG ===
const INPUT_FILE = "./cmc_out/categories_top250.json";
const MIN_CATEGORIES_FOR_DUP = 2; // ticker uznany za duplikat jeśli jest w >= 2 kategoriach
const OVERLAP_SAMPLE_SIZE = 30;   // ile tickerów przykładowych trzymać w raporcie overlap (żeby nie wybuchł plik)

// ---------------- helpers ----------------
function readJson(p) {
  return JSON.parse(fs.readFileSync(p, "utf-8"));
}

function writeJson(p, obj) {
  fs.writeFileSync(p, JSON.stringify(obj, null, 2), "utf-8");
}

function safeLen(x) {
  if (Array.isArray(x)) return x.length;
  if (x && typeof x === "object") return Object.keys(x).length;
  return 0;
}

function uniq(arr) {
  return Array.from(new Set(arr));
}

// ---------------- main ----------------
const data = readJson(INPUT_FILE);

// 1) per category counts + ticker -> categories
const categories = [];
const tickerToCats = new Map(); // ticker -> [slug...]

for (const [slug, entry] of Object.entries(data)) {
  const catName = entry.category || slug;
  const spolki = entry.spolki || [];
  const dane = entry.dane || {};

  const nSpolki = safeLen(spolki);
  const nDane = safeLen(dane);

  if (Array.isArray(spolki)) {
    for (const t of spolki) {
      if (typeof t !== "string") continue;
      const tick = t.trim();
      if (!tick) continue;
      if (!tickerToCats.has(tick)) tickerToCats.set(tick, []);
      tickerToCats.get(tick).push(slug);
    }
  }

  categories.push({
    slug,
    category: catName,
    count_spolki: nSpolki,
    count_dane: nDane,
    listing_url: entry.listing_url || "",
  });
}

// sort alphabetically for stable output
categories.sort((a, b) => a.slug.localeCompare(b.slug));

// 2) duplicates across categories (>= MIN_CATEGORIES_FOR_DUP)
const duplicates = []; // { ticker, categories_count, slugs[] }
for (const [ticker, slugs] of tickerToCats.entries()) {
  const u = uniq(slugs).sort();
  if (u.length >= MIN_CATEGORIES_FOR_DUP) {
    duplicates.push({ ticker, categories_count: u.length, slugs: u });
  }
}
duplicates.sort((a, b) => b.categories_count - a.categories_count || a.ticker.localeCompare(b.ticker));

// 3) overlaps between category pairs
const catToSet = new Map(); // slug -> Set(tickers)
for (const c of categories) {
  const entry = data[c.slug] || {};
  const tickers = Array.isArray(entry.spolki) ? entry.spolki : [];
  catToSet.set(c.slug, new Set(tickers));
}

const slugs = Array.from(catToSet.keys()).sort();
const overlaps = []; // { shared, a, b, sample[] }

for (let i = 0; i < slugs.length; i++) {
  const a = slugs[i];
  const A = catToSet.get(a);
  if (!A || A.size === 0) continue;

  for (let j = i + 1; j < slugs.length; j++) {
    const b = slugs[j];
    const B = catToSet.get(b);
    if (!B || B.size === 0) continue;

    const [small, big] = A.size <= B.size ? [A, B] : [B, A];
    const inter = [];
    for (const t of small) if (big.has(t)) inter.push(t);

    if (inter.length > 0) {
      inter.sort();
      overlaps.push({
        shared: inter.length,
        a,
        b,
        sample: inter.slice(0, OVERLAP_SAMPLE_SIZE),
      });
    }
  }
}

overlaps.sort((x, y) => y.shared - x.shared || x.a.localeCompare(y.a) || x.b.localeCompare(y.b));

// ---- write output files ----
const base = INPUT_FILE.replace(/\.json$/i, "");

const outCounts = `${base}_report_counts.json`;
const outDups = `${base}_report_duplicates.json`;
const outOverlap = `${base}_report_overlaps.json`;

writeJson(outCounts, {
  input: INPUT_FILE,
  categories_count: categories.length,
  unique_tickers_overall: tickerToCats.size,
  categories,
});

writeJson(outDups, {
  input: INPUT_FILE,
  min_categories: MIN_CATEGORIES_FOR_DUP,
  duplicates_count: duplicates.length,
  duplicates,
});

writeJson(outOverlap, {
  input: INPUT_FILE,
  overlap_pairs_count: overlaps.length,
  overlap_sample_size: OVERLAP_SAMPLE_SIZE,
  overlaps,
});

// Minimal console info (żebyś wiedział, że poszło)
console.log("DONE");
console.log(outCounts);
console.log(outDups);
console.log(outOverlap);