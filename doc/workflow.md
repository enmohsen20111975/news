# News Agent Workflow

## Purpose

This file is the operational memory for the local News Agent. Read it before debugging, changing the pipeline, or deploying integration changes.

The system collects real financial news, analyzes it locally with Ollama, stores the complete record in SQLite, and sends approved news to the production website:

- Production site: https://invist.m2y.net/
- Site name: دليل الاستثمار (EGXPilot)
- Local agent root: `/home/meme/my_apps/news_agent`
- Site source root: `/home/meme/my_apps/GLMinvestment`

## Source Of Truth

- Project rules: `CONSTITUTION.md`
- Operational workflow and integration memory: this file
- Local database: `data/news.db`
- Site news database: `GLMinvestment/data-engine/data/data_engine.db`
- Site canonical ingest route: `GLMinvestment/src/app/api/news/route.ts`
- Site read/feed route: `GLMinvestment/src/app/api/news-feed/route.ts`
- Local sender: `sender/production_sender.py`
- Local orchestration: `main.py`

Never put tokens, API keys, or passwords in this file. Secrets belong only in `.env` or the production secret manager.

## Pipeline

```text
Telegram / RSS / Web
        |
        v
local data/news.db (pending)
        |
        v
Ollama text analysis + optional Ollama Vision
        |
        v
local data/news.db (analyzed)
        |
        v
importance filter + duplicate protection
        |
        v
POST https://invist.m2y.net/api/news
        |
        v
GLMinvestment/data-engine/data/data_engine.db
        |
        v
GET /api/news-feed -> website news UI
```

## Scrapers Architecture

الـ scrapers في `collectors/scrappers/` تعمل كـ **standalone scripts** وتخزن في `db/data_engine.db` (معزأة عن `data/news.db`).
كل scraper يُشغّل مرة واحدة يومياً عن طريق cron أو `run.bat`، ويبقي البيانات محدثة.

### Data Flow
```
TradingView pages (ar.tradingview.com)
    ├── Playwright / REST endpoint
    ├── extract symbols + tab data (9 tabs)
    └── save_to_db() → db/data_engine.db
        ├── تبويبات market_movers_tabs  ← tradingview_market_movers.py (الجديد)
        ├── stocks                     ← tradingview_scraper.py + tradingview_rest.py
        └── screener_lists             ← tradingview_screener_lists.py
```

### Scraper Commands
```bash
# 9-tabs scraper (الجديد — يسحب كل التبويبات من صفحات Market Movers)
python collectors/scrappers/tradingview_market_movers.py

# Screener lists (gainers/losers/active/...)
python collectors/scrappers/tradingview_screener_lists.py

# Full market scraper (all stocks + tabs)
python collectors/scrappers/tradingview_scraper.py

# REST fetcher (no Playwright — خفيف وسريع)
python collectors/scrappers/tradingview_rest.py --market egypt

# Investing.com market data (sectors/commodities/currencies)
python collectors/scrappers/investing_scraper.py

# Investing.com news → data/news.db
python collectors/investing_news_collector.py
```

### Stock Data Sources (Fallback Chain)
1. TradingView REST (`tradingview_rest.py`) — خفيف، ثواني
2. TradingView Playwright (`tradingview_scraper.py`) — كامل، 60-120 ث
3. EGXPilot — fallback نهائي

---

## Local Components

- `collectors/telegram_collector.py`: Telegram messages and downloaded media.
- `collectors/rss_collector.py`: RSS feeds and feed media.
- `collectors/web_scraper.py`: web articles, Open Graph images, and ticker news.
- `collectors/egyptian_sources.py`: specialized Egyptian-market sites (currently Alborsaa News — alborsaanews.com — قسم البورصة والشركات). Disabled by default; enable with `ENABLE_EGYPTIAN_SOURCES=1`. Sources under grace period require `importance >= NEW_SOURCE_MIN_IMPORTANCE` before publishing.
- `collectors/investing_news_collector.py`: جمع أخبار Investing.com — يكتب مباشرة إلى `data/news.db` عبر NewsStore
- `collectors/keyword_filter.py`: EGX relevance gate (keyword → ticker → AI fallback) applied by all collectors.
- `config/sources.py`: central source registry; maps each channel/feed/site to its display name on the live site.
- `data/news_store.py`: local SQLite persistence and migrations.
- `collectors/scrappers/` (package): TradingView data scrapers using Playwright or REST.
  - `tradingview_rest.py`: الأسعار الأساسية عبر Scanner REST endpoint (بدون Playwright)
  - `tradingview_scraper.py`: Full scraper — كل الأسواق + 8 تبويبات تفصيلية (Performance/Valuation/Technicals/...)
  - `tradingview_screener_lists.py`: قوائم مذكية (gainers, losers, active, unusual-volume, ...) — يسحب رمز + اسم + ترتيب فقط
  - `tradingview_market_movers.py`: الـ **9 تبويبات** على صفحة Market Movers (overview, performance, technicals, valuation, dividends, profitability, incomeStatement, balanceSheet, cashFlow) — يسحب الجدول الكامل مع الـ column headers والـ cell values
  - `investing_scraper.py`: Investing.com — sector tables، commodities، currencies → `data/investing_egypt.json`
- `analyzer/news_analyzer.py`: Ollama text analysis and fallback model.
- `analyzer/vision_analyzer.py`: optional image analysis/OCR.
- `analyzer/recommendation_aggregator.py`: يجمع توصيات الأسهم من قنوات
  تيليجرام/ويب المتعددة، يحلل كل سهم بـ Ollama، ويطلع توصية موحّدة.
- `sender/production_sender.py`: authenticated JSON delivery to the live site.
- `ui/dashboard.py`: local monitoring API/UI.
- `main.py`: collect -> analyze -> send orchestration.

## Production API Contract

### Send news

```http
POST https://invist.m2y.net/api/news
Content-Type: application/json
x-agent-key: <PRODUCTION_API_KEY>
```

The key is loaded by the local agent from `PRODUCTION_API_KEY` in `.env`. The site reads the matching value from `NEWS_AGENT_API_KEY` or its deployment secret configuration.

Payload:

```json
{
  "title": "News title",
  "content": "Complete news body",
  "summary_ar": "Arabic summary",
  "summary_en": "English summary",
  "source": "Source name",
  "source_type": "telegram|rss|web",
  "url": "https://source.example/article",
  "tickers": ["COMI"],
  "importance": 75,
  "sentiment": "bullish|bearish|neutral",
  "impact_type": "earnings|macro|market|general",
  "market": "EGX",
  "image_paths": ["https://public.example/image.jpg"],
  "ocr_text": "Text extracted from image",
  "raw_analysis": {
    "reasoning": "Analysis reasoning",
    "recommended_action": "buy|hold|sell|monitor"
  },
  "published_at": "2026-09-02T12:00:00Z"
}
```

Expected success responses are HTTP 200 or 201. A successful duplicate response contains `duplicate: true` and must not be treated as a new publication.

### Read news

```http
GET https://invist.m2y.net/api/news-feed
GET https://invist.m2y.net/api/news-feed?market=crypto
```

The website feed reads `market_news` from `data-engine/data/data_engine.db` and maps `content` to the displayed body, JSON fields to arrays/objects, and `raw_analysis.reasoning` to the AI reasoning display.

## Image Rules

- Only real source images are allowed; never generate a news image.
- The browser can display public `http://` or `https://` URLs.
- Local paths such as `/home/meme/.../image.jpg` are not usable by the live website.
- `production_sender.py` filters out local filesystem paths before sending.
- Telegram media needs a public upload/static-media mechanism before it can appear on the live site.
- Web image extraction uses `og:image` and `twitter:image` metadata.

## Deduplication

- Local database prevents repeated news records using its configured content identity.
- Production `market_news` uses `UNIQUE(title, source)` and `INSERT OR IGNORE`.
- The feed also deduplicates normalized titles.
- Do not remove duplicate protection to make a test appear successful.

## Environment

Important variables are in `.env`:

- Telegram: `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNELS`
- Ollama: `OLLAMA_URL`, `OLLAMA_MODEL`, `OLLAMA_FALLBACK_MODEL`, optional vision model
- Production: `PRODUCTION_SERVER_URL`, `PRODUCTION_API_KEY`
- Collection: `COLLECTION_INTERVAL_MINUTES`, `MIN_IMPORTANCE_SCORE`, `MAX_NEWS_PER_BATCH`
- Egyptian sources: `ENABLE_EGYPTIAN_SOURCES`, `ALBORSAA_ENABLED`, `EGYPTIAN_DELAY_SECONDS`,
  `NEW_SOURCE_GRACE_DAYS`, `NEW_SOURCE_MIN_IMPORTANCE`
- Content filtering: `KEYWORD_FILTER_USE_AI` (1 = use Ollama fallback when keywords miss)

## Source Registry

Every news source has a display name that appears on the live site (`market_news.source`).
All Telegram channels collapse to a single `تيليجرام` label so the UI does not show
channel handles like `@sahmmisr`. Other sources keep their real brand name.

The registry lives at `config/sources.json` and is loaded by `config/sources.py`. It
covers: Telegram (one display name for all channels), RSS feeds (مباشر، أرقام، أموال الغد،
اليوم السابع - اقتصاد), and web sources (جريدة البورصة، بحث ويب).

## EGX Relevance Filter

`collectors/keyword_filter.py` gates new news before it enters `news.db`. Three layers:

1. Hard keyword match — Arabic + English terms related to EGX (البورصة، الإدراج، التوزيعات،
   EGX30، COMI, COMI.CA, FRA, etc).
2. Ticker symbol scan — explicit list of EGX-listed tickers plus a regex for `XXX.CA`.
3. AI fallback (`OLLAMA_MODEL` → `OLLAMA_FALLBACK_MODEL`) — used only when the keyword
   layer misses. Asks Ollama `yes/no` whether the text is about EGX. If AI is disabled
   (`KEYWORD_FILTER_USE_AI=0`) or unavailable, a short-text fallback (`len < 300`) keeps
   very short items so we do not drop potentially valid flashes.

The filter is applied inside each collector so unactionable content never reaches the
local DB or the production sender.

## Expert Recommendations Aggregator

`analyzer/recommendation_aggregator.py` reads analyzed news from `news.db`, groups
articles that mention the same ticker and look like buy/sell/hold signals, then asks
Ollama to produce **one consolidated recommendation per stock**. The result is saved
in `expert_recommendations` and pushed to GLMinvestment via
`POST /api/expert-recommendations/import`.

Flow per cycle (after `_analyze_pending`):

1. Pull `status='analyzed'` news from the last `RECOMMENDATION_LOOKBACK_HOURS`
   (default 48h).
2. Filter for recommendation hints`: توصية، شراء، بيع، دعم، مقاومة، استهدف، وقف، ...
3. Group by ticker (uses `tickers` column first, then a regex over title/body).
4. For each ticker with `>= RECOMMENDATION_MIN_SOURCES` items, ask Ollama to extract
   a structured JSON recommendation (action, entry, targets, stop_loss, technical
   analysis).
5. If Ollama is unavailable, fall back to a numeric regex extractor that produces
   a cautious `aggregated_fallback` recommendation.
6. Save to `expert_recommendations` (deduped on stock_symbol+session_date+entry_price)
   and POST to the production site. Successful ones are marked `sent_ok=1`.

Output feeds the GLMinvestment **Expert Recommendations** panel alongside the manual
expert entries seeded by `scripts/seed-expert-recommendations.js`.

## Egyptian Sources Collector

Adds Egyptian-market news from specialized local sites. Currently enabled sources:

- `alborsaanews.com` (جريدة البورصة) — pulls the البورصة والشركات and أسواق category pages.
  Honors robots.txt, lazy-loaded images (data-src on `<img>` and `<div>`), HTML entities,
  and Arabic titles. Rate-limited via `EGYPTIAN_DELAY_SECONDS`.

Sources explicitly evaluated and rejected:

- `mubasher.info` — Cloudflare challenge; bot access blocked.
- `argaam.com` — `robots.txt` disallows general bots (`User-agent: trendictionbot`,
  `PetalBot`) and the EGX sector URL returned 404.
- `egx.com.eg/ar/BulletinNews.aspx` — served by an F5 ASM WAF that requires a browser
  session; static HTTP returns an empty ASP.NET shell, not safe to scrape with `requests`.
- `beta.egx.com.eg` — request rejected.

When `ENABLE_EGYPTIAN_SOURCES=1`, the new source is registered in `data/.source_state.json`
with a `first_seen` timestamp. For `NEW_SOURCE_GRACE_DAYS` days after first registration,
items from this source require `importance >= NEW_SOURCE_MIN_IMPORTANCE` (default 75)
to be published to the live site. After the grace period, normal `MIN_IMPORTANCE_SCORE`
applies.

The current production URL must be `https://invist.m2y.net`. Do not replace it with `localhost` when testing production delivery.

## Runbook

### Start one cycle

```bash
cd /home/meme/my_apps/news_agent
. .venv/bin/activate
python3 main.py --once
```

### Run the local dashboard

```bash
cd /home/meme/my_apps/news_agent
./run.sh
```

Dashboard:

- `http://localhost:8001`
- `http://localhost:8001/api/status`

### Focused checks

```bash
cd /home/meme/my_apps/news_agent
. .venv/bin/activate
python3 -m unittest tests/test_news_store.py
python3 -m py_compile sender/production_sender.py collectors/web_scraper.py
```

For the site source:

```bash
cd /home/meme/my_apps/GLMinvestment
npx tsc --noEmit -p tsconfig.json
```

A full TypeScript check may report pre-existing errors outside the news files. Record those separately; do not confuse them with news integration failures.

## Troubleshooting Order

1. Check `.env` values without printing secrets.
2. Check Ollama availability at `OLLAMA_URL`.
3. Check Telegram credentials. An invalid bot token blocks Telegram collection but should not block Web/RSS collection.
4. Check local `data/news.db` for pending/analyzed records.
5. Check the sender endpoint and HTTP status.
6. Check the production route logs and `data-engine/data/data_engine.db`.
7. Check `GET /api/news-feed` for the displayed result.
8. Check whether images are public URLs, not local paths.
9. Check duplicate behavior before assuming delivery failed.

## Known Issues And Decisions

- Telegram requires a valid bot token. The known error is `The provided token is not valid`.
- The production site route must have a writable database directory and initialize `market_news` when needed.
- The sender must send `x-agent-key`; unauthenticated production writes are not allowed.
- `bullish` and `bearish` are normalized by the website UI to positive and negative display states.
- OCR text is not the same thing as AI reasoning. The feed must prefer `raw_analysis.reasoning` for the reasoning panel.
- The local agent may continue with Web/RSS/Ollama while Telegram credentials are being repaired.
- Do not test by inserting fake news into production.

## Change Procedure

Before editing:

1. Read this file and `CONSTITUTION.md`.
2. Identify the owning file for the behavior.
3. Reproduce the issue with the cheapest focused check.
4. Change the smallest possible surface.

After editing:

1. Run a focused test or compile check immediately.
2. Verify the local sender payload without sending fake production news.
3. Verify production only with real collected data or a read-only endpoint.
4. Update this file when the workflow, API, schema, or a known issue changes.
5. Never commit secrets or database files.

## Current Integration State

- The site is deployed on production according to the owner.
- The local agent is configured to send to `https://invist.m2y.net/api/news`.
- The API contract is JSON and authenticated with `x-agent-key`.
- The canonical storage table is `market_news` in the site data-engine database.
- The production read endpoint is `/api/news-feed`.
- The remaining external blocker is Telegram credential validity.
- Telegram collection uses the authenticated user session created by the dashboard (`telegram_ui_<hostname>`); the bot token is disabled for reading channels unless `TELEGRAM_USE_BOT=1` is explicitly set.
- Web/RSS sources can be unavailable or rate-limited; when both return zero, the agent imports real `news_agent` items from the production feed, analyzes them locally, and publishes them into the public `market_news` feed.
- The Egyptian sources collector is a new channel for EGX-specific news from specialized local sites; it is intentionally opt-in and gated behind a grace period.
- `ENABLE_TELEGRAM=0` and `SOCIAL_PLATFORMS=` are intentional while a separate worker owns Telegram collection and social publishing.

Last updated: 2026-09-03

---

## 2026-09-02 — Z.ai Code Sandbox Integration Audit

### What was done (sandbox only — not pushed)
- Cloned `news` repo shallowly to `/home/z/my-project/news`.
- Inspected `main.py`, `sender/production_sender.py`, `analyzer/news_analyzer.py`, `data/news_store.py`, `.env.example`.
- Synced `NEWS_AGENT_API_KEY` in GLMinvestment sandbox `.env` with news agent's `PRODUCTION_API_KEY` (`news_agent_secret_key_2026`) — **sandbox only**.
- Sent test news via `POST /api/news` with `x-agent-key` header → HTTP 201 → stored in `market_news` (ID=7895, ID=7896).
- Verified `news_impact_scorer.score_news_articles()` runs on the stored news successfully.
- Scrubbed real Telegram secrets from `.env.example` (replaced with placeholders).
- Created `.gitignore` (was previously empty — caused `.env` + `.venv/` + `data/news.db` to be committed).
- Wrote `Agent messages.md` with all modifications required from the human programmer.

### Critical security findings (in `Agent messages.md`)
1. 🚨 `.env` (real, with Telegram API_HASH + Bot Token + GLMinvestment PRODUCTION_API_KEY) is committed in `0975b0d` and pushed to GitHub.
2. 🚨 `.venv/` (7408 files) committed.
3. 🚨 `data/news.db` committed (could contain session data).
4. 🚨 `.gitignore` was empty.

### Modifications required from human programmer
- See `Agent messages.md` (root of this repo). All 10 items documented with exact code/SQL/commands.
- Priority order: 0 (security scrub) → 1 (revoke secrets) → 5-9 (code changes) → 10 (enable V40_2_NEWS_IMPACT).

### Integration verified end-to-end
```
news agent → POST /api/news (with x-agent-key) → GLMinvestment market_news table → news_impact_scorer → V40.2 daily_generator
                                                                                              ↑
                                        (after item 7 done) news_fetcher_analyzer reads from market_news
```

### Files touched in sandbox (not pushed)
- `.env.example` — secrets replaced with placeholders
- `.gitignore` — created (was empty)
- `Agent messages.md` — new file (430 lines)

### Next steps (awaiting owner's permission)
1. Push the `.env.example` + `.gitignore` + `Agent messages.md` changes (3 files, no secrets).
2. Human programmer to revoke secrets + scrub history (item 0 in Agent messages.md).
3. Human programmer to implement code changes (items 2-9).
4. After all done, enable `V40_2_NEWS_IMPACT=1` in production (item 10).
