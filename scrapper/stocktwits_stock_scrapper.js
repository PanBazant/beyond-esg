// stocktwits_snapshot_scraper.js
// Snapshot scraper: ticker -> runs/<timestamp>/messages/<id>/meta.json + media downloads on the fly
// Stops early if no NEW messages for 5 consecutive extracts.
// Requirements: Node 18+, npm i puppeteer

const puppeteer = require("puppeteer");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

// ---------------- CONFIG ----------------
const SYMBOL = "NVDA";
const PAGE_URL = `https://stocktwits.com/symbol/${SYMBOL}`;

// Scrape tuning
const SCRAPE_STEPS = 420;        // hard max scroll steps (prevents infinite loop)
const EXTRACT_EVERY = 10;        // extract from DOM every N scroll steps
const STEP_MIN = 140;
const STEP_MAX = 320;
const PAUSE_MIN = 280;
const PAUSE_MAX = 700;
const BIG_PAUSE_EVERY = 12;
const BIG_PAUSE_MIN = 1400;
const BIG_PAUSE_MAX = 2600;

// Download tuning
const CONCURRENCY = 4;
const TIMEOUT_MS = 25000;
const MAX_MEDIA_PER_MESSAGE = 8;

// >>> STOP RULE YOU WANTED <<<
const STOP_IF_NO_NEW_FOR_EXTRACTS = 5; // end run if "new==0" for 5 consecutive extracts

// ---------------- UTILS ----------------
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const rand = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;

function ensureDir(p) {
  fs.mkdirSync(p, { recursive: true });
}

function sanitizeFilename(name) {
  return String(name)
    .replace(/[<>:"/\\|?*\x00-\x1F]/g, "_")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 120);
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

function runTagUtc() {
  // 2026-02-21_18-40-12Z
  return new Date()
    .toISOString()
    .replaceAll(":", "-")
    .replace(".000", "")
    .replace("T", "_");
}

function safeReadJson(p) {
  try {
    if (!fs.existsSync(p)) return null;
    return JSON.parse(fs.readFileSync(p, "utf-8"));
  } catch {
    return null;
  }
}

function writeJson(p, obj) {
  ensureDir(path.dirname(p));
  fs.writeFileSync(p, JSON.stringify(obj, null, 2), "utf-8");
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

  // keep first non-empty datetime (stable)
  out.datetime = out.datetime || next.datetime || "";

  // keep longer text
  const prevText = out.text || "";
  const nextText = next.text || "";
  out.text = nextText.length > prevText.length ? nextText : prevText;

  // merge media
  const prevMedia = Array.isArray(out.media) ? out.media : [];
  const nextMedia = Array.isArray(next.media) ? next.media : [];
  out.media = uniqByKey([...prevMedia, ...nextMedia], (m) => `${m.type}:${m.src}`);

  // merge embeds
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
  const t = setTimeout(() => controller.abort(), TIMEOUT_MS);
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
      "Accept": "*/*",
      // If you see lots of 403/429, you can try:
      // "Referer": "https://stocktwits.com/",
    },
  });

  if (!res.ok) return { ok: false, status: res.status, statusText: res.statusText };

  const buf = Buffer.from(await res.arrayBuffer());
  ensureDir(path.dirname(outPath));
  fs.writeFileSync(outPath, buf);
  return { ok: true, skipped: false, bytes: buf.length };
}

// simple concurrency limiter
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

    // Dedup by ID within batch
    const byId = new Map();
    for (const m of messages) {
      if (!byId.has(m.id)) byId.set(m.id, m);
      else {
        const cur = byId.get(m.id);
        if ((m.text || "").length > (cur.text || "").length) cur.text = m.text;

        const mediaKey = new Set((cur.media || []).map((x) => `${x.type}:${x.src}`));
        for (const x of m.media || []) {
          const k = `${x.type}:${x.src}`;
          if (!mediaKey.has(k)) cur.media.push(x);
        }

        const embedKey = new Set((cur.embeds || []).map((e) => e.id));
        for (const e of m.embeds || []) {
          if (e.id && !embedKey.has(e.id)) cur.embeds.push(e);
        }
      }
    }

    return Array.from(byId.values());
  });
}

// ---------------- PIPELINE: UPSERT + DOWNLOAD ----------------
function buildAllMediaList(msg) {
  const base = Array.isArray(msg.media) ? msg.media : [];
  const embedMedia = (Array.isArray(msg.embeds) ? msg.embeds : []).flatMap((e) =>
    Array.isArray(e.media) ? e.media : []
  );

  const all = uniqByKey([...base, ...embedMedia], (m) => `${m.type}:${m.src}`);
  return all.slice(0, MAX_MEDIA_PER_MESSAGE);
}

async function main() {
  const RUN_TAG = runTagUtc();
  const RUN_ROOT = path.join("media", SYMBOL, "runs", RUN_TAG);
  const OUT_MESSAGES_ROOT = path.join(RUN_ROOT, "messages");

  ensureDir(OUT_MESSAGES_ROOT);
  console.log(`[RUN] ${SYMBOL} -> ${RUN_ROOT}`);

  const browser = await puppeteer.launch({ headless: false, defaultViewport: null });
  const page = await browser.newPage();

  await page.goto(PAGE_URL, { waitUntil: "domcontentloaded" });
  await sleep(3000);

  const limit = createLimiter(CONCURRENCY);

  let totalUpserts = 0;
  let newCountSinceStart = 0;
  let extractsWithoutNew = 0;

  const upsertOne = async (msg) => {
    const msgId = String(msg.id || "").trim();
    if (!msgId) return { ok: false, reason: "no_id" };

    const folder = path.join(OUT_MESSAGES_ROOT, sanitizeFilename(msgId));
    const metaPath = path.join(folder, "meta.json");
    ensureDir(folder);

    const prev = safeReadJson(metaPath);
    const merged = mergeMessage(prev, msg);
    const wasNew = !prev;

    // write merged meta immediately
    writeJson(metaPath, merged);

    // download media based on merged (so old media won’t re-download)
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

        const record = {
          media_type: m.type,
          media_src: m.src,
          saved_as: path.relative(RUN_ROOT, outPath).replace(/\\/g, "/"),
          ok: !!r.ok,
          skipped: !!r.skipped,
          bytes: r.bytes || 0,
          status: r.status || null,
        };

        files.push(record);
        fileKey.add(k);

        await sleep(120);
        return record;
      })
    );

    await Promise.allSettled(tasks);

    // store current files back into meta.json
    merged.files = files;
    writeJson(metaPath, merged);

    return { ok: true, wasNew };
  };

  for (let i = 1; i <= SCRAPE_STEPS; i++) {
    await page.evaluate((s) => window.scrollBy(0, s), rand(STEP_MIN, STEP_MAX));
    await sleep(rand(PAUSE_MIN, PAUSE_MAX));
    if (i % BIG_PAUSE_EVERY === 0) await sleep(rand(BIG_PAUSE_MIN, BIG_PAUSE_MAX));

    if (i % EXTRACT_EVERY === 0) {
      const batch = await extractFromDom(page);

      let batchNew = 0;
      for (const msg of batch) {
        try {
          const r = await upsertOne(msg);
          if (r.ok) {
            totalUpserts++;
            if (r.wasNew) {
              batchNew++;
              newCountSinceStart++;
            }
          }
        } catch (e) {
          console.warn("[WARN] upsert failed:", e?.message || e);
        }
      }

      console.log(
        `[step ${i}] extracted: ${batch.length}, new: ${batchNew}, total new: ${newCountSinceStart}, upserts: ${totalUpserts}`
      );

      // --- STOP RULE ---
      if (STOP_IF_NO_NEW_FOR_EXTRACTS > 0) {
        if (batchNew === 0) extractsWithoutNew++;
        else extractsWithoutNew = 0;

        if (extractsWithoutNew >= STOP_IF_NO_NEW_FOR_EXTRACTS) {
          console.log(
            `[STOP] No new messages for ${extractsWithoutNew} consecutive extracts.`
          );
          break;
        }
      }
    }
  }

  await sleep(500);

  // Build index.json by scanning message folders
  const index = [];
  const msgDirs = fs
    .readdirSync(OUT_MESSAGES_ROOT, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .map((d) => d.name);

  for (const d of msgDirs) {
    const metaPath = path.join(OUT_MESSAGES_ROOT, d, "meta.json");
    const meta = safeReadJson(metaPath);
    if (!meta?.id) continue;

    const filesCount = Array.isArray(meta.files) ? meta.files.length : 0;

    index.push({
      message_id: String(meta.id),
      username: meta.username || "unknown",
      datetime: meta.datetime || "",
      message_url: meta.url || `https://stocktwits.com/message/${meta.id}`,
      folder: path.relative(RUN_ROOT, path.join(OUT_MESSAGES_ROOT, d)).replace(/\\/g, "/"),
      files_count: filesCount,
      first_seen_at: meta._first_seen_at || "",
      updated_at: meta._updated_at || "",
    });
  }

  // newest first by datetime (best-effort)
  index.sort((a, b) => (b.datetime || "").localeCompare(a.datetime || ""));

  writeJson(path.join(RUN_ROOT, "index.json"), index);

  console.log(`[DONE] messages folders: ${msgDirs.length}`);
  console.log(`[DONE] index.json: ${path.join(RUN_ROOT, "index.json")}`);

  await browser.close();
}

main().catch((e) => {
  console.error("[FATAL]", e);
  process.exit(1);
});