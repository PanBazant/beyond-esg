// non_geo_clean_by_redundancy.js
// Node 18+
// Run: node non_geo_clean_by_redundancy.js

const fs = require("fs");

// ========= CONFIG =========
const INPUT_FILE = "./cmc_out/categories_top250.json";

// TYLKO DWA WYJŚCIA:
const OUT_CLEAN = "./cmc_out/non_geo_cleaned.json";           // pełne dane
const OUT_INDEX = "./cmc_out/non_geo_cleaned_index.json";     // spis kategorii (czytelny)

// Redundancja zbiorów (tylko matematyka na tickerach)
const CONTAINMENT_THRESHOLD = 0.85; // B ⊆ A w >= 85% -> B do wywalenia
const JACCARD_THRESHOLD = 0.60;     // Jaccard(A,B) >= 0.60 -> prawie duplikaty

// ========= helpers =========
function readJson(p) {
  return JSON.parse(fs.readFileSync(p, "utf-8"));
}
function writeJson(p, obj) {
  fs.writeFileSync(p, JSON.stringify(obj, null, 2), "utf-8");
}
function safeArray(x) {
  return Array.isArray(x) ? x : [];
}
function uniq(arr) {
  return Array.from(new Set(arr));
}
function intersectionSize(A, B) {
  const [small, big] = A.size <= B.size ? [A, B] : [B, A];
  let c = 0;
  for (const x of small) if (big.has(x)) c++;
  return c;
}
function jaccard(A, B) {
  const inter = intersectionSize(A, B);
  const union = A.size + B.size - inter;
  return union === 0 ? 0 : inter / union;
}
function containment(B_in_A_inter, sizeB) {
  return sizeB === 0 ? 0 : (B_in_A_inter / sizeB);
}
function isGeo(listingUrl) {
  const u = String(listingUrl || "");
  return u.includes("/largest-companies-in-") || u.includes("/largest-companies-in-the-");
}

// “lepsza” = większy zbiór tickerów (to tylko wybór reprezentanta)
function score(cat) {
  return cat.tickers.length;
}

// ========= load NON-GEO =========
const data = readJson(INPUT_FILE);

const nonGeo = [];
for (const [slug, entry] of Object.entries(data)) {
  if (isGeo(entry.listing_url)) continue;

  const tickersRaw = safeArray(entry.spolki).map(x => String(x ?? "").trim()).filter(Boolean);
  const tickers = uniq(tickersRaw);

  nonGeo.push({
    slug,
    name: entry.category || slug,
    listing_url: entry.listing_url || "",
    tickers,
    dane: entry.dane || {},
  });
}

// zbiory do obliczeń
const cats = nonGeo
  .map(c => ({ ...c, set: new Set(c.tickers) }))
  .sort((a, b) => b.tickers.length - a.tickers.length || a.slug.localeCompare(b.slug));

// ========= remove redundancy (bez raportów) =========
const kept = new Set(cats.map(c => c.slug));

function drop(slug) {
  kept.delete(slug);
}

// 1) containment pass
for (let i = 0; i < cats.length; i++) {
  const A = cats[i];
  if (!kept.has(A.slug)) continue;

  for (let j = 0; j < cats.length; j++) {
    if (i === j) continue;
    const B = cats[j];
    if (!kept.has(B.slug)) continue;

    if (B.set.size > A.set.size) continue;

    const inter = intersectionSize(A.set, B.set);
    const cont = containment(inter, B.set.size);

    if (cont >= CONTAINMENT_THRESHOLD) {
      drop(B.slug);
    }
  }
}

// 2) jaccard pass
const keptList = cats.filter(c => kept.has(c.slug));
for (let i = 0; i < keptList.length; i++) {
  const A = keptList[i];
  if (!kept.has(A.slug)) continue;

  for (let j = i + 1; j < keptList.length; j++) {
    const B = keptList[j];
    if (!kept.has(B.slug)) continue;

    const jac = jaccard(A.set, B.set);
    if (jac >= JACCARD_THRESHOLD) {
      const keepA = score(A) > score(B) || (score(A) === score(B) && A.slug.localeCompare(B.slug) <= 0);
      const toDrop = keepA ? B : A;
      drop(toDrop.slug);
    }
  }
}

// ========= build outputs =========
const cleanedCategories = cats
  .filter(c => kept.has(c.slug))
  .map(c => ({
    slug: c.slug,
    name: c.name,
    listing_url: c.listing_url,
    tickers: c.tickers, // pełna lista tickerów
    dane: c.dane        // pełne dane ticker->rekord
  }))
  .sort((a, b) => b.tickers.length - a.tickers.length || a.slug.localeCompare(b.slug));

writeJson(OUT_CLEAN, {
  input: INPUT_FILE,
  scope: "NON_GEO",
  params: { CONTAINMENT_THRESHOLD, JACCARD_THRESHOLD },
  counts: {
    before: nonGeo.length,
    after: cleanedCategories.length
  },
  categories: cleanedCategories
});

// SPIS (czytelny)
const index = cleanedCategories.map(c => ({
  slug: c.slug,
  name: c.name,
  tickers_unique: Array.isArray(c.tickers) ? c.tickers.length : 0,
  dane_count: c.dane && typeof c.dane === "object" ? Object.keys(c.dane).length : 0,
  listing_url: c.listing_url
}));

writeJson(OUT_INDEX, {
  input: INPUT_FILE,
  scope: "NON_GEO",
  counts: { categories: index.length },
  categories: index
});

console.log("DONE");
console.log("CLEAN:", OUT_CLEAN);
console.log("INDEX:", OUT_INDEX);