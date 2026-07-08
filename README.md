# beyond-esg

*🇬🇧 English · [🇵🇱 Polski](README.pl.md)*

A master's-thesis research prototype for engineering a value-based ("axiological") stock-selection method that operates beyond standard ESG norms while still respecting hard financial analysis (fundamentals and technicals).

Thesis title (Polish): *Inżynieria selekcji wartości w inwestowaniu poza normami ESG*.

> **Status:** research prototype, not a production product. It is an artifact of a master's thesis. Outputs are experimental and are intended to demonstrate a method, not to serve as investment advice.

---

## Overview

Standard ESG scoring applies a fixed, top-down normative framework. This project takes a different route: it mines **value axes bottom-up from real retail-investor discourse** (StockTwits comments), then treats those axes as one selection dimension alongside classic financial pillars.

The design principle is explicit: the discovered value axes are a **discourse signal, deliberately not a substitute for financial analysis**. Fundamentals and technicals sit in the same company row so that capital preservation is not ignored in favor of values.

The full flow:

1. **Scrape** investor comments (StockTwits) and a company universe with market-cap category rankings (CompaniesMarketCap).
2. **Derive value axes** from the comment corpus using seeded/organic **BERTopic** topic modeling plus **local-LLM perceptual-frame profiling**.
3. **Combine** the value axes with **yfinance** fundamentals and technicals into one row-per-company master dataset.
4. A **FastAPI** backend ranks companies and assembles a scored, constrained, ETF-like preview portfolio according to a weighted user preference profile.
5. A **React wizard** UI lets a user build a value profile, set scope and portfolio constraints, and inspect the resulting portfolio with per-company drill-down.

The application runs out-of-the-box on bundled **synthetic demo fixtures** and transparently switches to real pipeline output once it exists locally.

---

## How it works (pipeline stages)

### 1. Data acquisition — `scrapper/` (Node.js + Puppeteer)

- **Two sources.** StockTwits (retail-investor social messages) and companiesmarketcap.com (company universe grouped into thematic/geographic categories with market-cap rankings). All scraping is browser-driven (headful Chrome), with randomized timing and Cloudflare-block detection plus browser restart.
- **StockTwits symbol universe** (`symbols.js`): iterates A–Z letter tabs, infinite-scrolls, and extracts per-symbol rows (symbol, href, company name, industry, market cap). Stats file records ~32,395 indexed symbols.
- **StockTwits comment scrape** (`stocktwits_stock_scrapper.js`, batch driver `stocktwits_batch_scrape_all.js`): scrolls a symbol page, extracts messages (id, url, username, datetime, rich text, media, quoted/embedded messages), and stops after 5 consecutive empty extracts. Output is stored under `media_sample/<SYMBOL>/runs/<timestamp>/messages/<id>/meta.json` with idempotent merge (keeps longest text, unions media). Batch progress is journaled and resumable.
- **CompaniesMarketCap** (`cmc_get_categories.js`, `cmc_scrape_category.js`): scrapes category listings, paginates market-cap tables (top N, default 250) with table-scoring and header-index heuristics for robust ticker extraction.
- **Symbol mapping and merge** (`mapper.js`, `merge_top_cmc_with_stocktwits.js`): CMC and StockTwits use different ticker conventions; a candidate generator (dot/dash variants, exchange-suffix aliases) maps between them (~58% match rate reported). The merge emits `merged_flat_stocktwits.jsonl` — one flat row per matched ticker — which is the batch scraper's input and the universe seed downstream.

### 2. Analysis pipeline — `analiza/` (numbered Python scripts)

Execution order and modes are documented in `analiza/README.md`.

- **Flatten** (`01_flatten_stocktwits_messages.py`): walks scraped message folders, joins company metadata, and emits `posts_flat.jsonl` (one row per post). Full corpus ≈ 78,906 posts.
- **Social layer** (`02_build_social_features.py`): distant-supervised sentiment — trains a TF-IDF + logistic-regression classifier on posts self-labeled by explicit "bullish"/"bearish" tokens (lexicon fallback), scores every post, and aggregates per company (posts/authors counts, avg sentiment, share splits, controversy, coverage, author diversity, a sector-norm prior, and a legacy `custom_esg_proxy_score`).
- **Value-axes discovery (two-stage discovery + fusion, scripts `10a → 10b → 10c → 11_fuse`):**
  - **Filtering** (`10a_filter_value_frames.py`): three parallel filters over the post corpus — Filter A = seed-word match against a ~70-term governance/labor/environment/ethics/regulatory frozenset (~14.4% of posts); Filter B = passthrough (100%); Filter C = SentenceTransformer (`all-mpnet-base-v2`) cosine similarity to a hard-coded axiological-concept sentence, threshold 0.16 calibrated on the full corpus (~33.8%).
  - **BERTopic discovery** (`10b_bertopic_discovery.py`): for each filtered corpus independently, cleans boilerplate, fits BERTopic (mpnet embeddings + UMAP + HDBSCAN + CountVectorizer, `nr_topics=60`, seed 42). Each topic is auto-labeled axiological vs. trading-noise by comparing its top words to axiological vs. noise concept vectors. Produces per-company axiological coverage and topic exposure.
  - **LLM profiling** (`10c_llm_profiling.py`): per company, groups posts and prompts a **local OpenAI-compatible model** (calibrated run used **Qwen2.5-7B-Instruct** in LM Studio) with a strict JSON schema. The prompt asks not for global sentiment but for **perceptual frames / value lenses** — each with label, evidence quote, exposure, sentiment — plus an overall coverage label, with explicit instructions to return empty for pure trading chatter.
  - **Fusion** (`11_fuse_axiological.py`): merges the three BERTopic filters and the LLM output per company into `company_axiological_profile.jsonl`. Fields include coverage (max across filters), per-filter coverage, `inter_method_agreement` (fraction of the four methods showing signal), a confidence score, deduped LLM frames, `has_signal`, and `profile_null`. Summary reports avg coverage ≈ 0.221, avg agreement ≈ 0.49.
  - **Ablation** (scripts `13`–`15`): re-run profiling with a second LLM (gpt-5 via codex/openclaw) and compare.
- **Legacy value-axes path** (`11_build_comment_derived_esg.py`) still runs in parallel and writes organically-discovered `custom_esg_*` axes (axis label, score 0–100, exposure, confidence, family, keywords, avg sentiment). The final dataset therefore carries **both** the legacy `custom_esg_*` axes and the newer `axiological_*` profile.
- **Fundamentals / technicals** (`16_fetch_yfinance_financials.py`): pulls Yahoo Finance data via **yfinance (no API key)**. Fundamentals (net margin, operating margin, ROE, ROA, revenue growth) from `Ticker.info`; technicals (30/90-day momentum, 30-day volatility, 90-day drawdown) from 1-year adjusted close. Alternative importers (`05_`/`08_`) normalize arbitrary broker CSV exports into the same canonical CSVs.
- **Feature scoring** (`04_build_profitability_features.py`, `07_build_technical_features.py`): min-max normalizes each metric against the universe's 10th/90th-percentile bounds, then computes a weighted 0–100 score (volatility and drawdown inverted). An optional external ESG-benchmark import (`12_`) exists but currently has 0 rows.
- **Master assembly** (`03_build_company_master_dataset.py`): defines the universe from the merged StockTwits file, classifies each company's instrument type, parses market-cap labels, and left-joins six feature files (social, legacy comment-ESG, profitability, technical, real-ESG, axiological) into **`company_master_dataset.jsonl`** — 2,570 rows, ~75 fields per company. Instrument mix ≈ 2,322 equity, 96 funds/ETFs, 78 REITs, 74 ambiguous.

### 3. Backend — `backend/app` (FastAPI)

- Router mounted at `/api/v1`. Endpoints: `GET /health`; `GET /catalog`; `GET /data/status`, `GET /data/worklists/{kind}`, `POST /data/import/{kind}`; `GET /profiles` (3 presets) and `GET/POST/DELETE /profiles/saved` (persisted to `backend/data/custom_profiles.json`); `GET /company/{symbol}/market-data`; `POST /portfolio/preview` (main scoring endpoint); `POST /portfolio/report` (writes Markdown/JSON to `analiza/out/reports`). `app/main.py` also serves the built React frontend with SPA fallback and localhost-only CORS.
- **Selection score** (`scoring.py`): weighted sum of six 0–1 components — `base_quality`, `esg_alignment` (the value/axiological axis), `category_match`, `profitability_alignment`, `technical_alignment`, `market_cap_alignment`. Weights come from a profile and are L1-normalized (defaults 0.25 / 0.20 / 0.15 / 0.20 / 0.10 / 0.10). Missing metrics degrade gracefully (absent score = 0.5 in neutral mode, else 0.0).
- **Value alignment**: `esg_alignment` blends a base alignment from `custom_esg_proxy_score` (direction set by a prefer-low/neutral/prefer-high mode) with a per-axis component driven by user axis preferences (each axis has a mode and importance). A separate `perception_score` (axis exposure × per-axis sentiment) is used only for a UI-facing dimension filter, not for ranking.
- **Portfolio assembly** (`portfolio.py`): after category/universe/min-posts and dimension filters, companies are scored, sorted, then greedily selected with diversification — seed distinct categories first, then fill to `portfolio_size` respecting a per-category cap. Holding weights are equal or score-weighted (with an iterative max-weight cap). Summary reports weighted averages, concentration (HHI), max weight, and top category. When custom-ESG metrics exist, a fixed **"ESG-like reference portfolio" benchmark** is built and compared via overlap ratio and metric deltas.
- **Instrument-universe classification** (`instrument_universe.py`): rule/regex-based over company name, industry, category, and source hrefs → `common_equity`, `reit`, `fund_etf_trust`, `ambiguous`, or `crypto_coin`. Funds/ETFs and crypto are always excluded from portfolio candidates; REITs fold into common equity.
- **Data shape**: JSONL/JSON/CSV file-backed (no database), with an in-process mtime/size signature cache. The `POST /data/import/{kind}` endpoint decodes a base64 CSV and shells out to the numbered `analiza/*.py` scripts to regenerate features. Per-company market data (`market_data.py`) computes SMA/EMA/RSI/MACD from yfinance history.

### 4. Frontend — `frontend/` (React 19 + Vite)

- Single-page app, Polish UI, titled *"Profil aksjologiczny spółek"*. A 5-step wizard: **Start → Wartości (values) → Zakres (scope) → Dostrojenie (tuning) → Wyniki (results)**.
- **Step 1 (Start):** hero with preset cards (from `GET /profiles` plus a from-scratch card) and a load-saved-profile dropdown.
- **Step 2 (Values):** axis cards for the value axes — each shows label, average sentiment, an exposure bar, top keywords, and a 0–2× importance slider; list/group views, search, show-more.
- **Step 3 (Scope):** searchable multi-select category picker plus a minimum-comments-per-company input.
- **Step 4 (Tuning):** portfolio parameters (size, max holding weight, per-category cap, distinct categories, weighting mode, strict cap), financial-preference selects, an Advanced panel with six score-weight sliders and four dimension-filter thresholds (each with an include-missing toggle), and save/update/delete profile controls. The Generate button calls `POST /portfolio/preview`.
- **Step 5 (Results):** a TL;DR KPI card, a prototype-warnings box, an optional ESG-benchmark comparison block, summary stats (positions, categories, averages, HHI, top category), allocation and holdings strips, and an expandable company table. Expanding a row reveals value families/axes chips, a score breakdown, the axiological profile (coverage, confidence, inter-method agreement, frames), and an embedded price chart.
- **CompanyChart.jsx** uses `lightweight-charts` to render candlestick/line charts with MA20/50/200 overlays plus volume, RSI(14), and MACD(12/26/9) panes and period pills, fetching from `GET /company/{symbol}/market-data`.

---

## Architecture / repo layout

```
beyond-esg/
├── scrapper/        Node.js + Puppeteer data acquisition
│                    (StockTwits symbols/comments, CompaniesMarketCap
│                     categories, symbol mapping + merge)
├── analiza/         Numbered Python pipeline
│                    (flatten → social → value-axes discovery/fusion →
│                     yfinance fundamentals/technicals → master dataset →
│                     report generator); see analiza/README.md
├── backend/         FastAPI service (scoring, portfolio assembly,
│   └── app/         catalog, presets, market-data, report export,
│                    data-import endpoints); serves the built frontend
├── frontend/        React 19 + Vite value-profile wizard (Polish UI)
├── demo/            Synthetic demo fixtures (DEMO01..DEMO10)
├── start_app.ps1    One-command launcher (Windows / PowerShell)
└── stop_app.ps1     Stops the launched backend
```

Data flow: `scrapper/` → `analiza/out/company_master_dataset.jsonl` → `backend/` → `frontend/`.

---

## Tech stack

**Scrapers**
- Node.js (CommonJS, Node 18+), Puppeteer ^24 (headful Chrome)
- Native `fs` / `path` / `crypto`, JSON + JSONL files, hand-rolled concurrency limiter and idempotent merge (no database)

**Analysis pipeline (Python 3.11+)**
- BERTopic, sentence-transformers (`all-mpnet-base-v2`), UMAP, HDBSCAN
- scikit-learn (TF-IDF/CountVectorizer, logistic regression, cosine similarity), numpy
- OpenAI Python SDK against a local OpenAI-compatible endpoint (LM Studio); Qwen2.5-7B-Instruct for profiling, gpt-5 via codex/openclaw for ablation
- yfinance (no API key); JSONL/CSV file formats; pytest

**Backend**
- Python, FastAPI, Pydantic v2, Starlette (CORS + StaticFiles SPA hosting)
- yfinance, hand-rolled technical indicators (SMA/EMA/RSI/MACD), regex instrument classification
- File-backed datastore (JSONL/JSON/CSV), no database

**Frontend**
- React 19, Vite 8, lightweight-charts 4.2
- Plain `fetch` (no axios/react-query), hand-written CSS (no UI framework), JSX/ES modules (no TypeScript, no router)

---

## Running locally

### Simplest (Windows / PowerShell)

```powershell
.\start_app.ps1
# then open http://127.0.0.1:8000
```

`start_app.ps1` launches uvicorn (`app.main:app`) on `127.0.0.1:8000` as a background process, records the PID and chosen port under `backend/`, and polls `/api/v1/health`. The backend serves the built frontend from the same address, so no separate Vite server is needed for a demo.

Port options: `-Port 8010`, or `-AutoPort` to pick a free port from the pool (8000/8010/8020/8080/8090); `-Restart` to restart. Stop with `.\stop_app.ps1`.

### Manual

Backend:

```bash
cd backend
python -m venv .venv
pip install -e .
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# optional smoke test:
python scripts/smoke_test_api.py
```

Frontend (development):

```bash
cd frontend
npm install
npm run dev      # expects API at http://localhost:8000/api/v1 (VITE_API_BASE configurable)
npm run build    # produces the bundle the backend serves at http://127.0.0.1:8000
```

---

## Demo mode & data provenance

The repository ships with **synthetic demo fixtures** so a clean clone runs immediately.

- Fixtures live in `demo/`: `company_master_dataset.jsonl` (10 fictional companies `DEMO01..DEMO10`, e.g. "Acme Demo Corp"), `merged_flat_stocktwits.jsonl`, and `comment_esg_axes_summary.json`. Comment examples are explicit placeholders ("Przykładowy komentarz (dane syntetyczne).") — no real quotes or company names. The schema is identical to real pipeline output, so backend and frontend behave the same on demo data.
- The fallback is implemented in `backend/app/services/datasets.py` via `_with_demo_fallback(real_path, demo_name)`, applied to three paths: the master dataset, the comment-ESG axes summary, and the merged flat StockTwits file. Each resolves to the real file if it exists, otherwise the bundled synthetic copy. Resolution happens at module import time.
- When `analiza/out` is empty, the app **automatically serves demo data**, and switches to real data once the pipeline produces it.

**Real data is intentionally not published** for provenance reasons (web scraping plus financial-services sources). `.gitignore` blocks `analiza/out/`, raw upload dirs, `scrapper/cmc_out/`, `scrapper/media_sample/`, large universe files, and the provenance-sensitive fundamentals/technicals CSVs and CMC↔StockTwits symbol maps/reports. This is the ~2,500-company real universe plus computed scores, regenerable locally by running the `scrapper/` scrapers to build the universe and corpus, then the numbered `analiza/` pipeline to produce `company_master_dataset.jsonl` and the axes summary.

---

## Status / limitations

- This is a **prototype** from a master's thesis, framed as a design-science artifact — not a production or investment product.
- The value-axis signal is about **density, not volume**: value-axis discovery is triangulated across three post-filters and two paradigms (unsupervised BERTopic clustering + generative LLM frame extraction) with an explicit inter-method agreement and confidence, and `profile_null` marks companies whose comment volume is too weak to trust. A substantial share of activity is "none/marginal", and low-signal companies are flagged accordingly in the UI without affecting ranking.
- The value axes are a **discourse signal placed alongside** — not replacing — the financial pillar (fundamentals, technicals, and an ESG-like reference benchmark) in the same company row.
- The scraper is deliberately retained as a thesis artifact rather than trimmed. No external real-ESG benchmark rows are currently present (the importer exists but the dataset is empty).
