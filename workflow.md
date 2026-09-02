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

## Local Components

- `collectors/telegram_collector.py`: Telegram messages and downloaded media.
- `collectors/rss_collector.py`: RSS feeds and feed media.
- `collectors/web_scraper.py`: web articles, Open Graph images, and ticker news.
- `collectors/egyptian_sources.py`: specialized Egyptian-market sites (currently Alborsaa News — alborsaanews.com — قسم البورصة والشركات). Disabled by default; enable with `ENABLE_EGYPTIAN_SOURCES=1`. Sources under grace period require `importance >= NEW_SOURCE_MIN_IMPORTANCE` before publishing.
- `data/news_store.py`: local SQLite persistence and migrations.
- `analyzer/news_analyzer.py`: Ollama text analysis and fallback model.
- `analyzer/vision_analyzer.py`: optional image analysis/OCR.
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

Last updated: 2026-09-02
