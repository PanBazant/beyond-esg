// stocktwits_batch_scrape_sample_fixed.js
// Node 18+
// npm i puppeteer
//
// RUN: node stocktwits_batch_scrape_sample_fixed.js

const puppeteer = require("puppeteer");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

// ====================== CONFIG (NA SZTYWNO) ======================
const CONFIG = {
  // input: TWOJA PRÓBKA BADAWCZA (po merge)
  MERGED_JSONL_FILE: "./merged_flat_stocktwits.jsonl",

  // output
  OUT_ROOT: "./media_sample",
  PROGRESS_FILE: "./batch_progress_sample.json",

  // browser
  HEADLESS: false, // domyślnie HEADFUL, żebyś widział co się dzieje

  // 0 = wszystkie z próbki, inaczej limit
  LIMIT_SYMBOLS: 0,

  // per-symbol scraping
  SCRAPE_STEPS: 420,
  EXTRACT_EVERY: 10,
  STOP_IF_NO_NEW_FOR_EXTRACTS: 5,

  // scroll/pause tuning
  STEP_MIN: 140,
  STEP_MAX: 320,
  PAUSE_MIN: 280,
  PAUSE_MAX: 700,
  BIG_PAUSE_EVERY: 12,
  BIG_PAUSE_MIN: 1400,
  BIG_PAUSE_MAX: 2600,

  // media download
  MEDIA_CONCURRENCY: 4,
  TIMEOUT_MS: 25000,
  MAX_MEDIA_PER_MESSAGE: 8,

  // between symbols
  BETWEEN_SYMBOLS_MIN_MS: 2000,
  BETWEEN_SYMBOLS_MAX_MS: 6000,

  // timeout na page.goto (ms) — restart przeglądarki gdy Cloudflare blokuje ładowanie
  GOTO_TIMEOUT_MS: 15000,
};
// ================================================================

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const rand = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;

function ensureDir(p) {
  fs.mkdirSync(p, { recursive: true });
}

function safeReadJson(p) {
  try {
    if (!fs.existsSync(p)) return null;
    return JSON.parse(fs.readFileSync(p, "utf8"));
  } catch {
    return null;
  }
}

function writeJson(p, obj) {
  ensureDir(path.dirname(p));
  fs.writeFileSync(p, JSON.stringify(obj, null, 2), "utf8");
}

function runTagUtc() {
  return new Date().toISOString().replaceAll(":", "-").replace(".000", "").replace("T", "_");
}

function sanitizeFilename(name) {
  return String(name)
    .replace(/[<>:"/\\|?*\x00-\x1F]/g, "_")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 140);
}

function sha1(s) {
  return crypto.createHash("sha1").update(String(s)).digest("hex").slice(0, 12);
}

function extFromUrl(url, fallback) {
  try {
    const u = new URL(url);
    const base = path.basename(u.pathname);
    const ext = path.extname(base).toLowerCase();
    if (ext && ext.length <= 6) return ext;
  } catch {}
  return fallback;
}

function uniqByKey(arr, keyFn) {
  const m = new Map();
  for (const x of arr || []) {
    const k = keyFn(x);
    if (!k) continue;
    if (!m.has(k)) m.set(k, x);
  }
  return Array.from(m.values());
}

function mergeMessage(prev, next) {
  const out = { ...(prev || {}) };

  out.id = next.id || out.id;
  out.url = next.url || out.url;
  out.username = next.username || out.username;
  out.datetime = out.datetime || next.datetime || "";

  const prevText = out.text || "";
  const nextText = next.text || "";
  out.text = nextText.length > prevText.length ? nextText : prevText;

  const prevMedia = Array.isArray(out.media) ? out.media : [];
  const nextMedia = Array.isArray(next.media) ? next.media : [];
  out.media = uniqByKey([...prevMedia, ...nextMedia], (m) => `${m.type}:${m.src}`);

  const prevEmbeds = Array.isArray(out.embeds) ? out.embeds : [];
  const nextEmbeds = Array.isArray(next.embeds) ? next.embeds : [];
  const byId = new Map(prevEmbeds.map((e) => [e.id, e]));

  for (const e of nextEmbeds) {
    if (!e?.id) continue;
    if (!byId.has(e.id)) {
      byId.set(e.id, e);
    } else {
      const cur = byId.get(e.id);
      const curText = cur.text || "";
      const eText = e.text || "";
      cur.text = eText.length > curText.length ? eText : curText;
      cur.datetime = cur.datetime || e.datetime || "";
      cur.url = cur.url || e.url || "";
      cur.username = cur.username || e.username || "";

      const curMedia = Array.isArray(cur.media) ? cur.media : [];
      const eMedia = Array.isArray(e.media) ? e.media : [];
      cur.media = uniqByKey([...curMedia, ...eMedia], (m) => `${m.type}:${m.src}`);

      byId.set(e.id, cur);
    }
  }

  out.embeds = Array.from(byId.values());
  out._updated_at = new Date().toISOString();
  out._first_seen_at = out._first_seen_at || out._updated_at;

  return out;
}

async function fetchWithTimeout(url, opts = {}) {
  const controller = new AbortController();
  const t = setTimeout(() => controller.abort(), CONFIG.TIMEOUT_MS);
  try {
    return await fetch(url, { ...opts, signal: controller.signal });
  } finally {
    clearTimeout(t);
  }
}

async function downloadToFile(url, outPath) {
  if (fs.existsSync(outPath)) return { ok: true, skipped: true };

  const res = await fetchWithTimeout(url, {
    headers: {
      "User-Agent": "Mozilla/5.0 (compatible; media-downloader/1.0)",
      Accept: "*/*",
    },
  });

  if (!res.ok) return { ok: false, status: res.status, statusText: res.statusText };

  const buf = Buffer.from(await res.arrayBuffer());
  ensureDir(path.dirname(outPath));
  fs.writeFileSync(outPath, buf);
  return { ok: true, skipped: false, bytes: buf.length };
}

function createLimiter(concurrency) {
  let active = 0;
  const queue = [];

  const runNext = () => {
    if (active >= concurrency) return;
    const job = queue.shift();
    if (!job) return;

    active++;
    job()
      .catch(() => {})
      .finally(() => {
        active--;
        runNext();
      });
  };

  return (fn) =>
    new Promise((resolve, reject) => {
      queue.push(async () => {
        try {
          const r = await fn();
          resolve(r);
        } catch (e) {
          reject(e);
        }
      });
      runNext();
    });
}

// ---------------- DOM EXTRACTOR ----------------
async function extractFromDom(page) {
  return await page.evaluate(() => {
    const toAbs = (href) => {
      if (!href) return "";
      if (href.startsWith("http")) return href;
      return `${location.origin}${href}`;
    };

    const getMsgIdFromHref = (href) => {
      if (!href) return null;
      const m = href.match(/\/message\/(\d+)/);
      return m ? m[1] : null;
    };

    const getText = (root) => {
      const body = root.querySelector(".RichTextMessage_body__4qUeP");
      return (body?.innerText || "").trim();
    };

    const parseHeader = (root) => {
      const userEl =
        root.querySelector('[aria-label="Username"]') ||
        root.querySelector('[data-testid="message-header"] [href^="/"] span');

      const username = (userEl?.textContent || "").trim();

      const linkEl = root.querySelector('a[href*="/message/"]');
      const href = linkEl?.getAttribute("href") || "";
      const url = toAbs(href);
      const id = getMsgIdFromHref(href);

      const timeEl = root.querySelector("time[datetime]");
      const datetime = timeEl?.getAttribute("datetime") || "";

      return { id, url, username, datetime };
    };

    const parseMedia = (root) => {
      const out = [];

      root.querySelectorAll("video source[src]").forEach((s) => {
        out.push({ type: "video", src: s.getAttribute("src") });
      });

      root.querySelectorAll("img[src]").forEach((img) => {
        const src = img.getAttribute("src") || "";
        const isAvatar =
          src.includes("avatars.stocktwits-cdn.com") || src.includes("default_avatar");
        const isLogo = src.includes("logos.stocktwits-cdn.com");
        if (!src || isAvatar || isLogo) return;
        out.push({ type: "image", src });
      });

      const uniq = new Map();
      for (const m of out) uniq.set(`${m.type}:${m.src}`, m);
      return Array.from(uniq.values());
    };

    const parseEmbeds = (msgRoot, parentId) => {
      const embedRoots = msgRoot.querySelectorAll(".StreamMessageEmbed_message__cRdEE");
      const embeds = [];

      embedRoots.forEach((er) => {
        const header = parseHeader(er);
        const text = getText(er);
        const media = parseMedia(er);

        if (header.id && header.id !== parentId) {
          embeds.push({ ...header, text, media });
        }
      });

      return embeds;
    };

    const roots = Array.from(document.querySelectorAll('div[data-testid^="message-"]'));

    const messages = roots
      .map((r) => {
        const header = parseHeader(r);
        if (!header.id) return null;

        const text = getText(r);
        const media = parseMedia(r);
        const embeds = parseEmbeds(r, header.id);

        return { ...header, text, media, embeds };
      })
      .filter(Boolean);

    const byId = new Map();
    for (const m of messages) {
      if (!byId.has(m.id)) byId.set(m.id, m);
    }

    return Array.from(byId.values());
  });
}

function buildAllMediaList(msg) {
  const base = Array.isArray(msg.media) ? msg.media : [];
  const embedMedia = (Array.isArray(msg.embeds) ? msg.embeds : []).flatMap((e) =>
    Array.isArray(e.media) ? e.media : []
  );
  const all = uniqByKey([...base, ...embedMedia], (m) => `${m.type}:${m.src}`);
  return all.slice(0, CONFIG.MAX_MEDIA_PER_MESSAGE);
}

// ---------------- SYMBOL LIST FROM MERGED JSONL ----------------
function loadSymbolsFromMergedJsonl(p) {
  const lines = fs.readFileSync(p, "utf8").split(/\r?\n/).filter(Boolean);
  const out = [];

  for (const ln of lines) {
    let obj;
    try { obj = JSON.parse(ln); } catch { continue; }
    const s1 = obj.st_url_symbol;
    const s2 = obj.st_symbol;

    if (typeof s1 === "string" && s1.trim()) {
      out.push(s1.trim());
    } else if (typeof s2 === "string" && s2.trim()) {
      out.push(s2.trim().replace(/-/g, "."));
    }
  }

  return [...new Set(out)];
}

// ---------------- PER-SYMBOL SCRAPE ----------------
async function scrapeOneSymbol(browser, symbol, progress) {
  const SYMBOL = symbol;
  const PAGE_URL = `https://stocktwits.com/symbol/${SYMBOL}`;

  const RUN_TAG = runTagUtc();
  const RUN_ROOT = path.join(CONFIG.OUT_ROOT, SYMBOL, "runs", RUN_TAG);
  const OUT_MESSAGES_ROOT = path.join(RUN_ROOT, "messages");
  ensureDir(OUT_MESSAGES_ROOT);

  const page = await browser.newPage();
  await page.goto(PAGE_URL, { waitUntil: "domcontentloaded", timeout: CONFIG.GOTO_TIMEOUT_MS });
  await sleep(5000);

  // Cloudflare detection
  const [pageTitle, currentUrl, hasCfForm, hasCfWidget] = await Promise.all([
    page.title(),
    Promise.resolve(page.url()),
    page.$('#challenge-form').then(Boolean),
    page.$('[data-translate], [class*="cf-"], #cf-wrapper, #cf-content').then(Boolean),
  ]);

  const isCfBlocked =
    /just a moment|cloudflare|attention required|checking your browser|enable javascript/i.test(pageTitle) ||
    currentUrl.includes("challenges.cloudflare.com") ||
    hasCfForm ||
    hasCfWidget;

  if (isCfBlocked) {
    console.log(`[CF] blocked — title: "${pageTitle}" url: ${currentUrl}`);
    await page.close();
    throw new Error(`Cloudflare block (title: "${pageTitle}")`);
  }

  const limit = createLimiter(CONFIG.MEDIA_CONCURRENCY);

  let newCountSinceStart = 0;
  let extractsWithoutNew = 0;

  const upsertOne = async (msg) => {
    const msgId = String(msg.id || "").trim();
    if (!msgId) return { ok: false };

    const folder = path.join(OUT_MESSAGES_ROOT, sanitizeFilename(msgId));
    const metaPath = path.join(folder, "meta.json");
    ensureDir(folder);

    const prev = safeReadJson(metaPath);
    const merged = mergeMessage(prev, msg);
    const wasNew = !prev;

    writeJson(metaPath, merged);

    const mediaList = buildAllMediaList(merged);
    const prevFiles = Array.isArray(merged.files) ? merged.files : [];
    const fileKey = new Set(prevFiles.map((f) => `${f.media_type}:${f.media_src}`));
    const files = [...prevFiles];

    const tasks = mediaList.map((m) =>
      limit(async () => {
        if (!m?.src || !m?.type) return null;
        const k = `${m.type}:${m.src}`;
        if (fileKey.has(k)) return null;

        const h = sha1(m.src);
        const fallbackExt = m.type === "video" ? ".mp4" : ".webp";
        const ext = extFromUrl(m.src, fallbackExt);
        const filename = `${m.type}_${h}${ext}`;
        const outPath = path.join(folder, filename);

        const r = await downloadToFile(m.src, outPath);

        files.push({
          media_type: m.type,
          media_src: m.src,
          saved_as: path.relative(RUN_ROOT, outPath).replace(/\\/g, "/"),
          ok: !!r.ok,
          skipped: !!r.skipped,
          bytes: r.bytes || 0,
          status: r.status || null,
        });

        fileKey.add(k);
        await sleep(120);
        return true;
      })
    );

    await Promise.allSettled(tasks);
    merged.files = files;
    writeJson(metaPath, merged);

    return { ok: true, wasNew };
  };

  for (let i = 1; i <= CONFIG.SCRAPE_STEPS; i++) {
    await page.evaluate((s) => window.scrollBy(0, s), rand(CONFIG.STEP_MIN, CONFIG.STEP_MAX));
    await sleep(rand(CONFIG.PAUSE_MIN, CONFIG.PAUSE_MAX));

    if (CONFIG.BIG_PAUSE_EVERY > 0 && i % CONFIG.BIG_PAUSE_EVERY === 0) {
      await sleep(rand(CONFIG.BIG_PAUSE_MIN, CONFIG.BIG_PAUSE_MAX));
    }

    if (i % CONFIG.EXTRACT_EVERY === 0) {
      const batch = await extractFromDom(page);

      let batchNew = 0;
      for (const msg of batch) {
        try {
          const r = await upsertOne(msg);
          if (r.ok && r.wasNew) {
            batchNew++;
            newCountSinceStart++;
          }
        } catch {}
      }

      if (CONFIG.STOP_IF_NO_NEW_FOR_EXTRACTS > 0) {
        if (batchNew === 0) extractsWithoutNew++;
        else extractsWithoutNew = 0;

        if (extractsWithoutNew >= CONFIG.STOP_IF_NO_NEW_FOR_EXTRACTS) break;
      }
    }
  }

  // index.json
  const index = [];
  const msgDirs = fs
    .readdirSync(OUT_MESSAGES_ROOT, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .map((d) => d.name);

  for (const d of msgDirs) {
    const meta = safeReadJson(path.join(OUT_MESSAGES_ROOT, d, "meta.json"));
    if (!meta?.id) continue;

    index.push({
      message_id: String(meta.id),
      username: meta.username || "unknown",
      datetime: meta.datetime || "",
      message_url: meta.url || `https://stocktwits.com/message/${meta.id}`,
      folder: path.relative(RUN_ROOT, path.join(OUT_MESSAGES_ROOT, d)).replace(/\\/g, "/"),
      files_count: Array.isArray(meta.files) ? meta.files.length : 0,
      first_seen_at: meta._first_seen_at || "",
      updated_at: meta._updated_at || "",
    });
  }

  index.sort((a, b) => (b.datetime || "").localeCompare(a.datetime || ""));
  writeJson(path.join(RUN_ROOT, "index.json"), index);

  await page.close();

  // progress update
  progress.done.push(SYMBOL);
  progress.last_symbol = SYMBOL;
  progress.updated_at = new Date().toISOString();
  writeJson(CONFIG.PROGRESS_FILE, progress);

  return { symbol: SYMBOL, run_root: RUN_ROOT, new_messages_seen: newCountSinceStart, messages_saved: msgDirs.length };
}

// ---------------- BROWSER HELPERS ----------------
function launchBrowser() {
  return puppeteer.launch({
    headless: CONFIG.HEADLESS,
    defaultViewport: null,
    args: [
      "--start-maximized",
      "--disable-blink-features=AutomationControlled",
      "--no-sandbox",
    ],
    ignoreDefaultArgs: ["--enable-automation"],
  });
}

async function closeBrowser(browser) {
  try { await browser.close(); } catch {}
  try { browser.process()?.kill("SIGKILL"); } catch {}
}

// ---------------- MAIN ----------------
async function main() {
  const continueRun = process.argv.includes("--continue");

  const symbolsAll = loadSymbolsFromMergedJsonl(CONFIG.MERGED_JSONL_FILE);
  const symbols = CONFIG.LIMIT_SYMBOLS > 0 ? symbolsAll.slice(0, CONFIG.LIMIT_SYMBOLS) : symbolsAll;

  let progress;
  if (continueRun) {
    progress = safeReadJson(CONFIG.PROGRESS_FILE) || { done: [], failed: [], last_symbol: null, updated_at: null };
  } else {
    progress = { done: [], failed: [], last_symbol: null, updated_at: null };
    writeJson(CONFIG.PROGRESS_FILE, progress);
  }

  const doneSet = new Set(progress.done || []);
  const failedSet = new Set((progress.failed || []).map((x) => x.symbol));

  const todo = continueRun
    ? symbols.filter((s) => !doneSet.has(s) && !failedSet.has(s))
    : symbols;

  console.log("=== SAMPLE SCRAPER ===");
  console.log("Input file:", CONFIG.MERGED_JSONL_FILE);
  console.log("Mode:", continueRun ? "CONTINUE (skip done/failed)" : "fresh run (all symbols)");
  console.log("Total symbols:", symbols.length);
  console.log("Already done:", doneSet.size);
  console.log("Already failed:", failedSet.size);
  console.log("To do now:", todo.length);
  console.log("First 20 todo:", todo.slice(0, 20));

  let browser = await launchBrowser();

  for (let i = 0; i < todo.length; i++) {
    const sym = todo[i];
    console.log(`[${i + 1}/${todo.length}] ${sym}`);

    let failed = false;

    try {
      await scrapeOneSymbol(browser, sym, progress);
      console.log("[OK]", sym);
    } catch (e) {
      const err = String(e?.message || e);
      console.log("[FAIL]", sym, err);
      progress.failed = progress.failed || [];
      progress.failed.push({ symbol: sym, error: err, at: new Date().toISOString() });
      progress.updated_at = new Date().toISOString();
      writeJson(CONFIG.PROGRESS_FILE, progress);
      failed = true;
    }

    if (failed) {
      const isCf = (progress.failed?.at(-1)?.error || "").includes("Cloudflare");
      const restartDelay = isCf ? rand(12000, 22000) : 3000;
      console.log(`[RESTART] zamykam przeglądarkę, czekam ${Math.round(restartDelay / 1000)}s...`);
      await closeBrowser(browser);
      await sleep(restartDelay);
      browser = await launchBrowser();
      console.log("[RESTART] przeglądarka gotowa");
    }

    await sleep(rand(CONFIG.BETWEEN_SYMBOLS_MIN_MS, CONFIG.BETWEEN_SYMBOLS_MAX_MS));
  }

  await closeBrowser(browser);
  console.log("Done sample batch.");
}

main().catch((e) => {
  console.error("[FATAL]", e);
  process.exit(1);
});