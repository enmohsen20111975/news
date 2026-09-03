# Integration Contract Reference — News Agent ↔ GLMinvestment
# ===========================================================
# يوثّق الـ payload والـ endpoints والـ schema المتوقعة بين
# news agent (هذا المستودع) و GLMinvestment.

## Endpoint: `POST /api/news`

- **محلي:** `http://localhost:3000/api/news`
- **إنتاج:** `https://invist.m2y.net/api/news`

### Auth
```http
x-agent-key: <NEWS_AGENT_API_KEY>
X-News-Agent-Key: <NEWS_AGENT_API_KEY>
```

### Request Payload (single news)
```json
{
  "title": "string (required, max 200)",
  "content": "string (clean news text, max 1000)",
  "summary_ar": "string (ملخص عربي)",
  "summary_en": "string (ملخص إنجليزي)",
  "source": "string (e.g. 'AlBorsaNews', 'telegram', 'rss')",
  "source_type": "telegram | web | rss | copy",
  "url": "string (original URL)",
  "tickers": ["COMI", "TMGH"],
  "importance": 0-100,
  "sentiment": "bullish | bearish | neutral",
  "impact_type": "general | earnings | dividend | ipo | ma | regulatory | ...",
  "event_type": "IPO_SUBSCRIPTION | DIVIDEND_EX_DATE | EARNINGS_BEAT | ...",
  "reasoning": "سبب قصير بالعربي",
  "market": "EGX",
  "image_paths": ["https://..."],
  "ocr_text": "string (from vision analyzer)",
  "raw_analysis": { ... full Ollama analysis ... },
  "published_at": "ISO 8601",
  "is_valid_news": true
}
```

### Response (success 201)
```json
{
  "ok": true,
  "success": true,
  "message": "تم إضافة الخبر للموقع بنجاح",
  "id": 7895
}
```

### Response (duplicate 200)
```json
{
  "ok": true,
  "success": true,
  "message": "خبر مكرر - تم تجاهله",
  "duplicate": true
}
```

### Response (unauthorized 401)
```json
{ "ok": false, "error": "Unauthorized" }
```

---

## Endpoint: `POST /api/expert-recommendations/import`

```json
{
  "session_date": "2026-09-02",
  "session_type": "صباحية",
  "expert_name": "تحليل مجمّع (AI محلي)",
  "expert_source": "news_agent_aggregator",
  "recommendations": [
    {
      "stock_symbol": "COMI",
      "stock_name_ar": "البنك التجاري الدولي",
      "action": "BUY",
      "recommendation_type": "شراء واحتفاظ",
      "entry_price": 78.5,
      "target_price": 85.0,
      "stop_loss": 75.0,
      "technical_analysis": "...",
      "recommendation_reason": "..."
    }
  ]
}
```

---

## Target Schema (`market_news` in `data_engine.db`)

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK AUTOINCREMENT | |
| title | TEXT NOT NULL | |
| content | TEXT | clean news text |
| summary_ar | TEXT | |
| summary_en | TEXT | |
| source | TEXT | e.g. 'AlBorsaNews' |
| source_type | TEXT | telegram/web/rss/copy |
| url | TEXT | |
| tickers | TEXT (JSON array) | `["COMI","TMGH"]` |
| importance | INTEGER 0-100 | |
| sentiment | TEXT | bullish/bearish/neutral |
| impact_type | TEXT | earnings/dividend/ipo/... |
| event_type | TEXT | IPO_SUBSCRIPTION/DIVIDEND_EX_DATE/... |
| reasoning | TEXT | سبب القرار بالعربي |
| market | TEXT | EGX |
| image_paths | TEXT (JSON array) | |
| ocr_text | TEXT | from vision analyzer |
| raw_analysis | TEXT (JSON) | full Ollama output |
| published_at | TEXT | ISO 8601 |
| fetched_at | TEXT | datetime('now') |
| sent_at | TEXT | nullable |
| is_sent | INTEGER | 0/1 |
| applied | INTEGER | 0/1 — هل اشتغل في V40.2 |
| applied_at | TEXT | متى اشتغل |

---

## News Impact Scorer Event Types

| Event Type | Score | Verdict |
|-----------|-------|---------|
| IPO_SUBSCRIPTION | +18 | BOOST |
| DIVIDEND_EX_DATE | -12 | REDUCE |
| DIVIDEND_ANNOUNCE | +6 | BOOST |
| EARNINGS_BEAT | +14 | BOOST |
| EARNINGS_MISS | -14 | REDUCE |
| MA_ACQUISITION | +12 | BOOST |
| REGULATORY_APPROVAL | +10 | BOOST |
| STOCK_SPLIT | +4 | BOOST |
| MANAGEMENT_CHANGE | -3 | REDUCE |
| CONTRACT_AWARD | +8 | BOOST |
| EXPANSION | +7 | BOOST |
| FRAUD | -25 | VETO |
| HALT | -25 | VETO |

---

## Notes

- `event_type` و `reasoning` تمت إضافتهما للـ payload في `news_agent` بتاريخ 2026-09-03.
- `is_valid_news=false` لازم يتجاهل في GLMinvestment ولا يُخزن.
- الـ `tickers` جاية كـ JSON array في العمود `tickers` بنفس الصيغة.
