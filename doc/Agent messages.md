# Agent Messages — رسائل من Z.ai Code للمبرمجين البشر
# ===================================================
# **تاريخ:** 2026-09-02
# **كاتب:** Z.ai Code (الساندبوكس)
# **السياق:** فحص مستودع `news` + اختبار الربط مع `GLMinvestment`
#
# هذا الملف يوثّق كل التعديلات المطلوبة اللي أنا (Z.ai Code) مش قادر أعملها
# على الإنتاج/اللابتوب — ودي محتاجة المبرمج البشري يعملها.
# اقرأ الملف ده بالكامل قبل أي deploy.

---

## 🚨🚨 بنود حرجة جداً (خطر أمني مزدوج — أولاً قبل أي حاجة)

### 0. `.env` الحقيقي + `.venv/` كامل + `data/news.db` متسربة على GitHub

**المشكلة (أخطر من البند 1):**
المستودع `news` مرفوع على GitHub في commit `0975b0d` (first commit) وفيه:

| الملف | الحجم | الأسرار المتسربة |
|------|------|----------------|
| `.env` (الحقيقي) | ~2KB | `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_BOT_TOKEN`, `PRODUCTION_API_KEY` (مفتاح GLMinvestment!) |
| `.venv/` كامل | ~7000+ ملف | Python binaries + packages — مفيش أسرار بس حجم ضخم + مخالف لـ best practices |
| `data/news.db` | ~13MB | بيانات أخبار + metadata (ممكن تحتوي session data) |
| `.gitignore` | فاضي | مفيش أي حماية — ده السبب إن كل حاجة اتـcommit |

**التأكيد:** شغلت `git show HEAD:.env` وطلعت الـ 4 أسرار الحقيقية متسربة في الـ tracked version (مش بس في `.env.example`).

**المطلوب من المبرمج فوراً (الأولوية رقم 1 — قبل أي تعديل كود):**

1. **revoke فوراً لكل الأسرار دي (الترتيب مهم):**
   - Telegram API_HASH: https://my.telegram.org/apps → `Revoke` (API_ID بيفضل ثابت).
   - Telegram Bot Token: كلم `@BotFather` على Telegram → `/revoke` → هيعطيك token جديد.
   - `PRODUCTION_API_KEY` لـ GLMinvestment: ادخل GLMinvestment server → ولّد مفتاح جديد في `.env` (`NEWS_AGENT_API_KEY=new_value`) → حدّث news agent `.env` بنفس القيمة.

2. **امسح من git tracking (محلياً):**
   ```bash
   cd /path/to/news
   git rm --cached .env
   git rm --cached -r .venv/
   git rm --cached data/news.db
   git rm --cached data/news.db-shm data/news.db-wal 2>/dev/null || true
   ```

3. **حدّث `.gitignore`** (أنا بالفعل كتبت version صح في الساندبوكس — شوف `cat .gitignore`). انسخها بالظبط.

4. **امسح من git history (مهم جداً — tracking deletion مش بيكفي):**
   ```bash
   # استخدم BFG Repo-Cleaner (الأسهل)
   # نزّله من https://rtyley.github.io/bfg-repo-cleaner/
   java -jar bfg.jar --delete-files "{.env,data/news.db}"
   java -jar bfg.jar --delete-folders "{.venv}"
   git reflog expire --expire=now --all
   git gc --prune=now --aggressive
   git push --force-with-lease origin main
   
   # أو بـ git filter-repo (الـ modern way):
   pip install git-filter-repo
   git filter-repo --invert-paths --path .env --path .venv --path data/news.db --path data/news.db-shm --path data/news.db-wal
   git push --force-with-lease origin main
   ```

5. **بعد ما تخلص revoke + scrub:** حدّث `.env` الحقيقي بالـ tokens الجديدة على اللابتوب فقط (مش على GitHub).

**الأثر لو متمسحتش:** أي حد ممكن:
- يتحكم في الـ Bot وينشر بدل المالك.
- يقرأ رسائل التيليجرام على القنوات اللي الـ agent بيستمع عليها.
- يبعت أخبار وهمية لـ GLMinvestment بـ الـ API key المتسرب → يخرب تحليلات V40.2.
- يـ impersonate الـ news agent في أي request.

---

## 🚨 بنود عاجلة (خطر أمني حرج)

### 1. أسرار متسربة على GitHub في `.env.example`

**المشكلة:**
ملف `.env.example` كان فيه أسرار حقيقية متسربة على GitHub في أول commit (`0975b0d`):

| المتغير | القيمة المتسربة | نوع الخطر |
|---------|----------------|-----------|
| `TELEGRAM_API_ID` | `34557076` | Telegram App credentials |
| `TELEGRAM_API_HASH` | `fe604a9844bf753210acb4e648af4155` | Telegram App credentials |
| `TELEGRAM_BOT_TOKEN` | `8150921223:AAFteLXeaH_lutZC62auVorlaey9BfNJVP0` | Bot control + publish as the bot |

**المطلوب من المبرمج:**

1. **revoke فوراً** لكل الأسرار دي:
   - Telegram API: ادخل https://my.telegram.org/apps → اعمل `Revoke` لـ API_HASH (API_ID بيفضل ثابت، بس الـ hash هو اللي بيتبدل).
   - Telegram Bot Token: كلم `@BotFather` على Telegram → `/revoke` → هيعطيك token جديد. حدّث الـ `.env` الحقيقي بالقيمة الجديدة.

2. **امسح الأسرار من git history** (لأنها لسه في commit `0975b0d`):
   ```bash
   cd /path/to/news
   # الطريقة الأسهل: استخدم BFG Repo-Cleaner
   # (نزّله من https://rtyley.github.io/bfg-repo-cleaner/)
   java -jar bfg.jar --replace-text passwords.txt
   git reflog expire --expire=now --all
   git gc --prune=now --aggressive
   git push --force-with-lease origin main
   ```
   أو بـ `git filter-branch`:
   ```bash
   git filter-branch --force --index-filter \
     'git rm --cached --ignore-unmatch .env.example && git rm --cached --ignore-unmatch .env' \
     --prune-empty --tag-name-filter cat -- --all
   ```

3. **حدّث `.env.example`** بالـ version الجديد (أنا بالفعل عملت ده في الساندبوكس — شوف `git diff .env.example`). القيم كلها placeholders دلوقتي.

4. **تأكد إن `.env` (الحقيقي) موجود في `.gitignore`**:
   ```bash
   grep "^\.env$" .gitignore || echo ".env" >> .gitignore
   git add .gitignore && git commit -m "security: ensure .env is gitignored"
   ```

**الأثر لو متمسحتش:** أي حد ممكن يتحكم في الـ Bot + يقرأ رسائل التيليجرام + ينشر بدل المالك. ده خطر كبير جداً.

---

## 🔧 بنود تعديل كود (news repo)

### 2. إضافة `reasoning` field للـ payload الـ sender بيبعته

**السبب:**
GLMinvestment عنده `news_signals` schema فيها `reasoning` column (للـ Decision Logger). الـ sender دلوقتي مش بيبعت `reasoning`، فالـ V40.2 مش بيقدر يـ log سبب قرار الـ VETO/BOOST/REDUCE.

**المطلوب:**
في `sender/production_sender.py` → دالة `_format_for_site()`، ضيف:

```python
# بعد raw_analysis
'reasoning': analysis.get('reasoning', '') or news.get('reasoning', ''),
'event_type': news.get('impact_type', 'general'),  # للـ news_impact_scorer
'is_valid_news': analysis.get('is_valid_news', True),
```

وكمان في `analyzer/news_analyzer.py`، خلي الـ Ollama prompt يطلع `reasoning` صريح:
```
"reasoning": "سبب قصير بالعربي ليه الخبر مهم/مش مهم لإي سهم"
```

---

### 3. إضافة `event_type` field (للـ news_impact_scorer classification)

**السبب:**
GLMinvestment عنده `news_impact_scorer.py` بـ 13 event type (IPO, DIVIDEND, EARNINGS_BEAT, إلخ). الـ news agent بيحلل بـ Ollama بس مش بيبعت `event_type` متوقع. لو الـ sender بعت `event_type`، الـ GLMinvestment يقدر:
- يتخطى الـ keyword matching البطيء
- يستخدم تصنيف الـ Ollama (أدق من الـ keywords)

**المطلوب:**
في `analyzer/news_analyzer.py`، زوّد الـ Ollama prompt عشان يطلع:
```json
{
  "event_type": "IPO_SUBSCRIPTION | DIVIDEND_EX_DATE | EARNINGS_BEAT | EARNINGS_MISS | MA_ACQUISITION | REGULATORY_APPROVAL | STOCK_SPLIT | MANAGEMENT_CHANGE | CONTRACT_AWARD | EXPANSION | FRAUD | HALT | GENERAL"
}
```

الـ 13 type موجودين في `GLMinvestment/vps-service/analyzers/news_impact_scorer.py` (متغير `EVENT_TYPES`).

---

### 4. توثيق الـ contract في `INTEGRATION.md`

**المطلوب:**
أنشئ ملف `INTEGRATION.md` في جذر المستودع يوثّق:
- الـ payload الكامل الـ sender بيبعته لـ `/api/news`
- الـ auth headers المطلوبة (`x-agent-key` + `X-News-Agent-Key`)
- الـ endpoints المتاحة في GLMinvestment
- الـ schema المتوقع في `market_news` table

أنا كتبت المسودة في آخر الملف ده (شوف قسم "Integration Contract Reference").

---

## 🔧 بنود تعديل كود (GLMinvestment repo)

### 5. إزالة `/api/news/ingest/route.ts` (dead endpoint)

**المشكلة:**
`src/app/api/news/ingest/route.ts` بيدور على `news_signals` table في `predictions.db`. بس الـ table دي **مش موجودة** (اتأكدت بـ `PRAGMA table_info`). الـ endpoint ده dead code.

**المطلوب:**
- امسح `src/app/api/news/ingest/route.ts` (و الـ folder كله لو مفيش غيره).
- أو، لو محتاجين batch endpoint، ادمجه في `/api/news` (POST بياخد `{news: [...], source: '...'}`).

**الأثر لو اتشال:** مفيش — مفيش client بيستدعيه. الـ sender بيبعت لـ `/api/news` (POST خبر واحد).

---

### 6. توحيد الـ schema (market_news = single source of truth)

**المشكلة:**
فيه جدولين للـ news في GLMinvestment:
- `market_news` في `data_engine.db` (شغالة، 7,806 خبر بعد الهجرة)
- `news_signals` في `predictions.db` (مش موجودة، بس الكود بيدور عليها)

**المطلوب:**
- استخدم `market_news` كـ single source of truth.
- لو محتاج `applied` / `applied_at` columns (للـ V40.2 feedback loop)، زوّدهم لـ `market_news`:
  ```sql
  ALTER TABLE market_news ADD COLUMN applied INTEGER DEFAULT 0;
  ALTER TABLE market_news ADD COLUMN applied_at TEXT;
  ALTER TABLE market_news ADD COLUMN event_type TEXT DEFAULT 'general';
  ALTER TABLE market_news ADD COLUMN reasoning TEXT DEFAULT '';
  ```
- حدّث `news_impact_scorer.py` و `news_fetcher_analyzer.py` عشان يقرأوا من `market_news`.

---

### 7. ربط `news_fetcher_analyzer.get_news_with_impact` بـ `market_news`

**المشكلة:**
الـ V40.2 daily_generator بـ toggle `V40_2_NEWS_IMPACT=1` بيستدعي `get_news_with_impact(ticker)`. بس الـ function دي بتجيب أخبار من DuckDuckGo search (مش من `market_news`). ده معناه إن الأخبار اللي الـ news agent بيبعتها مش بتوصل لـ V40.2.

**المطلوب:**
في `vps-service/analyzers/news_fetcher_analyzer.py`:
- ضيف source جديد اسمه `market_news_db`:
  ```python
  def _get_news_from_market_news(self, ticker: str, days: int = 3) -> list:
      """يقرأ من market_news table في data_engine.db"""
      import sqlite3
      from pathlib import Path
      db_path = Path(os.environ.get('DATA_ENGINE_DB', 'db/data_engine.db'))
      conn = sqlite3.connect(str(db_path))
      cutoff = (datetime.now() - timedelta(days=days)).isoformat()
      rows = conn.execute('''
          SELECT title, content, summary_ar, importance, sentiment, impact_type, published_at
          FROM market_news
          WHERE tickers LIKE ? AND published_at >= ?
          ORDER BY importance DESC, published_at DESC
          LIMIT 5
      ''', (f'%"{ticker}"%', cutoff)).fetchall()
      conn.close()
      return [{'title': r[0], 'content': r[1], 'published_at': r[6]} for r in rows]
  ```
- في `get_news_with_impact()`، جرّب `market_news_db` الأول (الأخبار المحللة بالـ Ollama)، وبعدين DuckDuckGo كـ fallback.

---

### 8. إضافة `is_valid_news` filter في POST /api/news

**المشكلة:**
الـ sender بيبعت `is_valid_news: true/false` بس الـ POST route في `/api/news/route.ts` مش بيتعامل معاه. الأخبار الـ invalid بتتخزن.

**المطلوب:**
في `src/app/api/news/route.ts` → POST handler، بعد الـ `isAuthorized` check:
```typescript
const body = await request.json();
const { is_valid_news } = body;
if (is_valid_news === false) {
    return NextResponse.json({ 
        ok: true, 
        skipped: true, 
        reason: 'is_valid_news=false' 
    }, { status: 200 });
}
```

---

### 9. إضافة feedback endpoint (GLMinvestment → news agent)

**المشكلة:**
الـ flow دلوقتي في اتجاه واحد (news → GLMinvestment). الـ news agent مش بيعرف إذا كان خبره اشتغل في V40.2 ولا لأ.

**المطلوب:**
أضف endpoint في GLMinvestment:
```
GET /api/news/applied/<id>
→ { "applied": true, "applied_at": "2026-09-02T17:00:00Z", "ticker": "COMI", "verdict": "BOOST", "score_delta": +18 }
```

وفي news agent، أضف periodic poll (كل 5 دقايق) لـ `/api/news/applied/<id>` للأخبار الـ unsent. لو `applied=true`، حدّث `published_links` في `news.db` بـ `"glm_applied": true`.

---

### 10. تفعيل `V40_2_NEWS_IMPACT=1` بعد الربط الكامل

**المطلوب:**
بعد ما البنود 5-9 يخلصوا، فعّل الـ flag في الإنتاج:
```bash
# في GLMinvestment/.env (الإنتاج)
V40_2_NEWS_IMPACT=1
```
ثم أعد تشغيل Python backend. راقب الـ logs لـ `[NEWS-VETO]` / `[NEWS-BOOST]` / `[NEWS-REDUCE]` لمدة 7 أيام قبل ما تعتبرها stable.

---

## ✅ بنود أنا عملتها في الساندبوكس (مرجعية)

دي التعديلات اللي أنا عملتها في الساندبوكس للتحقق من الربط — **مش متـpush على GitHub**:

### في news repo:
1. ✅ مسح الأسرار من `.env.example` (استبدلت بـ placeholders).
2. ✅ فحص الـ sender contract (`_format_for_site` payload).
3. ✅ فحص `analyzer/news_analyzer.py` (بيستورد `EGX_TICKER_NAMES` من GLMinvestment بنجاح عبر `GLMINVESTMENT_PATH`).
4. ✅ فحص `data/news_store.py` schema (`news` table محلية).
5. ✅ اختبار الربط: بعت خبر تجريبي بـ `x-agent-key` → HTTP 201 → اتحفظ في `market_news` (ID=7895).
6. ✅ اختبار `news_impact_scorer` على الخبر المتخزن → اشتغل صح.

### في GLMinvestment repo:
1. ✅ فك ضغط `data/all.zip` في `db/vps_real/` (للقراءة فقط، chmod 444).
2. ✅ نسخ DBs أساسية لـ `db/` (stocks, predictions, news, data_engine, prices, auth).
3. ✅ إنشاء `market_news` table في `data_engine.db` + هجرة 7,806 خبر من `news.db/news_articles`.
4. ✅ إنشاء symlink: `data-engine/data/data_engine.db → ../../db/data_engine.db`.
5. ✅ تعديل `proxy-server.js` + `scripts/watchdog.sh` لمسارات نسبية (`__dirname` + `BASH_SOURCE`).
6. ✅ مسح `Documentation/handOver.text` (التوكن المتسرب).
7. ✅ مزامنة `NEWS_AGENT_API_KEY` في `.env` (الساندبوكس) = `PRODUCTION_API_KEY` في news `.env`.

---

## 📋 Integration Contract Reference

### Endpoint: `POST /api/news`

**URL:** `http://localhost:3000/api/news` (محلي) أو `https://invist.m2y.net/api/news` (إنتاج)

**Auth:** header `x-agent-key: <NEWS_AGENT_API_KEY>` (نفس `PRODUCTION_API_KEY` في news `.env`)

**Payload (single news):**
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
  "market": "EGX",
  "image_paths": ["https://..."],
  "ocr_text": "string (from vision analyzer)",
  "raw_analysis": { ... full Ollama analysis ... },
  "published_at": "ISO 8601",
  "is_valid_news": true
}
```

**Response (success 201):**
```json
{
  "ok": true,
  "success": true,
  "message": "تم إضافة الخبر للموقع بنجاح",
  "id": 7895
}
```

**Response (duplicate 200):**
```json
{
  "ok": true,
  "success": true,
  "message": "خبر مكرر - تم تجاهله",
  "duplicate": true
}
```

**Response (unauthorized 401):**
```json
{ "ok": false, "error": "Unauthorized" }
```

### Database Schema (target — `market_news` in `data_engine.db`)

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
| market | TEXT | EGX |
| image_paths | TEXT (JSON array) | |
| ocr_text | TEXT | from vision analyzer |
| raw_analysis | TEXT (JSON) | full Ollama output |
| published_at | TEXT | ISO 8601 |
| fetched_at | TEXT | datetime('now') |
| sent_at | TEXT | nullable |
| is_sent | INTEGER | 0/1 |
| **event_type** *(مطلوب إضافته)* | TEXT | IPO_SUBSCRIPTION/DIVIDEND_EX_DATE/... |
| **reasoning** *(مطلوب إضافته)* | TEXT | سبب القرار بالعربي |
| **applied** *(مطلوب إضافته)* | INTEGER | 0/1 — هل اشتغل في V40.2 |
| **applied_at** *(مطلوب إضافته)* | TEXT | متى اشتغل |

### News Impact Scorer Event Types (للـ `event_type` field)

من `GLMinvestment/vps-service/analyzers/news_impact_scorer.py`:

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

## 📞 تواصل

لو في أي سؤال عن التعديلات دي، راسل المالك (`enmohsen20111975`) أو Z.ai Code في الشات.

**تذكير:** لو لقيت أي سر متسرب في أي مكان تاني، اعمل revoke فوراً وابلغ المالك. الأسرار دي خطيرة.

---

*آخر تحديث: 2026-09-02*
*كاتب: Z.ai Code*
