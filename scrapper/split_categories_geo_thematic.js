// group_existing_categories_data.js
// Node 18+
// Run: node group_existing_categories_data.js

const fs = require("fs");

// === CONFIG ===
const INPUT_DATA_FILE = "./cmc_out/categories_top250.json"; // tu masz dane z tickrami
const INPUT_CATEGORIES_FILE = "./categories.json";  // opcjonalnie: słownik nazw (jeśli masz)
const WRITE_PER_GROUP_FILES = true;

// ---- helpers ----
function readJson(p) {
  return JSON.parse(fs.readFileSync(p, "utf-8"));
}
function writeJson(p, obj) {
  fs.writeFileSync(p, JSON.stringify(obj, null, 2), "utf-8");
}
function safeStr(x) {
  return typeof x === "string" ? x : "";
}

// ---- load data ----
const data = readJson(INPUT_DATA_FILE); // { slug: { category, listing_url, spolki, dane } }
let categoriesDict = null;

try {
  const catDoc = readJson(INPUT_CATEGORIES_FILE);
  const arr = Array.isArray(catDoc.categories) ? catDoc.categories : [];
  categoriesDict = new Map(arr.map(c => [c.slug, c]));
} catch {
  categoriesDict = null;
}

// ---- heurystyki klasyfikacji ----
// 1) geo: CompaniesMarketCap używa bardzo charakterystycznego patternu URL
function isGeo(entry) {
  const url = safeStr(entry.listing_url) + " " + safeStr(entry.url) + " " + safeStr(entry.href);
  return (
    url.includes("/largest-companies-in-") ||
    url.includes("/largest-companies-in-the-")
  );
}

// 2) indeksy/meta: rzeczy niebranżowe, “benchmarki”, total marketcap, itp.
function isIndexOrMeta(slug, entry, dictItem) {
  const s = safeStr(slug).toLowerCase();
  const name =
    safeStr(entry.category) ||
    safeStr(dictItem?.name) ||
    safeStr(dictItem?.title) ||
    "";

  if (s === "assets-by-market-cap" || s === "total-marketcap") return true;

  // indeksy/benchmarki po slug
  const markers = ["dow-jones", "dax", "cac-40"];
  if (markers.some(m => s.includes(m))) return true;

  // indeksy po nazwie
  const n = name.toLowerCase();
  if (n.includes("dow") || n.includes("dax") || n.includes("cac")) return true;

  return false;
}

function enrichName(slug, entry) {
  const dictItem = categoriesDict ? categoriesDict.get(slug) : null;
  return {
    slug,
    name: entry.category || dictItem?.name || dictItem?.title || slug,
    listing_url: entry.listing_url || dictItem?.url || "",
  };
}

// ---- group ----
const grouped = {
  input_data_file: INPUT_DATA_FILE,
  input_categories_file: INPUT_CATEGORIES_FILE,
  counts: {
    total: 0,
    geographic: 0,
    thematic: 0,
    indices_and_meta: 0,
  },
  geographic: {},
  thematic: {},
  indices_and_meta: {},
  summary_list: {
    geographic: [],
    thematic: [],
    indices_and_meta: [],
  }
};

for (const [slug, entry] of Object.entries(data)) {
  grouped.counts.total++;

  const dictItem = categoriesDict ? categoriesDict.get(slug) : null;

  if (isIndexOrMeta(slug, entry, dictItem)) {
    grouped.indices_and_meta[slug] = entry; // zachowujesz pełne dane!
    grouped.summary_list.indices_and_meta.push(enrichName(slug, entry));
    grouped.counts.indices_and_meta++;
    continue;
  }

  if (isGeo(entry)) {
    grouped.geographic[slug] = entry;
    grouped.summary_list.geographic.push(enrichName(slug, entry));
    grouped.counts.geographic++;
  } else {
    grouped.thematic[slug] = entry;
    grouped.summary_list.thematic.push(enrichName(slug, entry));
    grouped.counts.thematic++;
  }
}

// sort listy dla stabilności
for (const k of ["geographic", "thematic", "indices_and_meta"]) {
  grouped.summary_list[k].sort((a, b) => a.slug.localeCompare(b.slug));
}

// ---- write outputs ----
const base = INPUT_DATA_FILE.replace(/\.json$/i, "");
writeJson(`${base}_grouped.json`, grouped);

if (WRITE_PER_GROUP_FILES) {
  writeJson(`${base}_geographic.json`, grouped.geographic);
  writeJson(`${base}_thematic.json`, grouped.thematic);
  writeJson(`${base}_indices_and_meta.json`, grouped.indices_and_meta);

  // lekkie listy (same slugi+name) – do ręcznego przeglądu
  writeJson(`${base}_geographic_list.json`, grouped.summary_list.geographic);
  writeJson(`${base}_thematic_list.json`, grouped.summary_list.thematic);
  writeJson(`${base}_indices_and_meta_list.json`, grouped.summary_list.indices_and_meta);
}

console.log("DONE");