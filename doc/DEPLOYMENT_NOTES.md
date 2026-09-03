# ملاحظات النشر لمبرمج الموقع — News Agent v2

## نظرة عامة
الـ **News Agent** هو مشروع Python مستقل يجمع أخبار البورصة المصرية من تيليجرام ومواقع مصرية (جريدة البورصة، أموال الغد) ويحلّلها بنموذج AI محلي (Ollama + glm-fast) ثم يرسلها للموقع الرئيسي (GLMinvestment) عبر REST API.

**بيئة التشغيل:** Linux (WSL Ubuntu) • Python 3.12 • Ollama محلي • Telethon (Telegram)

---

## 1. الـ API endpoints اللي بيرفع عليها الـ Agent

### أ. إرسال خبر جديد
**`POST /api/news`**
- Base URLs (معرّفة في `.env`):
  - `LOCAL_SITE_URL=http://localhost:3000` (للتطوير)
  - `PRODUCTION_SERVER_URL=https://invist.m2y.net` (الإنتاج)
- Headers:
  - `Content-Type: application/json`
  - `x-agent-key: <PRODUCTION_API_KEY>` (من `.env`)

**Payload (مهم — كل الحقول دي لازم يكون الـ API يقبلها):**
```json
{
  "title": "عنوان الخبر (string, مطلوب)",
  "content": "النص الكامل للخبر (string) — ممكن يبقى 2000-3000 حرف",
  "summary_ar": "ملخص عربي (string)",
  "summary_en": "ملخص إنجليزي (string, فاضي حالياً)",
  "source": "اسم المصدر — مثل 'تيليجرام · @BursaAcademy' أو 'جريدة البورصة' أو 'أموال الغد'",
  "source_type": "telegram | web | rss | copy",
  "url": "رابط الخبر الأصلي (string)",
  "tickers": ["COMI", "HRHO"],
  "importance": 0-100,
  "sentiment": "bullish | bearish | neutral",
  "impact_type": "earnings | dividend | ipo | acquisition | macro | regulation | price_move | general",
  "market": "EGX",
  "image_paths": ["https://...", "data/telegram_images/abc.jpg"],
  "ocr_text": "نص مستخرج من الصور (string)",
  "raw_analysis": { ... كائن كامل من AI analyzer ... },
  "published_at": "ISO 8601 timestamp",
  "is_valid_news": true | false
}
```

### ب. إرسال توصية خبراء
**`POST /api/expert-recommendations/import`**

**Payload:**
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
      "action": "BUY | SELL | HOLD",
      "recommendation_type": "شراء واحتفاظ | دعم / ارتداد | T+1 / مضاربة | متوسط / تجميع | تفريغ",
      "entry_price": 85.5,
      "entry_price_from": 84.0,
      "entry_price_to": 87.0,
      "target_price": 95.0,
      "target_price_2": 100.0,
      "stop_loss": 80.0,
      "support_level": 82.0,
      "resistance_level": 90.0,
      "technical_analysis": "...",
      "recommendation_reason": "...",
      "chart_images": ["https://...", "data/telegram_images/abc.jpg"],
      "source_news_ids": ["uuid1", "uuid2"]
    }
  ]
}
```

**استجابة النجاح:** `{"recommendations": [{"id": "uuid"}], "errors": []}`
**استجابة الخطأ:** `{"errors": ["stock_symbol is required"]}`

---

## 2. الـ Database Schema (news.db)

### جدول `news`
```sql
CREATE TABLE news (
  id TEXT PRIMARY KEY,
  source TEXT,             -- اسم المصدر البشري
  source_type TEXT,        -- telegram | web | rss | copy
  title TEXT,
  body TEXT,               -- النص الكامل (ممكن 2000-3000 حرف)
  url TEXT,
  tickers TEXT,            -- JSON array
  importance INTEGER,
  sentiment TEXT,
  impact_type TEXT,
  market TEXT DEFAULT 'EGX',
  image_paths TEXT,        -- JSON array (URLs + local paths)
  image_urls TEXT,         -- JSON array
  raw_analysis TEXT,       -- JSON من AI analyzer
  ocr_text TEXT,
  published_at TEXT,
  collected_at TEXT,
  sent_to_production INTEGER DEFAULT 0,
  is_valid_news INTEGER DEFAULT 1,
  summary_ar TEXT,
  summary_en TEXT
)
```

### جدول `expert_recommendations`
```sql
CREATE TABLE expert_recommendations (
  id TEXT PRIMARY KEY,
  stock_symbol TEXT,
  stock_name_ar TEXT,
  action TEXT,
  recommendation_type TEXT,
  entry_price REAL,
  entry_price_from REAL,
  entry_price_to REAL,
  target_price REAL,
  target_price_2 REAL,
  stop_loss REAL,
  support_level REAL,
  resistance_level REAL,
  technical_analysis TEXT,
  recommendation_reason TEXT,
  chart_images TEXT,        -- JSON array (جديد في v2)
  source_news_ids TEXT,     -- JSON array (جديد في v2)
  session_date TEXT,
  expert_name TEXT,
  expert_source TEXT,
  notes TEXT,
  created_at TEXT,
  sent_to_production INTEGER DEFAULT 0
)
```

---

## 3. تعديلات v2 (اللي اتعملت في الـ news_agent)

### أ. ticker index موسّع (مهم جداً)
**قبل:** كان فيه 22 سهم بس (من `news_fetcher_analyzer.py` في GLMinvestment). أخبار زي "النيل للأدوية" أو "كورا" أو "مصر بني سويف" كانت بدون ticker.

**بعد:** ملف جديد `config/stocks_index.json` فيه **1047 سهم مصري** و **3149 hint** (اسم عربي + إنجليزي + aliases). الـ analyzer بيقرأ منه الأول، ولو مش موجود يرجع للـ index القديم.

**لتجديد الـ index:**
```bash
python3 scripts/build_stocks_index.py
```
الـ script بيسحب من `/home/meme/my_apps/GLMinvestment/data/all/stocks.db` (جدول `stocks` بعمود `ticker, name, name_ar`).

### ب. Spam filter مُحسّن (`analyzer/news_analyzer.py`)
أضفنا كلمات رفض صريحة:
- **فيديو/لايف:** "لايف", "بث مباشر", "فيديو", "video", "live", "started live"
- **ردود ومناقشات:** "رد على", "رد:", "تعليق:", "مناقشة", "نقاش"
- **سبام/تسويق:** "تابعونا", "اشترك", "انضم", "يوتيوب", "facebook"
- **خارج النطاق:** "الذهب", "الفضة", "BTC", "USDT", "فوركس", "كريبتو", "بيتكوين", "بايننس", "فيوتشر", "سبوت"
- **Coin tickers:** "MIRA", "BAT", "PEPE", "DOGE"
- **أخبار عامة:** "طقس", "كرة قدم", "مسلسل", "وصفة"

كمان أضفنا regex patterns:
- `^\s*رد[:\s]` — رد صريح في أول السطر
- `^@\w+\s` — منشن لعضو
- نص قصير بعد حذف الروابط

### ج. Duplicate method تم إصلاحه
كان في `analyzer/news_analyzer.py`:
- method `_filter_and_classify` معرّفة **مرتين** (السطر 134 و 227)
- method `_merge_vision_result` فيها `return` قبل ما تبدأ (كود ميت)

اتنقلت لـ method واحدة منظمة + helper method `_is_spam`.

### د. إرسال النص الكامل (`sender/production_sender.py`)
قبل: كان بيقطع `body` عند 800 حرف.
بعد:
- لو `analysis.news_text` موجود وطويل → استخدمه
- وإلا استخدم `body` كامل (ممكن 3000+ حرف)
- وإلا fallback على `title` أو `summary_ar`

### هـ. الصور مع التوصيات (`analyzer/recommendation_aggregator.py` + `sender/production_sender.py`)
قبل: التوصية كانت بدون صور.
بعد:
- الـ aggregator بيجمع `image_paths` و `image_urls` من كل news_item مرتبط
- بيخزنهم في `chart_images` (list of URLs + paths)
- الـ sender بيبعتهم في الـ payload

### و. RSS feeds ميتة تم تحديثها (`collectors/rss_collector.py` + `.env`)
قبل في `.env`:
```
RSS_FEEDS=https://www.mubasher.info/rss,https://www.argaam.com/ar/rss
```
كلها بترجع 403/404/HTML.

بعد:
```
RSS_FEEDS=https://www.alborsaanews.com/feed,https://amwalalghad.com/feed/atom/
```
كمان: لو الـ entry URL بيرجع نص مبتور بـ `[...]`، الـ collector يفتح الرابط ويستخرج النص الكامل من `<article>` أو `<meta description>`.

### ز. Egyptian sources تم تفعيلها (`.env`)
أضفنا `ENABLE_EGYPTIAN_SOURCES=1` لتفعيل scraper "جريدة البورصة".

### ح. Telegram source display محسّن
قبل: كل أخبار التيليجرام بتظهر كـ "تيليجرام" generic.
بعد: `تيليجرام · @BursaAcademy` (اسم القناة الفعلي).

---

## 4. كيفية تشغيل المشروع

```bash
# 1. البيئة
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. .env (مهم جداً)
TELEGRAM_API_ID=...
TELEGRAM_API_HASH=...
TELEGRAM_USE_BOT=0  # للقراءة من القنوات نستخدم user session
TELEGRAM_CHANNELS=@BursaAcademy,@sahmmisr,...
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=glm-fast:latest
LOCAL_SITE_URL=http://localhost:3000
PRODUCTION_SERVER_URL=https://invist.m2y.net
PRODUCTION_API_KEY=...
RSS_FEEDS=https://www.alborsaanews.com/feed,https://amwalalghad.com/feed/atom/
ENABLE_EGYPTIAN_SOURCES=1

# 3. Ollama (يجب أن يكون شغال)
ollama serve &
ollama pull glm-fast:latest

# 4. بناء ticker index (مرة واحدة أو كل شهر)
python3 scripts/build_stocks_index.py

# 5. تشغيل الـ Agent
./run.sh

# 6. تشغيل Dashboard (UI) على :8001
./run_dashboard.sh
```

### Windows PowerShell

افتح PowerShell داخل مجلد المشروع وشغّل:

```powershell
.\run.ps1 -AgentArguments '--once' # أول مرة: ينشئ .venv الخاصة بويندوز ويثبت المتطلبات
.\run.ps1              # تشغيل مستمر كل فترة الجمع
.\run_dashboard.ps1    # لوحة المراقبة على http://localhost:8001
```

البيئة الافتراضية المنقولة من Linux لا تُستخدم على Windows؛ `run.ps1` ينشئ بيئة
جديدة في `.venv\Scripts`. يجب تشغيل تطبيق Ollama قبل الوكيل، ويكفي أن يكون
`OLLAMA_URL=http://localhost:11434` مضبوطاً في `.env`.

إذا كانت قاعدة بيانات الأسهم في مكان مختلف، اضبط `GLM_STOCKS_DB` على مسارها
الكامل قبل تشغيل `scripts\build_stocks_index.py`.
 **"Ollama error":** تحقق إن Ollama شغال + `Invoke-RestMethod http://localhost:11434/api/tags` بيرجع.
 **مفيش ticker متعرف:** شغل `python scripts\build_stocks_index.py` بعد ضبط `GLM_STOCKS_DB` إذا كانت قاعدة GLMinvestment خارج المجلد الشقيق.

## 5. ملاحظات تقنية مهمة للمبرمج

1. **`news.db` ينكتب فيه rows جديدة كل 15 دقيقة.** الـ agent يقرأ news.db → يحلل → يرسل للـ API.

2. **`is_valid_news`** = false يعني الخبر اترفض (spam filter). متابعوش في الـ UI.

3. **`tickers`** بتيجي كـ JSON array. ممكن يكون فيها ticker وأقارب (مثلاً COMI + HRHO).

4. **`summary_ar`** في الغالب بيكون نفس النص الكامل (مش ملخص). الـ agent بيركز على استخراج الـ tickers والـ importance والـ sentiment.

5. **`chart_images`** في التوصية ممكن يكون URLs أو paths محلية. لو path محلي يبدأ بـ `data/telegram_images/` لازم يكون متخزن على disk أو محول لـ URL signed.

6. **التكرار:** الـ API لازم يكون عنده dedup على `(title, source)` — الـ agent بيبعت كل news مرتين (local + production)، فلو في dedup هيشتغل تلقائياً.

7. **الـ session period:** كل 15 دقيقة الـ agent بيعمل cycle كامل: telegram + rss + web → analyze → aggregate → send.

---

## 6. Troubleshooting

- **"مفيش أخبار" في الـ dashboard:** تحقق من `data/news.db` بـ sqlite3، و `tail data/agent.log`.
- **"Telegram غير متصل":** الـ session قد انتهت. ادخل على `http://localhost:8001` → تبويب "تيليجرام" → ادخل رقم الهاتف و الكود.
- **"Ollama error":** تحقق إن `ollama serve` شغال + `curl http://localhost:11434/api/tags` بيرجع.
- **مفيش ticker متعرف:** شغل `python3 scripts/build_stocks_index.py` لتحديث الـ index من قاعدة GLMinvestment.

---

## 7. Git Workflow

كل التعديلات في branch `master`. الـ commits الأخيرة:
- تحسينات v2: spam filter، ticker index، صور التوصيات، RSS feeds، Egyptian sources.
- rebuild الـ index من GLMinvestment DB.