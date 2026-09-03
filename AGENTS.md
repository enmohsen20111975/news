# News Agent — دليل الوكلاء والمهام

> دليل سريع للوكلاء (Agents) والمهام (Commands) في المشروع. يتم تحديثه مع كل تغيير بنيوي.
> آخر تحديث: 2026-09-03

## 🎯 الهدف العام

مشروع **News Agent** هو وكيل أخبار مالي محلي متخصص في بورصة مصر (EGX)، يجمع الأخبار من مصادر متعددة، يحللها بالذكاء الاصطناعي المحلي (Ollama)، وينشرها للموقع الرسمي ومنصات التواصل.

---

## 🚀 التشغيل اليومي

| المهمة | الأمر | الوصف |
|---|---|---|
| تشغيل كل شيء | `run.bat` | ينشئ الـ venv، يثبت الـ deps، يتحقق من Ollama، يفتح الداشبورد في المتصفح، ويبدأ الوكيل |
| تشغيل الواجهة فقط | `run_dashboard.bat` / `run_dashboard.ps1` / `run_dashboard.sh` | يشغل FastAPI dashboard على port 8001 بدون main.py |
| مراقبة CLI | `python monitor.py` | إحصائيات سريعة من data/news.db |
| تشغيل investing scraper | `run_investing_scraper.bat` | يشغل investing_scraper.py كل ساعة تلقائياً |

---

## 📈 الـ Scrapers

| المهمة | الأمر | قاعدة البيانات |
|---|---|---|
| 9-tabs scraper (جديد) | `python collectors/scrappers/tradingview_market_movers.py` | `db/data_engine.db` |
| Screener lists | `python collectors/scrappers/tradingview_screener_lists.py` | `db/data_engine.db` |
| Full market scraper | `python collectors/scrappers/tradingview_scraper.py` | `db/data_engine.db` |
| REST fetcher (لا يحتاج Playwright) | `python collectors/scrappers/tradingview_rest.py --market egypt` | `db/data_engine.db` |
| Stock ticker backfill | `python scripts/backfill_tickers.py` | `db/data_engine.db` |
| Investing.com market data | `python collectors/scrappers/investing_scraper.py` | `data/investing_egypt.json` |
| Investing.com news collector | `python collectors/investing_news_collector.py` | `data/news.db` |
| استيراد أخبار Investing.com من JSON | `python scripts/import_investing_news.py` | `data/news.db` |

> ⚠️ **مهم**: جميع الـ scrapers مستقلة ولا تستخدم `main.py`. الـ scrapers اللي بتخزن في `db/data_engine.db` (TradingView) مستقلة عن الـ collectors اللي بتخزن في `data/news.db` (Investing News، Telegram، RSS، Web).

---

## 🧠 التحليل
| المهمة | الأمر |
|---|---|
| بناء أو تحديث فهرس الأسهم | `python scripts/build_stocks_index.py` |
| استيراد أخبار Investing.com من JSON إلى قاعدة البيانات | `python scripts/import_investing_news.py` |
| اختبار التخزين | `python -m unittest tests/test_news_store.py` |
| اختبار الـ scrapers | `python -m py_compile collectors/scrappers/*.py` |

---

## 🧪 التشخيص
| المهمة | الأمر |
|---|---|
| فحص Kimi WebBridge daemon | `~/.kimi-webbridge/bin/kimi-webbridge status` |
| مراجعة قاعدة البيانات | `python -c "import sqlite3; c=sqlite3.connect('db/data_engine.db'); print(c.execute('SELECT name FROM sqlite_master WHERE type=\"table\"').fetchall())"` |
| فحص قاعدة الأخبار | `python monitor.py` |

---

## 📁 البنية المعمارية

```
news_agent/
├── main.py                    # ⚙️ Orchestration engine (Collect → Analyze → Send)
├── monitor.py                 # 📊 CLI monitor
├── run.bat / run.ps1 / run.sh # ▶️ One-click launcher (run.bat يفتح المتصفح أوتوماتيكياً)
├── run_dashboard.*            #   Dashboard-only scripts
├── run_investing_scraper.bat  #   Investing.com loop scraper
├── CONSTITUTION.md            # 📜 Project rules (v1.1)
├── workflow.md                # 📋 Operations guide + API contract
├── INTEGRATION.md             # 🔗 GLMinvestment integration contract
├── CHANGELOG.md               # 📝 Change history
├── AGENTS.md                  # 👈 هذا الملف
├── collectors/
│   ├── __init__.py
│   ├── telegram_collector.py
│   ├── rss_collector.py
│   ├── web_scraper.py
│   ├── investing_news_collector.py  # ← Investing news → data/news.db
│   ├── egyptian_sources.py
│   ├── keyword_filter.py
│   └── scrappers/
│       ├── __init__.py
│       ├── tradingview_scraper.py
│       ├── tradingview_screener_lists.py
│       ├── tradingview_market_movers.py  # ← 9-tabs scraper (جديد)
│       ├── tradingview_rest.py
│       └── investing_scraper.py         # ← Investing.com sectors/commodities
├── analyzer/
├── sender/
├── data/                   # 🗄️ data/news.db + data/investing_egypt.json
├── db/                     # 🗄️ db/data_engine.db (scrapers)
├── config/
├── scripts/                # 🔧 Utility scripts (incl. import_investing_news.py)
├── ui/                     # 🖥️ FastAPI dashboard
└── tests/
```

---

## 🗄️ قواعد البيانات

| القاعدة | المسار | المدير | الاستخدام |
|---|---|---|---|
| News DB | `data/news.db` | `data/news_store.py` (NewsStore) | الأخبار، التوصيات، OCR |
| Stock DB | `db/data_engine.db` | الـ scrapers | أسعار الأسهم، التبويبات، screener lists |
| Investing JSON | `data/investing_egypt.json` | `investing_scraper.py` | sector/commodity/currency data |

**لا يتم خلط الـ databases.** كل scraper يكتب في القاعدة المناسبة له.

---

## 📋 قائمة التوافق (Checklist)

عند إضافة scraper جديد أو تعديل البيانات:
- [ ] الـ scraper يكتب في `db/data_engine.db` أو `data/news.db` حسب نوعه — ليس في الجذر
- [ ] الـ scraper يحتوي على retry logic للـ timeouts
- [ ] الـ scraper يتعامل مع صفحات لا تحتوي 9 tabs (large/small/high-net-income)
- [ ] تم توثيق الـ scraper في `workflow.md`
- [ ] تم تحديث `CONSTITUTION.md` إذا غيرت البنية
- [ ] تم تحديث `CHANGELOG.md`
- [ ] تم تحديث `AGENTS.md` إذا أضفت commands جديدة
- [ ] لم يتم لمس أي secrets أو .env
- [ ] تم تشغيل الـ test على صفحة واحدة أولاً
- [ ] محرك الـ scraper في `collectors/scrappers/` أو `collectors/` أو `scripts/` (ليس الجذر)

---

## 🤖 دليل الوكلاء

### متى تستخدم `task` (Subagent)؟
- ✅ مهام متعددة خطوات تحتاج بحث كود
- ✅ مراجعة شاملة لكود كبير
- ❌ لا تستخدمها لمهام بسيطة

### متى تستخدم `agent_manager`؟
- ✅ عندما يطلب المستخدم تشغيل جلسات مرئية في VS Code
- ✅ للمهام المعزولة التي تستحق وجودها في UI

### متى تستخدم `kimi-webbridge`؟
- ✅ استخراج بيانات من صفحات ويب تتطلب تفاعلاً
- ⚠️ تتطلب تثبيت امتداد Chrome — شرط يجب على المستخدم
