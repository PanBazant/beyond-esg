// symbols_by_letter_strict_checkpoint.js
// Scrape https://stocktwits.com/symbol by letters (A-Z), infinite scroll per letter,
// collect: symbol + symbol_href + company_name + company_href + industry + market_cap
// Checkpoints: during letter + after each letter + final JSON.

const puppeteer = require("puppeteer");
const fs = require("fs");

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const rand = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;

const URL = "https://stocktwits.com/symbol";
const LETTERS = "abcdefghijklmnopqrstuvwxyz".split("");

// scroll/ekstrakcja per litera
const MAX_STEPS_PER_LETTER = 12000;
const EXTRACT_EVERY = 8;          // co ile kroków scrolla ekstrakcja
const MAX_NO_NEW_EXTRACTS = 70;   // ile ekstrakcji bez nowych = stop

// checkpointy W TRAKCIE litery
const CHECKPOINT_EVERY_EXTRACTS = 25; // co ile ekstrakcji zapis (np. 25)
const CHECKPOINT_MIN_SECONDS = 0;     // 0 = wyłącz; np. 120 = zapis co 2 min

// pliki
const PARTIAL_FILE = "symbols_table_partial.json";
const FINAL_FILE = "symbols_table.json";

function saveJson(map, filename) {
  const rows = Array.from(map.values()).sort((a, b) => a.symbol.localeCompare(b.symbol));
  fs.writeFileSync(filename, JSON.stringify(rows, null, 2), "utf-8");
  return rows.length;
}

async function extractRows(page) {
  return await page.evaluate(() => {
    const clean = (s) => (s || "").replace(/\s+/g, " ").trim();
    const toAbs = (href) => {
      if (!href) return "";
      if (href.startsWith("http")) return href;
      try {
        return new URL(href, location.origin).toString();
      } catch {
        return href;
      }
    };

    const out = [];

    // wariant 1: <table>
    const trs = Array.from(document.querySelectorAll("table tbody tr"));
    for (const tr of trs) {
      const tds = Array.from(tr.querySelectorAll("td"));
      if (tds.length < 4) continue;

      const symbol = clean(tds[0]?.innerText);
      const symbolLink = tds[0]?.querySelector('a[href]')?.getAttribute("href") || "";

      const company_name = clean(tds[1]?.innerText);
      const companyLink = tds[1]?.querySelector('a[href]')?.getAttribute("href") || "";

      const industry = clean(tds[2]?.innerText);
      const market_cap = clean(tds[3]?.innerText);

      if (!symbol) continue;

      out.push({
        symbol: symbol.toUpperCase(),
        symbol_href: toAbs(symbolLink),
        company_name,
        company_href: toAbs(companyLink),
        industry,
        market_cap,
      });
    }

    // fallback: role=row/cell (div-table)
    if (out.length === 0) {
      const rows = Array.from(document.querySelectorAll('[role="row"]'));
      for (const r of rows) {
        const cells = Array.from(r.querySelectorAll('[role="cell"]'));
        if (cells.length < 4) continue;

        const symbol = clean(cells[0]?.innerText);
        const symbolLink = cells[0]?.querySelector('a[href]')?.getAttribute("href") || "";

        const company_name = clean(cells[1]?.innerText);
        const companyLink = cells[1]?.querySelector('a[href]')?.getAttribute("href") || "";

        const industry = clean(cells[2]?.innerText);
        const market_cap = clean(cells[3]?.innerText);

        if (!symbol) continue;

        out.push({
          symbol: symbol.toUpperCase(),
          symbol_href: toAbs(symbolLink),
          company_name,
          company_href: toAbs(companyLink),
          industry,
          market_cap,
        });
      }
    }

    return out;
  });
}

async function clickLetterStrict(page, letter) {
  return await page.evaluate((ltr) => {
    const want = String(ltr).toLowerCase();
    const nodes = Array.from(
      document.querySelectorAll('[class*="SymbolsListingPageContent_letterBase__"]')
    );

    const target = nodes.find((el) => (el.textContent || "").trim().toLowerCase() === want);
    if (!target) return false;

    target.scrollIntoView({ block: "center" });
    target.click();
    return true;
  }, letter);
}

async function waitSelectedLetter(page, letter, timeoutMs = 8000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    const selected = await page.evaluate(() => {
      const sel = document.querySelector('[class*="SymbolsListingPageContent_selectedLetter__"]');
      return (sel?.textContent || "").trim().toLowerCase();
    });
    if (selected === letter.toLowerCase()) return true;
    await sleep(150);
  }
  return false;
}

function mergeBatch(store, batch) {
  let added = 0;

  for (const r of batch) {
    if (!r?.symbol) continue;

    if (!store.has(r.symbol)) {
      store.set(r.symbol, r);
      added++;
    } else {
      const cur = store.get(r.symbol);

      if (!cur.company_name && r.company_name) cur.company_name = r.company_name;
      if (!cur.industry && r.industry) cur.industry = r.industry;
      if ((!cur.market_cap || cur.market_cap === "-") && r.market_cap) cur.market_cap = r.market_cap;

      if (!cur.symbol_href && r.symbol_href) cur.symbol_href = r.symbol_href;
      if (!cur.company_href && r.company_href) cur.company_href = r.company_href;
    }
  }

  return added;
}

async function processLetter(page, letter, store) {
  console.log(`\n=== LETTER ${letter.toUpperCase()} ===`);

  await page.evaluate(() => window.scrollTo(0, 0));
  await sleep(500);

  const clicked = await clickLetterStrict(page, letter);
  if (!clicked) {
    console.log(`(warn) cannot find letter node for: ${letter}`);
    return;
  }

  const okSel = await waitSelectedLetter(page, letter);
  if (!okSel) console.log(`(warn) selected letter did not switch to ${letter} (continuing)`);

  // daj chwilę na render listy dla litery
  await sleep(900);

  let noNewExtracts = 0;
  let extracts = 0;

  // checkpoint czasowy
  let lastCheckpointTs = Date.now();

  for (let step = 1; step <= MAX_STEPS_PER_LETTER; step++) {
    const scrollBy = (step % 14 === 0) ? rand(900, 1400) : rand(220, 520);
    await page.evaluate((s) => window.scrollBy(0, s), scrollBy);
    await sleep(rand(220, 600));
    if (step % 12 === 0) await sleep(rand(1200, 2400));

    if (step % EXTRACT_EVERY === 0) {
      extracts++;

      const batch = await extractRows(page);
      const added = mergeBatch(store, batch);

      if (added === 0) noNewExtracts++;
      else noNewExtracts = 0;

      if (extracts % 10 === 0) {
        console.log(
          `[${letter.toUpperCase()} step ${step}] total=${store.size} (+${added}) noNew=${noNewExtracts} extracts=${extracts}`
        );
      }

      // checkpoint po liczbie ekstrakcji
      if (CHECKPOINT_EVERY_EXTRACTS > 0 && extracts % CHECKPOINT_EVERY_EXTRACTS === 0) {
        const n = saveJson(store, PARTIAL_FILE);
        lastCheckpointTs = Date.now();
        console.log(`Checkpoint (in-letter) -> ${PARTIAL_FILE} (${n} rows)`);
      }

      // checkpoint po czasie
      if (CHECKPOINT_MIN_SECONDS > 0) {
        const elapsedSec = (Date.now() - lastCheckpointTs) / 1000;
        if (elapsedSec >= CHECKPOINT_MIN_SECONDS) {
          const n = saveJson(store, PARTIAL_FILE);
          lastCheckpointTs = Date.now();
          console.log(`Checkpoint (time) -> ${PARTIAL_FILE} (${n} rows)`);
        }
      }

      if (noNewExtracts >= MAX_NO_NEW_EXTRACTS) {
        console.log(`Stop ${letter.toUpperCase()} (no new rows)`);
        break;
      }
    }
  }

  // checkpoint po literze
  const n = saveJson(store, PARTIAL_FILE);
  console.log(`Checkpoint after ${letter.toUpperCase()} -> ${PARTIAL_FILE} (${n} rows)`);
}

(async () => {
  console.log("START");

  const browser = await puppeteer.launch({ headless: false, defaultViewport: null });
  const page = await browser.newPage();

  await page.goto(URL, { waitUntil: "domcontentloaded", timeout: 0 });
  await sleep(2500);

  const store = new Map();

  // initial: to co widać na start
  const init = await extractRows(page);
  mergeBatch(store, init);
  console.log("Initial rows:", store.size);

  for (const letter of LETTERS) {
    await processLetter(page, letter, store);
  }

  const final = saveJson(store, FINAL_FILE);
  console.log(`\nSaved final -> ${FINAL_FILE} (${final} rows)`);

  await browser.close();
  console.log("DONE");
})();
