const puppeteer = require("puppeteer");
const fs = require("fs");
const path = require("path");

const BASE = "https://companiesmarketcap.com";
const START = `${BASE}/all-categories/`;

const OUT_DIR = "cmc_out";
const OUT_FILE = path.join(OUT_DIR, "categories.json");

const NAV_TIMEOUT = 0;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function ensureDir(p) {
  if (!fs.existsSync(p)) fs.mkdirSync(p, { recursive: true });
}

function saveJson(filePath, obj) {
  fs.writeFileSync(filePath, JSON.stringify(obj, null, 2), "utf-8");
}

function toAbs(href) {
  if (!href) return "";
  if (href.startsWith("http")) return href;
  return new URL(href, BASE).toString();
}

async function scrapeCategories(page) {
  await page.goto(START, { waitUntil: "domcontentloaded", timeout: NAV_TIMEOUT });
  await sleep(1200);

  const categories = await page.evaluate(() => {
    const clean = (s) => (s || "").replace(/\s+/g, " ").trim();
    const anchors = Array.from(document.querySelectorAll('a[href]'));
    const out = [];

    for (const a of anchors) {
      const href = (a.getAttribute("href") || "").trim();
      const text = clean(a.textContent);

      if (!href || !text) continue;
      if (!href.startsWith("/")) continue;
      if (href.startsWith("//")) continue;

      const bad = [
        "/all-categories",
        "/all-countries",
        "/country",
        "/index",
        "/etf",
        "/watchlist",
        "/account",
        "/login",
        "/signup",
        "/privacy",
        "/terms",
      ];
      if (bad.some((b) => href.startsWith(b))) continue;

      const looksCategory =
        /^\/[a-z0-9-]+\/$/.test(href) ||
        /^\/[a-z0-9-]+\/largest-[a-z0-9-]+-by-market-cap\/$/.test(href);

      if (!looksCategory) continue;
      out.push({ name: text, href });
    }

    // dedup po slug; preferuj link listingowy "largest-...by-market-cap/"
    const bySlug = new Map();
    for (const item of out) {
      const m1 = item.href.match(/^\/([a-z0-9-]+)\/$/);
      const m2 = item.href.match(/^\/([a-z0-9-]+)\/largest-[a-z0-9-]+-by-market-cap\/$/);
      const slug = (m2 && m2[1]) || (m1 && m1[1]) || null;
      if (!slug) continue;

      const prev = bySlug.get(slug);
      if (!prev) {
        bySlug.set(slug, { slug, name: item.name, href: item.href });
      } else {
        const isListing = item.href.includes("/largest-") && item.href.includes("-by-market-cap/");
        const prevIsListing = prev.href.includes("/largest-") && prev.href.includes("-by-market-cap/");
        if (isListing && !prevIsListing) {
          bySlug.set(slug, { slug, name: prev.name || item.name, href: item.href });
        }
      }
    }

    return Array.from(bySlug.values()).sort((a, b) => a.slug.localeCompare(b.slug));
  });

  return categories.map((c) => ({ ...c, url: toAbs(c.href) }));
}

(async () => {
  ensureDir(OUT_DIR);

  const browser = await puppeteer.launch({
    headless: false,
    defaultViewport: null,
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
  });

  const page = await browser.newPage();
  const categories = await scrapeCategories(page);

  saveJson(OUT_FILE, {
    source: "companiesmarketcap.com",
    created_at: new Date().toISOString(),
    count: categories.length,
    categories,
  });

  console.log("Saved:", OUT_FILE, "count:", categories.length);

  await browser.close();
})();
