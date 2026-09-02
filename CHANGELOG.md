# Changelog — News Agent

## [SECURITY-CRITICAL + GLMINVESTMENT-INTEGRATION-AUDIT] — (2026-09-02)

> **توجيه المالك:** "بص على المشروع دة (news). دة المشروع المحلى اللي بيولد الأخبار.
> شوف محتاج تعديلات إيه وأعمل ربط قوي بينه وبين المشروع بتاعنا وتحكم كامل.
> وأكتب اللي أنت عايزه في ملف Agent messages.md عشان لو فيه حاجة محتاج المبرمج بتاعه
> يعملها أنت مش قادر تعملها عندك."

### 🔒 بنود أمنية حرجة (مكتشفة في الساندبوكس)

#### 1. `.env` الحقيقي متسرب على GitHub
- **المشكلة:** ملف `.env` (الذي يحتوي على Telegram API_ID + API_HASH + Bot Token + GLMinvestment PRODUCTION_API_KEY) تم commit في commit `0975b0d` (first commit) وهو مرفوع على GitHub.
- **التأكيد:** `git show HEAD:.env` أرجع القيم الحقيقية لكل 4 أسرار.
- **المطلوب:** revoke فوراً + scrub من git history (BFG أو git filter-repo).
- التفاصيل الكاملة في `Agent messages.md` بند 0.

#### 2. `.venv/` كامل متسرب على GitHub
- **المشكلة:** 7408 ملف Python binaries + packages مرفوعة على GitHub.
- **المطلوب:** `git rm --cached -r .venv/` + scrub من history.
- **السبب:** حجم ضخم + مخالف لـ best practices + ممكن يحتوي cached secrets.

#### 3. `data/news.db` متسرب على GitHub
- **المشكلة:** قاعدة بيانات الأخبار المحلية (13MB) مرفوعة على GitHub.
- **المطلوب:** `git rm --cached data/news.db` + scrub من history.

#### 4. `.gitignore` كان فاضي
- **المشكلة:** المستودع كله ما كانش محمي — ده السبب إن كل حاجة اتـcommit.
- **الحل في الساندبوكس:** كتبت `.gitignore` صح (يحمي .env, .venv/, *.db, __pycache__/, *.session, إلخ).

### 🔧 بنود تعديل كود (محتاجة المبرمج البشري)

كل التفاصيل في `Agent messages.md`. ملخص سريع:

- **بند 2:** إضافة `reasoning` field للـ payload (للـ Decision Logger في GLMinvestment).
- **بند 3:** إضافة `event_type` field (للـ news_impact_scorer classification).
- **بند 4:** توثيق الـ contract في `INTEGRATION.md`.

### ✅ بنود تم تنفيذها في الساندبوكس (مش متـpush)

#### 1. `.env.example` — تنظيف الأسرار
- استبدلت القيم الحقيقية بـ placeholders (`YOUR_TELEGRAM_API_ID_HERE`, إلخ).
- أضفت `PRODUCTION_API_KEY=YOUR_NEWS_AGENT_API_KEY_HERE`.
- أضمت `GLMINVESTMENT_PATH=` متغير جديد للـ cross-repo import.

#### 2. `.gitignore` — إنشاء جديد
- كان فاضي تماماً.
- النسخة الجديدة تحمي: `.env`, `.venv/`, `*.db`, `__pycache__/`, `*.session`, إلخ.

#### 3. `Agent messages.md` — ملف جديد (430 سطر)
- يوثّق 11 بند للتعديلات المطلوبة:
  - بند 0: أمني حرج (scrub .env + .venv/ + data/news.db من history)
  - بند 1: أمني (revoke Telegram + GLMinvestment API key)
  - بنود 2-4: تعديلات في news repo
  - بنود 5-9: تعديلات في GLMinvestment repo
  - بند 10: تفعيل V40_2_NEWS_IMPACT=1 بعد الربط الكامل
- فيه أوامر git جاهزة (BFG, filter-repo) + SQL migrations + code patches.
- فيه Integration Contract Reference (payload, schema, event types).

#### 4. اختبار الربط الفعلي (sandbox only)
- مزامنة API key بين news + GLMinvestment.
- POST /api/news بـ x-agent-key → HTTP 201 → stored in market_news (ID 7895, 7896).
- news_impact_scorer اشتغل على الخبر المتخزن.
- الـ integration شغّال end-to-end:
  ```
  news agent → POST /api/news → GLMinvestment market_news → news_impact_scorer → V40.2
  ```

### القواعد ما اتنكسرتش
- ✅ ما عدّلتش أي كود في news repo (بس .env.example + .gitignore + Agent messages.md + workflow.md).
- ✅ ما عدّلتش أي كود في GLMinvestment (بس نسخت Agent messages.md).
- ✅ مسح الأسرار من .env.example (مش من .env الحقيقي — ده محتاج revoke + scrub من المبرمج).
- ✅ كل التوثيق بالعربي.
- ✅ ما push حاجة على GitHub (بانتظار إذن المالك).

### الخطوات القادمة (محتاجة إذن المالك)
1. 🔴 revoke أسرار Telegram + GLMinvestment API key.
2. 🔴 scrub git history في news repo.
3. 🔴 push: .env.example + .gitignore + Agent messages.md + workflow.md + CHANGELOG.md.
4. 🟡 المبرمج البشري ينفذ بنود Agent messages.md (2-9).
5. 🟡 بعد كده، تفعيل V40_2_NEWS_IMPACT=1 في الإنتاج.
