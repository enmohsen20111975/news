# News Agent — دليل الوكلاء والمهام

> دليل سريع للوكلاء (Agents) والمهام (Commands) في المشروع. يتم تحديثه مع كل تغيير بنيوي.
> آخر تحديث: 2026-09-03

## 🎯 الهدف العام

مشروع **News Agent** هو وكيل أخبار مالي محلي متخصص في بورصة مصر (EGX)، يجمع أخباراً، يحللها بالذكاء الاصطناعي المحلي (Ollama)، وينشرها للموقع الرسمي ومنصات التواصل.

---

## 🏗️ المهام (Commands) المتوفرة

### التشغيل اليومي
| المهمة | الأمر | الوصف |
|---|---|---|
| تشغيل كل شيء | `run.bat` | ينشئ الـ venv، يثبت الـ deps، يتحقق من Ollama، يفتح الداشبورد في المتصفح، ويبدأ الوكيل |
| تشغيل الواجهة فقط | `run_dashboard.bat` / `run_dashboard.ps1` / `run_dashboard.sh` | يشغل FastAPI dashboard على port 8001 بدون main.py |
| مراقبة CLI | `python monitor.py` | إحصائيات سريعة من data/news.db |
| تشغيل investing scraper | `run_investing_scraper.bat` | يشغل investing_scraper.py كل ساعة تلقائياً |

### الـ Scrapers (جمع بيانات الأسواق)
| المهمة | الأمر | قاعدة البيانات |
|---|---|---|
| 9-tabs scraper (الجديد) | `python collectors/scrappers/tradingview_market_movers.py` | `db/data_engine.db` |
| Screener lists | `python collectors/scrappers/tradingview_screener_lists.py` | `db/data_engine.db` |
| Full market scraper | `python collectors/scrappers/tradingview_scraper.py` | `db/data_engine.db` |
| REST fetcher (لا يحتاج Playwright) | `python collectors/scrappers/tradingview_rest.py --market egypt` | `db/data_engine.db` |
| Stock ticker backfill | `python scripts/backfill_tickers.py` | `db/data_engine.db` |
| Investing.com market data | `python collectors/scrappers/investing_scraper.py` | `data/investing_egypt.json` |
| Investing.com news collector | `python collectors/investing_news_collector.py` | `data/news.db` |

> ⚠️ **مهم**: جميع الـ scrapers مستقلة ولا تستخدم `main.py`. الـ scrapers اللي بتخزن في `db/data_engine.db` (TradingView) مستقلة عن الـ collectors اللي بتخزن في `data/news.db` (Investing News، Telegram، RSS، Web).

### التحليل
| المهمة | الأمر |
|---|---|
| بناء أو تحديث فهرس الأسهم | `python scripts/build_stocks_index.py` |
| اختبار التخزين | `python -m unittest tests/test_news_store.py` |

### التشخيص
| المهمة | الأمر |
|---|---|
| تشخيص الوكلاء | `.kimi-webbridge/bin/kimi-webbridge status` |
| تشغيل الوكيل المتعدد جلسات | `agent_manager` (VS Code extension) |

---

## 📁 البنية المعمارية

```
news_agent/
├── main.py              # ⚙️ Orchestration engine (Collect → Analyze → Send)
├── monitor.py           # 📊 CLI monitor
├── run.bat              # ▶️ One-click launcher (opens browser automatically)
├── run_dashboard.*     #   Dashboard-only scripts
├── CONSTITUTION.md     # 📜 Project rules (v1.1)
├── workflow.md         # 📋 Operations guide + API contract
├── INTEGRATION.md      # 🔗 GLMinvestment integration contract
├── CHANGELOG.md        # 📝 Change history
├── AGENTS.md           # 👈 هذا الملف
├── collectors/         # 📥 News collection
│   ├── telegram_collector.py
│   ├── rss_collector.py
│   ├── web_scraper.py
│   ├── egyptian_sources.py
│   ├── keyword_filter.py
│   └── scrappers/      # 📈 Stock market data scrapers
│       ├── tradingview_rest.py
│       ├── tradingview_scraper.py
│       ├── tradingview_screener_lists.py
│       └── tradingview_market_movers.py
├── analyzer/            # 🧠 AI analysis (Ollama)
├── sender/              # 📤 Publishing
├── data/                # 🗄️ data/news.db (NewsStore)
├── db/                  # 🗄️ db/data_engine.db (scrapers)
├── config/              # ⚙️ Source registry
├── scripts/             # 🔧 Utility scripts
├── ui/                  # 🖥️ FastAPI dashboard
└── tests/               # ✅ Unit tests
```

---

## 🗄️ قواعد البيانات

| القاعدة | المسار | المدير | الاستخدام |
|---|---|---|---|
| News DB | `data/news.db` | `data/news_store.py` | الأخبار، التوصيات، OCR |
| Stock DB | `db/data_engine.db` | الـ scrapers | أسعار الأسهم، التبويبات، screener lists |

**لا يتم خلط الـ databases. كل scraper يكتب في `db/data_engine.db` فقط.**

---

## 🔄 دائرة حياة التطوير

1. **قراءة إلزامية**: قراءة `CONSTITUTION.md` + `workflow.md` قبل أي تعديل
2. **التخطيط**: تحديد الملف المالك وتأثير التغيير على باقي المشروع
3. **التنفيذ**: تغيير أصغر حجم ممكن
4. **الاختبار**: تشغيل الـ scraper على صفحة واحدة، التحقق من عدد الأعمدة والصفوف
5. **التوثيق**: تحديث `CONSTITUTION.md` + `workflow.md` + `CHANGELOG.md` بعد الانتهاء

---

## 💬 دليل الوكلاء (Agent Guide)

### متى تستخدم `task` (Subagent)؟
- ✅ مهام متعددة خطوات تحتاج بحث كود (مثلاً: إيجاد كل الـ scrapers وتحليلها)
- ✅ مراجعة شاملة لكود كبير
- ❌ لا تستخدمها لمهام بسيطة (استخدم الأدوات المباشرة بدلاً من ذلك)

### متى تستخدم `agent_manager`؟
- ✅ عندما يطلب المستخدم تشغيل جلسات مرئية في VS Code
- ✅ للمهام المعزولة التي تستحق وجودها في UI

### متى تستخدم `kimi-webbridge`؟
- ✅ استخراج بيانات من صفحات ويب تتطلب تفاعلاً (نقر تبويبات، تمرير، كتابة)
- ✅ عندما يكون Playwright غير مثبت أو محظور
- ⚠️ تتطلب تثبيت امتداد Chrome — شرط يجب على المستخدم

---

## 📋 قائمة التوافق (Checklist)

عند إضافة scraper جديد أو تعديل البيانات:
- [ ] الـ scraper يستخدم `db/data_engine.db` (ليس `data/news.db`) — ما عدا Investing News اللي بيستخدم `data/news.db`
- [ ] الـ scraper يحتوي على retry logic للـ timeouts
- [ ] الـ scraper يتعامل مع صفحات لا تحتوي 9 tabs (large/small/high-net-income)
- [ ] تم توثيق الـ scraper في `workflow.md`
- [ ] تم تحديث `CONSTITUTION.md` إذا غيرت البنية
- [ ] تم تحديث `CHANGELOG.md`
- [ ] تم تحديث `AGENTS.md` إذا أضفت commands جديدة
- [ ] لم يتم لمس أي secrets أو .env
- [ ] تم تشغيل الـ test على صفحة واحدة أولاً
- [ ] محرك الـ scraper في `collectors/scrappers/` أو `collectors/` (ليس الجذر)
