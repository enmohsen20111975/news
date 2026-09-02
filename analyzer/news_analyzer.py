"""
محلل الأخبار بالذكاء الاصطناعي المحلي (Ollama + Vision)
========================================================
يحلل الخبر ويُخرج:
- قائمة أسهم متأثرة (tickers)
- درجة الأهمية (0-100)
- المشاعر (bullish/bearish/neutral)
- نوع التأثير
- ملخص عربي مختصر
- تحليل الصور إن وجدت (نموذج رؤية)
- نص مستخرج من الصور (OCR)

يستخدم نموذج محلي لفهم سياق الخبر وتأثيره على الأسهم المدرجة.
"""

import os
import json
import logging
import asyncio
import re
import importlib.util
from datetime import datetime
from pathlib import Path

import httpx

from analyzer.vision_analyzer import VisionAnalyzer

log = logging.getLogger('NewsAnalyzer')

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GLM_VPS = os.getenv('GLMINVESTMENT_PATH', str(PROJECT_ROOT.parent / 'GLMinvestment' / 'vps-service'))

TICKER_HINTS = {}
try:
    spec = importlib.util.spec_from_file_location(
        "news_fetcher_analyzer",
        Path(GLM_VPS) / "analyzers" / "news_fetcher_analyzer.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    EGX_TICKER_NAMES = mod.EGX_TICKER_NAMES
    for ticker, names in EGX_TICKER_NAMES.items():
        TICKER_HINTS[ticker.lower()] = ticker
        TICKER_HINTS[names['ar']] = ticker
        TICKER_HINTS[names['en'].lower()] = ticker
except Exception:
    TICKER_HINTS = {
        'cib': 'COMI', 'التجاري الدولي': 'COMI',
        'أموك': 'AMOC', 'طلعت مصطفى': 'TMGH',
        'مدينة نصر': 'MNHD', 'سيدبك': 'SKPC',
    }

IMPORTANCE_KEYWORDS = {
    'urgent': 30, 'عاجل': 30, 'breaking': 25, 'خبر عاجل': 30,
    'رفع أسعار الفائدة': 25, 'خفض أسعار الفائدة': 25,
    'أرباح': 20, 'خسارة': 20, 'نتائج': 18, 'ربع سنوي': 18,
    'توزيع': 15, 'أرباح نقدية': 20, 'أسهم مجانية': 20,
    'اكتتاب': 22, 'إدراج': 18, 'استحواذ': 20, 'اندماج': 22,
    'مليار': 15, 'مليون': 10, 'صفقة': 12,
    'قرار': 10, 'حكومة': 8, 'وزير': 8,
    'صعود': 5, 'هبوط': 5, 'ارتفع': 5, 'انخفض': 5,
    'سوق': 3, 'بورصة': 3,
}

_ENGLISH_NOISE = {
    'HTTP', 'HTTPS', 'POST', 'NEWS', 'INFO', 'HTML', 'JSON', 'API', 'URL',
    'TODAY', 'BREAKING', 'EGP', 'USA', 'UK', 'PDF', 'CEO', 'CFO', 'CTO',
    'IPO', 'GDP', 'CPI', 'FRA', 'CBE', 'WWW', 'COM',
}

_ARABIC_COMPANY_MAP = [
    ('البنك التجاري', 'COMI'), ('التجاري الدولي', 'COMI'), ('CIB', 'COMI'),
    ('طلعت مصطفى', 'TMGH'), ('أوراسكوم', 'ORHD'), ('السويدي', 'SWDY'),
    ('أبو قير', 'ABUK'), ('الشرقية للدخان', 'EAST'),
    ('فوري', 'FWRY'), ('المصرية للاتصالات', 'ETEL'), ('الاتصالات', 'ETEL'),
    ('مدينة نصر', 'MNHD'), ('هيليوبوليس', 'HELI'), ('سوديك', 'OCDI'),
    ('إيبيكو', 'EIPH'), ('سيدي كرير', 'SKPC'), ('موبكو', 'MFPC'),
    ('البنك الأهلي', 'BIEH'), ('البنك السعودي', 'SAIB'),
    ('الهرم', 'HRHO'), ('الإسكندرية', 'ISPH'), ('القاهرة للدواجن', 'CPCI'),
    ('دلتا للسكر', 'DAPH'), ('أجوا', 'AJWA'),
    ('القاهرة للاستثمار', 'CCAP'), ('كابيتال للاستثمار', 'CCAP'),
]


def _extract_tickers_enhanced(original_text: str, clean_text: str, text_lower: str) -> list:
    tickers = []
    for hint, ticker in TICKER_HINTS.items():
        if hint in text_lower or hint in clean_text:
            if ticker not in tickers:
                tickers.append(ticker)

    ticker_patterns = [
        r'\b([A-Z]{3,5})\.CA\b',
        r'\b([A-Z]{3,5})-CA\b',
        r'\b([A-Z]{3,5})-EGP\b',
        r'#([A-Z]{3,5})\b',
    ]
    for pattern in ticker_patterns:
        for m in re.finditer(pattern, original_text):
            tk = m.group(1)
            if tk not in _ENGLISH_NOISE and tk not in tickers:
                tickers.append(tk)

    for pattern, ticker in _ARABIC_COMPANY_MAP:
        if pattern in clean_text or pattern.lower() in text_lower:
            if ticker not in tickers:
                tickers.append(ticker)

    for idx_name in ['EGX30', 'EGX70', 'EGX100']:
        if idx_name in original_text or idx_name in clean_text:
            if idx_name not in tickers:
                tickers.append(idx_name)

    return tickers


SENTIMENT_POSITIVE = [
    'ارتفع', 'صعد', 'قفز', 'نمو', 'أرباح', 'مكاسب', 'اتفاقية',
    'استحواذ', 'توزيع', 'أسهم مجانية', 'رفع', 'نجاح', 'تميز'
]
SENTIMENT_NEGATIVE = [
    'انخفض', 'هبط', 'خسارة', 'خسائر', 'ضغوط', 'تراجع', 'خفض',
    'غرامة', 'عقوبة', 'ديون', 'إفلاس', 'تأخير', 'رفض'
]

IMPACT_TYPES = {
    'earnings':    ['أرباح', 'خسارة', 'نتائج', 'إيرادات', 'ربحية'],
    'dividend':    ['توزيع', 'أرباح نقدية', 'مكافأة'],
    'ipo':         ['اكتتاب', 'إدراج', 'طرح'],
    'acquisition': ['استحواذ', 'اندماج', 'صفقة', 'شراء'],
    'macro':       ['فائدة', 'تضخم', 'دولار', 'جنيه', 'احتياطي', 'بنك مركزي'],
    'regulation':  ['قانون', 'حكومة', 'رسوم', 'ضرائب', 'لائحة'],
    'price_move':  ['صعود', 'هبوط', 'ارتفع', 'انخفض', 'قمة', 'قاع'],
}


class NewsAnalyzer:
    """محلل الأخبار بنموذج Ollama المحلي + Vision + keyword fallback"""

    def __init__(self):
        self.ollama_url      = os.getenv('OLLAMA_URL', 'http://localhost:11434')
        self.model           = os.getenv('OLLAMA_MODEL', 'glm-fast:latest')
        self.fallback_model  = os.getenv('OLLAMA_FALLBACK_MODEL', 'qwen2.5:1.5b')
        self.vision_model    = os.getenv('OLLAMA_VISION_MODEL', '')
        self._ollama_ok      = True
        self._vision_analyzer = VisionAnalyzer()

    async def analyze(self, news: dict) -> dict:
        """حلل الخبر — نص + صور إن وجدت"""
        title = news.get('title', '') or ''
        body  = news.get('body', '') or ''
        original_text = f"{title}\n{body}".strip()

        # 1. تنظيف النص + فهم السياق بـ AI
        clean_text = original_text
        ai_meta = {}
        if self._ollama_ok and original_text and len(original_text) > 20:
            try:
                ai_meta = await self._analyze_with_ollama(original_text) or {}
                if ai_meta.get('clean_text') and len(ai_meta['clean_text']) > 10:
                    clean_text = ai_meta['clean_text']
            except Exception:
                pass

        # 2. فلترة وتبويب في Python
        filtered = self._filter_and_classify(clean_text, original_text, news, ai_meta=ai_meta)

        # 3. تحليل الصور إن وجدت
        image_paths = news.get('image_paths') or []
        if isinstance(image_paths, str):
            try:
                image_paths = json.loads(image_paths)
            except Exception:
                image_paths = []

        if image_paths:
            vision_result = self._vision_analyzer.analyze_images_batch(image_paths)
            if vision_result.get('description') or vision_result.get('ocr_text'):
                filtered = self._merge_vision_result(filtered, vision_result, clean_text)

        filtered['image_paths'] = image_paths
        return filtered

    def _merge_vision_result(self, text_result: dict, vision: dict, clean_text: str) -> dict:
        """دمج نتائج تحليل الصور مع نتائج النص"""
        merged = dict(text_result)

        if vision.get('description'):
            old_summary = merged.get('summary_ar', '')
            vision_desc = vision['description'][:200]
            merged['summary_ar'] = f"{old_summary} | 🖼️ {vision_desc}".strip(' |')

        if vision.get('ocr_text'):
            merged['ocr_text'] = vision['ocr_text']
            ocr_text = vision['ocr_text']
            for hint, ticker in TICKER_HINTS.items():
                if hint.lower() in ocr_text.lower() and ticker not in merged.get('tickers', []):
                    merged.setdefault('tickers', []).append(ticker)

        if vision.get('sentiment') in ('bullish', 'bearish'):
            merged['sentiment'] = vision['sentiment']

        if vision.get('tickers'):
            for t in vision['tickers']:
                if t not in merged.get('tickers', []):
                    merged.setdefault('tickers', []).append(t)

        if vision.get('is_chart'):
            merged['impact_type'] = 'price_move'

        merged['source'] = 'ollama+vision'
        return merged

    def _filter_and_classify(self, clean_text: str, original_text: str, news: dict, ai_meta: dict | None = None) -> dict:
        """فلترة وتبويب الأخبار بالكامل في Python"""
        text_lower = clean_text.lower()
        orig_lower = original_text.lower()
        ai_meta = ai_meta or {}

        # 1. كلمات/keywords وعلامات رفض
        spam_patterns = [
            'لايف', 'بث مباشر', 'اكتب اسم السهم', 'سؤال وجواب',
            'تعليق:', 'share', 'تابعونا', 'يوتيوب', 'facebook',
            'بدأنا اللايف', 'متابعة', 'اشتراك', 'قناة التليجرام',
            'انضم للمجموعة', 'تواصل معنا', 'رابط القناة',
            'مرحبا بك', 'يسعدنا انضمامك', 'قائمة المنشورات',
            'youtube.com', 'youtu.be', 'facebook.com', 'fb.watch',
            'انشر', 'منشن', 'tag', 'إعادة نشر',
        ]
        is_spam = any(p in orig_lower for p in spam_patterns)

        # 2. فلترة URLs فقط (النص اللي مالهوش محتوى غير روابط)
        url_pattern = re.compile(r'https?://\S+')
        urls = url_pattern.findall(clean_text)
        text_without_urls = url_pattern.sub('', clean_text).strip()

        if len(text_without_urls) < 15 and urls:
            is_spam = True

        # 3. فلترة القصير جداً
        if len(clean_text.strip()) < 20:
            is_spam = True

        # 4. استخراج tickers (محسّن — 2026-09-02)
        tickers = _extract_tickers_enhanced(original_text, clean_text, text_lower)

        # دمج tickers من Ollama AI لو موجودة
        ai_tickers = ai_meta.get('tickers', [])
        if ai_tickers:
            for t in ai_tickers:
                if t not in tickers:
                    tickers.append(t)

        # 5. حساب الأهمية
        importance = 10
        for kw, weight in IMPORTANCE_KEYWORDS.items():
            if kw in clean_text or kw.lower() in text_lower:
                importance += weight
        importance = min(100, importance)

        # 6. المشاعر
        pos = sum(1 for w in SENTIMENT_POSITIVE if w in clean_text)
        neg = sum(1 for w in SENTIMENT_NEGATIVE if w in clean_text)
        if pos > neg:
            sentiment = 'bullish'
        elif neg > pos:
            sentiment = 'bearish'
        else:
            sentiment = 'neutral'

        # 7. نوع التأثير
        impact_type = 'general'
        for itype, keywords in IMPACT_TYPES.items():
            if any(k in clean_text for k in keywords):
                impact_type = itype
                break

        # 8. لو AI فهم سياق الخبر، نثق في قراره الإضافي لو موجود
        ai_valid = ai_meta.get('is_valid_news')
        ai_importance = ai_meta.get('importance')
        ai_sentiment = ai_meta.get('sentiment')
        ai_impact = ai_meta.get('impact_type')
        ai_event_type = ai_meta.get('event_type')
        ai_reasoning = ai_meta.get('reasoning')

        if ai_sentiment in ('bullish', 'bearish', 'neutral'):
            sentiment = ai_sentiment
        if ai_impact:
            impact_type = ai_impact
        if isinstance(ai_importance, int) and 0 <= ai_importance <= 100:
            importance = max(importance, ai_importance)

        if ai_valid is False:
            is_spam = True

        is_valid = not is_spam and importance >= 10

        return {
            'is_valid_news': is_valid,
            'news_text': clean_text.strip() if is_valid else '',
            'tickers': tickers,
            'importance': importance if is_valid else 0,
            'sentiment': sentiment if is_valid else 'neutral',
            'impact_type': impact_type if is_valid else 'general',
            'event_type': ai_event_type or impact_type if is_valid else 'general',
            'summary_ar': clean_text.strip() if is_valid else '',
            'summary_en': ai_meta.get('summary_en', ''),
            'reasoning': ai_reasoning or ('ai+python' if ai_meta else 'python_filtered'),
            'source': 'ollama+python',
        }

    async def _analyze_with_ollama(self, text: str) -> dict | None:
        """إرسال الخبر لـ Ollama وانتظار تحليل فهم/أهمية/تأثير/ملخص."""
        prompt = self._build_prompt(text)
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                resp = await client.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"temperature": 0.1, "num_predict": 400}
                    }
                )
                if resp.status_code != 200:
                    raise Exception(f"HTTP {resp.status_code}")

                raw = resp.json().get('response', '')
                return self._parse_ollama_response(raw, text)

        except Exception as e:
            log.warning(f"Ollama error ({self.model}): {e}")
            if self.model != self.fallback_model:
                try:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        resp = await client.post(
                            f"{self.ollama_url}/api/generate",
                            json={"model": self.fallback_model, "prompt": prompt,
                                  "stream": False, "options": {"temperature": 0.1, "num_predict": 300}}
                        )
                        raw = resp.json().get('response', '')
                        return self._parse_ollama_response(raw, text)
                except Exception as e2:
                    log.warning(f"Fallback model also failed: {e2}")
            self._ollama_ok = False
            return None

    def _build_prompt(self, text: str) -> str:
        return f"""أنت محلل أخبار مالية متخصص في البورصة المصرية.
حلل الخبر التالي وأخرج JSON فقط بالحقول المطلوبة:

{{
  "is_valid_news": true/false,
  "clean_text": "نص الخبر بعد تنظيفه من الهراء والروابط والاشتراكات",
  "summary_ar": "ملخص قصير بالعربية",
  "summary_en": "short English summary",
  "importance": 0-100,
  "sentiment": "bullish/bearish/neutral",
  "impact_type": "earnings/dividend/ipo/acquisition/macro/regulation/price_move/general",
  "event_type": "IPO_SUBSCRIPTION|DIVIDEND_EX_DATE|EARNINGS_BEAT|EARNINGS_MISS|MA_ACQUISITION|REGULATORY_APPROVAL|STOCK_SPLIT|MANAGEMENT_CHANGE|CONTRACT_AWARD|EXPANSION|FRAUD|HALT|GENERAL",
  "reasoning": "سبب قصير بالعربي ليه الخبر مهم أو مش مهم وإيه تأثيره المتوقع",
  "affected_tickers": ["COMI", ...]
}}

الخبر:
{text}

JSON فقط بدون أي نص إضافي."""

    def _parse_ollama_response(self, raw: str, original_text: str) -> dict:
        """استخرج JSON من رد Ollama"""
        match = re.search(r'\{[\s\S]*\}', raw)
        if match:
            try:
                data = json.loads(match.group())
                data.setdefault('clean_text', original_text)
                data.setdefault('is_valid_news', True)
                if data.get('affected_tickers') and not data.get('tickers'):
                    data['tickers'] = data.pop('affected_tickers', [])
                data.setdefault('tickers', [])
                return data
            except json.JSONDecodeError:
                pass
        return {'clean_text': original_text, 'tickers': []}

    async def _analyze_with_keywords(self, text: str, news: dict) -> dict:
        """تحليل بسيط بالكلمات المفتاحية — لا يحتاج Ollama"""
        text_lower = text.lower()

        tickers = []
        for hint, ticker in TICKER_HINTS.items():
            if hint in text_lower or hint in text:
                if ticker not in tickers:
                    tickers.append(ticker)

        importance = 10
        for kw, weight in IMPORTANCE_KEYWORDS.items():
            if kw in text or kw.lower() in text_lower:
                importance += weight
        importance = min(100, importance)

        pos = sum(1 for w in SENTIMENT_POSITIVE if w in text)
        neg = sum(1 for w in SENTIMENT_NEGATIVE if w in text)
        if pos > neg:
            sentiment = 'bullish'
        elif neg > pos:
            sentiment = 'bearish'
        else:
            sentiment = 'neutral'

        impact_type = 'general'
        for itype, keywords in IMPACT_TYPES.items():
            if any(k in text for k in keywords):
                impact_type = itype
                break

        title = news.get('title', '') if isinstance(news, dict) else ''
        summary = title[:100] if title else text[:100]

        is_valid = bool(tickers) or importance > 30

        return {
            'is_valid_news': is_valid,
            'news_text': summary if is_valid else '',
            'tickers':     tickers,
            'importance':  importance,
            'sentiment':   sentiment,
            'impact_type': impact_type,
            'summary_ar':  summary,
            'summary_en':  '',
            'reasoning':   'keyword_fallback',
        }
