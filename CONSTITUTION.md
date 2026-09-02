# News Agent — دستور المشروع

## الغرض
وكيل أخبار محلي محسّن لسوق البورصة المصرية EGX، يجمع الأخبار من مصادر متعددة، يحللها بالذكاء الاصطناعي المحلي، وينشرها للموقع الرسمي ومنصات التواصل.

## القواعد الأساسية

### 1. جمع الأخبار مع الصور
- كل خبر يجب أن يحمل **صورة حقيقية** من المصدر الأصلي
- التيليجرام: تنزيل الصور من الرسائل (`download_media`)
- الويب: استخراج الصور من المقالات (Open Graph, `og:image`)
- الـ RSS: استخراج `media_content` أو `enclosure`
- **ممنوع** توليد صور بالذكاء الاصطناعي للخبر — الصورة من المصدر الأصلي فقط

### 2. تحليل محلي بذكاء اصطناعي
كل خبر يدخل في مسارين متوازيين:
1. **تحليل نصي** — Ollama ينتج: tickers, importance, sentiment, impact_type, summary
2. **تحليل بصري** — Ollama Vision (`llava`/`moondream`/`llama3.2-vision`) يفهم الصورة:
   - وصف الصورة بالعربية
   - استخراج نص OCR من الرسم البياني/لقطة الشاشة
   - تحديد نوع المحتوى: chart / screenshot / document
   - sentiment بصري إضافي

النتيجة النهائية: **قرار مساعد** للتحليل المالي يحتوي على:
- degree_of_importance (0-100)
- confidence_score (0-100)
- recommended_action (buy/hold/sell/observe)
- affected_tickers
- visual_analysis (وصف الصورة + OCR)
- text_analysis (الملخص والمشاعر)
- reasoning (سبب القرار)
- source_links (روابط الخبر الأصلي)

### 3. مكافحة التكرار
- قاعدة البيانات المحلية: `UNIQUE(body[:200])` via SHA256 hash
- الموقع الرسمي: `UNIQUE(title, source)` في جدول `market_news`
- الإرسال للموقع: `INSERT OR IGNORE` — لا يرسل خبر مكرر
- أي مصدر يرسل نفس الخبر = يتم تجاهله تلقائياً

### 4. النشر على منصات التواصل
كل خبر محلل يمكن نشره على:
- **Telegram** — عبر Bot API (`sendMessage` + `sendPhoto`)
- **Facebook** — عبر Graph API
- **WhatsApp** — عبر WhatsApp Business API أو Twilio

قبل النشر:
- التحقق من `importance >= MIN_IMPORTANCE_SCORE` (افتراضياً 55)
- التحقق من عدم النشر المسبق (`sent_ok = 0`)
- تسجيل رابط المنشور في `published_links` JSON

### 5. ارتباط مستمر مع الموقع الرسمي
الموقع الرسمي (GLMinvestment) هو **المصدر الوحيد للحقيقة**.

يتم إرسال الأخبار للموقع في صورتين:
1. **قرار مساعد للتحليلات** — `/api/ai/decisions` أو embedded في `/api/news`
   - يحتوي على: tickers, importance, sentiment, recommended_action, confidence, reasoning
   - يُستخدم في صفحة التحليل الفني لكل سهم
2. **خبر عادي + صورة** — `/api/news` (POST)
   - يحتوي على: title, content, image_paths, summary_ar, source, url
   - يظهر في قسم الأخبار العام

### 6. قاعدة البيانات
الجدول الرئيسي `news` في `data/news.db`:
- id (SHA256 hash)
- source, source_type (telegram/web/rss/copy)
- title, body, url, published_at
- image_paths (JSON array)
- ocr_text (نص مستخرج من الصورة)
- status (pending/analyzed/sent)
- tickers, importance, sentiment, impact_type
- summary_ar, summary_en
- raw_analysis (JSON كامل للقرار المساعد)
- published_links (JSON — روابط النشر على المنصات)
- sent_at, sent_ok

### 7. هيكل المشروع
```
news_agent/
├── main.py                 # المحرك الرئيسي
├── collector/
│   ├── telegram_collector.py   # التيليجرام + صور
│   ├── web_scraper.py          # الويب + صور
│   └── rss_collector.py        # RSS
├── analyzer/
│   ├── news_analyzer.py        # تحليل النصوص (Ollama)
│   └── vision_analyzer.py      # تحليل الصور (Ollama Vision)
├── sender/
│   ├── production_sender.py    # إرسال للموقع + منصات التواصل
│   └── social_publisher.py     # نشر على FB/WA/TG
├── data/
│   └── news_store.py           # SQLite storage
├── ui/
│   ├── dashboard.py            # FastAPI dashboard
│   ├── index.html
│   ├── style.css
│   └── app.js
└── .env
```

### 8. المتغيرات البيئية (.env)
```env
# Telegram
TELEGRAM_API_ID=
TELEGRAM_API_HASH=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHANNELS=

# Ollama
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=glm-fast:latest
OLLAMA_FALLBACK_MODEL=qwen2.5:1.5b
OLLAMA_VISION_MODEL=llava:13b  # أو moondream / llama3.2-vision

# GLMinvestment (الموقع الرسمي)
LOCAL_SITE_URL=http://localhost:3000
LOCAL_SITE_API_KEY=

# السيرفر الإنتاجي (قديم — للاحتياط فقط)
PRODUCTION_SERVER_URL=
PRODUCTION_API_KEY=

# التشغيل
COLLECTION_INTERVAL_MINUTES=15
MIN_IMPORTANCE_SCORE=55
MAX_NEWS_PER_BATCH=20

#社交媒体
FACEBOOK_PAGE_ID=
FACEBOOK_ACCESS_TOKEN=
WHATSAPP_BUSINESS_API_URL=
WHATSAPP_ACCESS_TOKEN=
```

### 9. تدفق البيانات الكامل
```
1. جمع (Telegram/Web/RSS/Copy)
   ├── نص الخبر
   ├── صورة المصدر (download/og:image/media_content)
   └── metadata (source, url, published_at)

2. تخزين مؤقت (news.db)
   └── status = 'pending'

3. تحليل (Ollama + Vision)
   ├── تحليل النص → tickers, importance, sentiment
   ├── تحليل الصورة → OCR, description, visual_sentiment
   └── دمج → قرار مساعد كامل

4. إرسال للموقع الرسمي (GLMinvestment)
   ├── POST /api/news — خبر عادي + صورة
   └── embedding القرار المساعد في التحليلات

5. نشر على منصات التواصل (إن كانت مهمة)
   ├── Telegram Bot (sendMessage + sendPhoto)
   ├── Facebook Page
   └── WhatsApp
   └── تسجيل الروابط في published_links

6. تحديث الحالة
   └── status = 'sent', sent_ok = 1
```

### 10. قواعد عدم التكرار
- لا يُرسل خبر لنفس المنصة مرتين
- إذا تم النشر على Telegram، لا يُنشر مرة أخرى
-同一 الخبر من مصادر مختلفة: يُرسل مرة واحدة مع ذكر كل المصادر
- `UNIQUE constraint` في كل جدول في الموقع

### 11. السياسات
- **لا بيانات وهمية** — كل خبر من مصدر حقيقي
- **لا صور مولدة** — الصورة من المصدر الأصلي فقط
- **الشفافية** — كل خبر يحتوي على المصدر والرابط الأصلي
- **الأولوية** — الأخبار الأكثر أهمية تُنشر أولاً
- **الاحتياطي** — إذا فشل الذكاء الاصطناعي، نستخدم keyword fallback

### 12. الأمان
- API keys في `.env` فقط — لا ترفع للمستودع
- الموقع الرسمي: مفتاح API للتحقق من الهوية
- جميع الاتصالات عبر HTTPS
- لا تسجيل أسرار في اللوج

---
آخر تحديث: 2026-09-02
صيغة: v1.0
