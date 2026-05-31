// cmc_scrape_category.js
// TOP N per category z companiesmarketcap.com
// OUTPUT FORMAT (bez wrapperów):
//   result[category_slug] = {
//     category: "<NAZWA KATEGORII>",
//     listing_url: "<URL LISTINGU>",
//     spolki: ["TICKER", ...],
//     dane: { "TICKER": { rank, company_name, market_cap, company_url, page } }
//   }
//
// Użycie:
//   node cmc_scrape_category.js
//   node cmc_scrape_category.js --all
//
// Wymaga wcześniej:
//   node cmc_get_categories.js  -> cmc_out/categories.json

const puppeteer = require("puppeteer");
const fs = require("fs");
const path = require("path");
const readline = require("readline");

const BASE = "https://companiesmarketcap.com";
const OUT_DIR = "cmc_out";
const CATEGORIES_FILE = path.join(OUT_DIR, "categories.json");

const DEFAULT_LIMIT = 250;
const DEFAULT_OUT_FILE = (limit) => path.join(OUT_DIR, `categories_top${limit}.json`);

const NAV_TIMEOUT = 60000;

// tempo (human-ish)
const MIN_SLEEP = 220;
const MAX_SLEEP = 720;
const LONG_PAUSE_EVERY_PAGES = 7;
const LONG_PAUSE_MIN = 1400;
const LONG_PAUSE_MAX = 2800;

const DEBUG = false;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const rand = (a, b) => Math.floor(Math.random() * (b - a + 1)) + a;

function ensureDir(p) {
  if (!fs.existsSync(p)) fs.mkdirSync(p, { recursive: true });
}

function loadJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf-8"));
}

function saveJson(filePath, obj) {
  fs.writeFileSync(filePath, JSON.stringify(obj, null, 2), "utf-8");
}

function ask(question) {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise((resolve) =>
    rl.question(question, (ans) => {
      rl.close();
      resolve(ans);
    })
  );
}

function hasFlag(name) {
  return process.argv.slice(2).includes(name);
}

function normalize(s) {
  return (s || "").toLowerCase().replace(/\s+/g, " ").trim();
}

function showCategories(cats, limit = 30) {
  const shown = cats.slice(0, limit);
  for (let i = 0; i < shown.length; i++) {
    const c = shown[i];
    console.log(`${String(i + 1).padStart(3, " ")}. ${c.name}  (${c.slug})`);
  }
  if (cats.length > limit) console.log(`... (${cats.length - limit} more)`);
}

function pickByNumbers(input, cats) {
  const s = (input || "").replace(/\s+/g, "");
  if (!s) return [];

  const parts = s.split(",");
  const idx = new Set();

  for (const p of parts) {
    if (!p) continue;
    if (p.includes("-")) {
      const [a, b] = p.split("-").map((x) => parseInt(x, 10));
      if (!Number.isFinite(a) || !Number.isFinite(b)) continue;
      const lo = Math.min(a, b);
      const hi = Math.max(a, b);
      for (let k = lo; k <= hi; k++) idx.add(k - 1);
    } else {
      const n = parseInt(p, 10);
      if (Number.isFinite(n)) idx.add(n - 1);
    }
  }

  return Array.from(idx)
    .filter((i) => i >= 0 && i < cats.length)
    .map((i) => cats[i]);
}

function isListingUrl(url) {
  const u = String(url || "");
  return /by-market-cap/i.test(u) || /\/largest-/i.test(u) || /largest-.*companies/i.test(u);
}

// --- cookie click, ale bez crasha "execution context destroyed"
async function acceptCookiesIfAny(page) {
  for (let attempt = 1; attempt <= 2; attempt++) {
    try {
      const clicked = await page.evaluate(() => {
        const els = Array.from(document.querySelectorAll("button, a, div[role='button']"));
        const cand = els.find((el) => /accept|agree|got it|ok/i.test((el.textContent || "").trim()));
        if (cand) {
          cand.click();
          return true;
        }
        return false;
      });

      if (clicked) {
        // klik czasem robi reload -> poczekaj, ale bez twardego faila
        await page.waitForNavigation({ waitUntil: "domcontentloaded", timeout: 8000 }).catch(() => {});
      }
      return;
    } catch (e) {
      const msg = String(e?.message || e);
      if (msg.includes("Execution context was destroyed")) {
        await page.waitForNavigation({ waitUntil: "domcontentloaded", timeout: 15000 }).catch(() => {});
        await sleep(rand(200, 600));
        continue;
      }
      return;
    }
  }
}

// --- jeśli kategoria jest /slug/ (nie listing), znajdź link do listingu
async function resolveListingUrl(page, categoryUrl) {
  // odporne na reload w trakcie evaluate/$$eval
  for (let attempt = 1; attempt <= 4; attempt++) {
    try {
      await page.goto(categoryUrl, { waitUntil: "domcontentloaded", timeout: NAV_TIMEOUT });
      await sleep(rand(350, 800));
      await acceptCookiesIfAny(page);
      await sleep(rand(200, 450));

      // Najbardziej typowe linki do listingów
      let href = "";
      try {
        href = await page.$$eval(
          'a[href*="/largest-"][href*="by-market-cap"]',
          (as) => (as.length ? as[0].href : "")
        );
      } catch {}

      // Fallback: cokolwiek z by-market-cap
      if (!href) {
        try {
          href = await page.$$eval('a[href*="by-market-cap"]', (as) => (as.length ? as[0].href : ""));
        } catch {}
      }

      return href || categoryUrl;
    } catch (e) {
      const msg = String(e?.message || e);
      if (msg.includes("Execution context was destroyed")) {
        await page.waitForNavigation({ waitUntil: "domcontentloaded", timeout: 15000 }).catch(() => {});
        await sleep(rand(250, 900));
        continue;
      }
      throw e;
    }
  }
  return categoryUrl;
}

// --- parsowanie jednej strony listingu (bez brania ranku jako tickera)
async function scrapeListingPage(page) {
  try {
    await page.waitForFunction(() => !!document.querySelector("table tr td"), { timeout: 12000 });
  } catch {}

  const res = await page.evaluate(() => {
    const clean = (s) => (s || "").replace(/\s+/g, " ").trim();
    const abs = (href) => {
      if (!href) return "";
      if (href.startsWith("http")) return href;
      return new URL(href, location.origin).toString();
    };

    const h1 = document.querySelector("h1");
    const page_title = clean(h1 ? h1.textContent : "");

    const tables = Array.from(document.querySelectorAll("table"));
    if (!tables.length) return { page_title, rows: [], debug: { reason: "no_table" } };

    const scoreTable = (t) => {
      const ths = Array.from(t.querySelectorAll("thead th")).map((x) => clean(x.textContent).toLowerCase());
      const hasName = ths.some((h) => h.includes("name") || h.includes("company"));
      const hasCap = ths.some((h) => h.includes("market cap") || h.includes("marketcap"));
      const tdCount = t.querySelectorAll("tr td").length;
      let score = tdCount;
      if (hasName) score += 5000;
      if (hasCap) score += 5000;
      return score;
    };

    let best = tables[0];
    let bestScore = scoreTable(best);
    for (const t of tables.slice(1)) {
      const sc = scoreTable(t);
      if (sc > bestScore) {
        best = t;
        bestScore = sc;
      }
    }

    const headers = Array.from(best.querySelectorAll("thead th")).map((x) => clean(x.textContent).toLowerCase());
    const idxOf = (pred) => {
      const i = headers.findIndex(pred);
      return i >= 0 ? i : null;
    };

    const nameIdx = idxOf((h) => h.includes("name") || h.includes("company"));
    const capIdx = idxOf((h) => h.includes("market cap") || h.includes("marketcap"));
    const rankIdx = idxOf((h) => h === "#" || h.includes("rank"));

    const fallbackRankIdx = 0;
    const fallbackNameIdx = 1;

    let rows = Array.from(best.querySelectorAll("tbody tr"));
    if (!rows.length) {
      rows = Array.from(best.querySelectorAll("tr")).filter((tr) => tr.querySelectorAll("td").length >= 2);
    }

    // ticker rules:
    // - nie może być gołą liczbą (bo wtedy łapiesz ranking)
    // - musi mieć literę LUB kropkę (np. 0700.HK) — same cyfry odpadają
    const isTickerCore = (t) => /^[A-Z0-9][A-Z0-9.\-]{0,18}$/.test(t);
    const hasLetter = (t) => /[A-Z]/.test(t);
    const hasDot = (t) => /\./.test(t);
    const isPureDigits = (t) => /^[0-9]+$/.test(t);

    function extractTickerFromNameCell(td) {
      if (!td) return "";

      // 1) elementy wyglądające na ticker/symbol/code
      const candidates = [];
      const nodes = td.querySelectorAll("span, small, div");
      for (const n of nodes) {
        const cls = (n.getAttribute("class") || "").toLowerCase();
        const txt = clean(n.textContent || "").toUpperCase();
        if (!txt) continue;
        if (!isTickerCore(txt)) continue;

        const classLooksTicker = /ticker|symbol|code/.test(cls);
        const ok =
          !isPureDigits(txt) && (hasLetter(txt) || hasDot(txt)); // tu nadal odrzucamy same cyfry

        if (!ok) continue;
        candidates.push({ txt, prio: classLooksTicker ? 2 : 1 });
      }
      if (candidates.length) {
        candidates.sort((a, b) => b.prio - a.prio || a.txt.length - b.txt.length);
        return candidates[0].txt;
      }

      // 2) fallback: ostatni token z tekstu komórki
      const full = clean(td.textContent || "").toUpperCase();
      if (!full) return "";

      const tokens = full.split(" ").filter(Boolean);
      for (let i = tokens.length - 1; i >= 0; i--) {
        const t = tokens[i];
        if (!isTickerCore(t)) continue;
        if (isPureDigits(t)) continue; // krytyczne: nie bierz ranku
        if (!(hasLetter(t) || hasDot(t))) continue;
        return t;
      }
      return "";
    }

    function removeTrailingTicker(nameText, ticker) {
      const n = clean(nameText);
      if (!ticker) return n;
      const t = ticker.trim().toUpperCase();
      const up = n.toUpperCase();
      if (up.endsWith(" " + t)) return clean(n.slice(0, n.length - (t.length + 1)));
      if (up.endsWith(t)) return clean(n.slice(0, n.length - t.length));
      return n;
    }

    const parsed = [];

    for (const tr of rows) {
      const tds = Array.from(tr.querySelectorAll("td"));
      if (tds.length < 2) continue;

      const rIdx = rankIdx != null ? rankIdx : fallbackRankIdx;
      const nIdx = nameIdx != null ? nameIdx : fallbackNameIdx;

      const rank = clean(tds[rIdx]?.textContent || "");

      const nameTd = tds[nIdx];
      if (!nameTd) continue;

      const a = nameTd.querySelector("a[href]");
      const company_url = a ? abs(a.getAttribute("href")) : "";

      const rawName = clean((a ? a.textContent : nameTd.textContent) || "");
      if (!rawName) continue;

      const ticker = extractTickerFromNameCell(nameTd);
      if (!ticker) continue;

      const company_name = removeTrailingTicker(rawName, ticker);

      let market_cap = "";
      if (capIdx != null && tds[capIdx]) {
        market_cap = clean(tds[capIdx].textContent || "");
      }
      if (!market_cap) {
        for (let i = 0; i < tds.length; i++) {
          const tx = clean(tds[i].textContent || "");
          if (tx.includes("$")) {
            market_cap = tx;
            break;
          }
        }
      }

      parsed.push({ rank, company_name, ticker, market_cap, company_url });
    }

    return {
      page_title,
      rows: parsed,
      debug: {
        headers,
        nameIdx,
        capIdx,
        rankIdx,
        rowCount: rows.length,
        chosenTableTdCount: best.querySelectorAll("tr td").length,
      },
    };
  });

  return res;
}

// --- scrap TOP N z listingu (wielostronicowo), resume z danych (max(page)+1)
async function scrapeTopFromListing(page, listingUrl, limit, prevEntry) {
  const dane = prevEntry?.dane && typeof prevEntry.dane === "object" ? { ...prevEntry.dane } : {};
  const spolki = Array.isArray(prevEntry?.spolki) ? [...prevEntry.spolki] : [];
  const seen = new Set(spolki);

  let currentPage = 1;
  // resume po stronach: weź max(page) z istniejących danych
  const pages = Object.values(dane)
    .map((x) => x && x.page)
    .filter((p) => Number.isFinite(p));
  if (pages.length) currentPage = Math.max(...pages) + 1;

  // jeśli nie mamy nic, start od 1
  if (!spolki.length) currentPage = 1;

  let guardSameFirst = null;

  while (spolki.length < limit) {
    const url =
      currentPage === 1
        ? listingUrl
        : `${listingUrl}${listingUrl.includes("?") ? "&" : "?"}page=${currentPage}`;

    await page.goto(url, { waitUntil: "domcontentloaded", timeout: NAV_TIMEOUT });
    await sleep(rand(500, 1100));
    await acceptCookiesIfAny(page);
    await sleep(rand(120, 320));

    const batch = await scrapeListingPage(page);

    if (DEBUG) {
      console.log(`[debug] page=${currentPage} rows=${batch.rows?.length || 0}`);
      if (batch.debug) console.log("[debug] table:", batch.debug);
    }

    if (!batch.rows || batch.rows.length === 0) break;

    const first = batch.rows[0];
    const firstKey = `${first.ticker}|${first.company_url}|${first.market_cap}`;
    if (guardSameFirst && guardSameFirst === firstKey) break;
    guardSameFirst = firstKey;

    let addedOnPage = 0;

    for (const r of batch.rows) {
      const t = (r.ticker || "").trim();
      if (!t) continue;
      if (seen.has(t)) continue;

      seen.add(t);
      spolki.push(t);
      dane[t] = {
        rank: r.rank || "",
        company_name: r.company_name || "",
        market_cap: r.market_cap || "",
        company_url: r.company_url || "",
        page: currentPage,
      };

      addedOnPage += 1;
      if (spolki.length >= limit) break;
    }

    // jeśli nic nie dodaliśmy, nie miel kolejnych stron w nieskończoność
    if (addedOnPage === 0) break;

    currentPage += 1;

    if (currentPage % LONG_PAUSE_EVERY_PAGES === 0) {
      await sleep(rand(LONG_PAUSE_MIN, LONG_PAUSE_MAX));
    } else {
      await sleep(rand(MIN_SLEEP, MAX_SLEEP));
    }

    if (currentPage > 400) break; // safety
  }

  const trimmedSpolki = spolki.slice(0, limit);
  const trimmedDane = {};
  for (const t of trimmedSpolki) trimmedDane[t] = dane[t];

  return { spolki: trimmedSpolki, dane: trimmedDane };
}

(async () => {
  ensureDir(OUT_DIR);

  if (!fs.existsSync(CATEGORIES_FILE)) {
    console.error("Brak:", CATEGORIES_FILE, "-> uruchom najpierw cmc_get_categories.js");
    process.exit(1);
  }

  const catFile = loadJson(CATEGORIES_FILE);
  const all = catFile.categories || [];
  if (!all.length) {
    console.error("categories.json jest pusty.");
    process.exit(1);
  }

  let selected = [];
  let limit = DEFAULT_LIMIT;
  let outFile = DEFAULT_OUT_FILE(limit);

  if (hasFlag("--all")) {
    selected = all;

    const limStr = await ask(`Ile top spółek na kategorię? [domyślnie ${DEFAULT_LIMIT}]: `);
    limit = limStr.trim() ? Math.max(1, parseInt(limStr.trim(), 10)) : DEFAULT_LIMIT;

    const outName = await ask(`Nazwa pliku wyjściowego? [domyślnie ${path.basename(DEFAULT_OUT_FILE(limit))}]: `);

    outFile = outName.trim()
      ? path.join(OUT_DIR, outName.trim().endsWith(".json") ? outName.trim() : `${outName.trim()}.json`)
      : DEFAULT_OUT_FILE(limit);
  } else {
    console.log("\nWybór kategorii (nie musisz znać slugów).");
    console.log("Wpisz FRAZĘ do wyszukania (np. 'semiconductor', 'bank', 'ai'), potem wybierzesz numerami.");
    console.log("Albo wpisz 'all' żeby pokazać pierwsze 30 i wybrać numerami.\n");

    const q = await ask("Szukaj (fraza / 'all'): ");
    const query = normalize(q);

    let filtered = all;
    if (query && query !== "all") {
      filtered = all.filter((c) => normalize(c.name).includes(query) || normalize(c.slug).includes(query));
      if (!filtered.length) {
        console.log("\nNic nie znaleziono. Pokażę pierwsze 30 z całej listy.\n");
        filtered = all;
      }
    }

    console.log("\nKategorie (pierwsze 30):");
    showCategories(filtered, 30);

    const pick = await ask("\nWybierz numerami (np. 1,3,5-8): ");
    selected = pickByNumbers(pick, filtered);

    if (!selected.length) {
      console.log("Nie wybrano kategorii. Koniec.");
      process.exit(0);
    }

    const limStr = await ask(`Ile top spółek na kategorię? [domyślnie ${DEFAULT_LIMIT}]: `);
    limit = limStr.trim() ? Math.max(1, parseInt(limStr.trim(), 10)) : DEFAULT_LIMIT;

    const outName = await ask(`Nazwa pliku wyjściowego? [domyślnie ${path.basename(DEFAULT_OUT_FILE(limit))}]: `);

    outFile = outName.trim()
      ? path.join(OUT_DIR, outName.trim().endsWith(".json") ? outName.trim() : `${outName.trim()}.json`)
      : DEFAULT_OUT_FILE(limit);
  }

  // Wczytaj istniejący output (resume)
  let result = {};
  if (fs.existsSync(outFile)) {
    try {
      const loaded = loadJson(outFile);
      if (loaded && typeof loaded === "object") result = loaded;
    } catch {}
  }

  const browser = await puppeteer.launch({
    headless: false,
    defaultViewport: null,
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
  });

  const page = await browser.newPage();
  page.setDefaultNavigationTimeout(NAV_TIMEOUT);

  // UA pomaga na niektórych setupach
  await page.setUserAgent(
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
  );
  await page.setExtraHTTPHeaders({ "accept-language": "en-US,en;q=0.9,pl;q=0.8" });

  for (let i = 0; i < selected.length; i++) {
    const c = selected[i];
    console.log(`[${i + 1}/${selected.length}] ${c.name}`);

    const prev = result[c.slug];
    const prevCount = Array.isArray(prev?.spolki) ? prev.spolki.length : 0;
    if (prevCount >= limit) continue;

    // jeśli to listing, nie wołaj resolveListingUrl (to było źródłem crasha)
    const listingUrl = isListingUrl(c.url) ? c.url : await resolveListingUrl(page, c.url);

    const scraped = await scrapeTopFromListing(page, listingUrl, limit, prev);

    // ✅ WYMAGANY FORMAT: category to nazwa (string)
    result[c.slug] = {
      category: c.name,
      listing_url: listingUrl,
      spolki: scraped.spolki,
      dane: scraped.dane,
    };

    // checkpoint po każdej kategorii
    saveJson(outFile, result);

    await sleep(rand(700, 1500));
  }

  await browser.close();
  console.log(`\nZapisano: ${outFile}`);
})();
