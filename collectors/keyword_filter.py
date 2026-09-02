"""
فلتر ذكي لتحديد صلة الخبر بالبورصة المصرية
==========================================
ثلاث طبقات:
1. Keyword hard-match (سريع، 100% دقة في الكلمات الواضحة)
2. EGX ticker symbols (COMI.CA, EAST, إلخ)
3. AI fallback (Ollama) للأسئلة الغامضة

الفلسفة:
- لو الخبر فيه أي من الكلمات الواضحة → مقبول فوراً
- لو مفيش → AI يقرر بسرعة
- لو AI فشل أو غير متاح → fallback نهائي: نسمح بمرور نص قصير (< 200 char)
  عشان ما نفقدش أخبار محتملة
"""

import os
import re
import logging
import asyncio
from functools import lru_cache

log = logging.getLogger('KeywordFilter')

EGX_TICKERS = {
    # أكبر 30 سهم في EGX (مختق، بدون .CA)
    'COMI', 'HRHO', 'EAST', 'EFIH', 'EFID', 'JUFO', 'CIEB', 'TMGH', 'PHDC',
    'SWDY', 'EKHO', 'HELI', 'ESRS', 'ORWE', 'CCAP', 'AMOC', 'EGCH', 'ETEL',
    'ABUK', 'SKPC', 'OFH', 'CLHO', 'OIH', 'PHAR', 'GBCO', 'IRAX', 'MNHD',
    'SMFR', 'OCDI', 'AXA', 'PIOH', 'PACH', 'PINS', 'PRDC', 'OCDI', 'ALCN',
    'ATQA', 'BINV', 'BTFH', 'CANA', 'CCRS', 'CEFM', 'CIRA', 'CLAG', 'CSAG',
    'DOMT', 'DSCW', 'EDFM', 'EGAS', 'EHDR', 'EMFD', 'EPPK', 'ESAC', 'ETRS',
    'FWRY', 'GBCO', 'GHRI', 'GSSC', 'ICID', 'IDRE', 'ISPH', 'KRDI', 'LCSW',
    'MFPC', 'MOIL', 'MPCO', 'NAHO', 'NINH', 'OBRI', 'OCDI', 'ORHD', 'OSAB',
    'RAKW', 'RDIH', 'REAC', 'RREL', 'SCEM', 'SDTI', 'SIPM', 'SKPC', 'SPMD',
    'SUKR', 'TALM', 'TORA', 'UEGC', 'UNIT', 'WCDF', 'ZMID',
}

EGX_INDICES = {
    'EGX30', 'EGX70', 'EGX100', 'EGX50', 'EGX20',
    'مؤشر', 'الشريعة', 'EWI',
}

EGX_KEYWORDS_AR = {
    'البورصة', 'البورصة المصرية', 'الأسهم', 'سهم', 'أسهم',
    'تداولات', 'تداول', 'مؤشر', 'مؤشرات',
    'إدراج', 'شطب', 'قيد', 'الهيئة', 'الرقابة المالية',
    'عمومية', 'جمعية عمومية', 'مساهمين', 'مساهم',
    'توزيعات', 'أرباح', 'أرباح', 'توزيعات أرباح', 'كوبون',
    'استحواذ', 'اندماج', 'تخارج', 'حصص',
    'رأس المال', 'رأس المال', 'زيادة رأس المال', 'تخفيض رأس',
    'القيد', 'هيئة الاستثمار', 'الهيئة العامة للاستثمار',
    'صانع السوق', 'صانع', 'سيولة', 'تسوية',
    'الجلسة', 'افتتاح', 'إغلاق',
    'أسهم حرة', 'free float', 'تداول',
    'شركة', 'شركات', 'مساهمة',
    'استثمار', 'استثمارات',
}

EGX_KEYWORDS_EN = {
    'stock', 'stocks', 'shares', 'equity', 'equities',
    'trading', 'trade', 'investor', 'investors',
    'earnings', 'revenue', 'profit', 'dividend',
    'merger', 'acquisition', 'IPO', 'listing',
    'EGX', 'Cairo', 'Egyptian Exchange',
    'fiscal year', 'quarterly', 'annual report',
    'FRA', 'Financial Regulatory Authority',
    'EGX-listed', 'listed company',
}


class KeywordFilter:
    """يقرر هل الخبر متعلق بـ EGX أم لا"""

    def __init__(self, ollama_url: str | None = None):
        self.ollama_url = ollama_url or os.getenv('OLLAMA_URL', 'http://localhost:11434')
        self.model = os.getenv('OLLAMA_MODEL', 'glm-fast:latest')
        self.fallback_model = os.getenv('OLLAMA_FALLBACK_MODEL', 'qwen2.5:1.5b')
        self.ai_enabled = os.getenv('KEYWORD_FILTER_USE_AI', '1').lower() in ('1', 'true', 'yes')

        self._compile_patterns()

    def _compile_patterns(self):
        all_kw = (
            EGX_TICKERS
            | EGX_INDICES
            | EGX_KEYWORDS_AR
            | EGX_KEYWORDS_EN
        )
        escaped = sorted(all_kw, key=len, reverse=True)
        pattern = '|'.join(re.escape(k) for k in escaped)
        self._kw_regex = re.compile(rf'\b({pattern})\b', re.UNICODE | re.IGNORECASE)

    def quick_match(self, text: str) -> bool:
        """فحص سريع بالكلمات المفتاحية — synchronous، بدون AI"""
        if not text or len(text.strip()) < 10:
            return False
        if self._kw_regex.search(text):
            return True
        if self._has_ticker_like(text):
            return True
        return False

    @staticmethod
    def _has_ticker_like(text: str) -> bool:
        """يبحث عن أنماط زي COMI.CA أو COMI-CA"""
        return bool(re.search(r'\b[A-Z]{3,5}(?:[\.\-]CA)\b', text))

    async def is_relevant(self, text: str, title: str = '') -> tuple[bool, str]:
        """يقرر هل الخبر متعلق بـ EGX

        Returns:
            (is_relevant, reason)
            reason: 'keyword' | 'ai' | 'fallback_short' | 'no'
        """
        full_text = f'{title}\n{text}'.strip()
        if self.quick_match(full_text):
            return True, 'keyword'
        if not self.ai_enabled:
            return False, 'no'
        try:
            decision = await self._ask_ai(full_text)
            return decision, 'ai'
        except Exception as e:
            log.debug(f'AI filter failed: {e}')
            return len(full_text) < 300, 'fallback_short'

    async def filter_batch(self, items: list[dict], text_field: str = 'body') -> list[dict]:
        """يفلتر batch من الأخبار — يحتفظ فقط بالمتعلقة بـ EGX"""
        if not items:
            return []
        kept = []
        for item in items:
            text = item.get(text_field, '') or item.get('title', '')
            title = item.get('title', '')
            ok, reason = await self.is_relevant(text, title)
            if ok:
                item['_filter_reason'] = reason
                kept.append(item)
            else:
                log.debug(f'رفض: {title[:60]} — reason={reason}')
        return kept

    async def _ask_ai(self, text: str) -> bool:
        """يسأل Ollama بسرعة هل الخبر عن البورصة المصرية"""
        prompt = (
            'هل الخبر التالي عن البورصة المصرية (EGX) أو الأسهم المدرجة فيها؟\n'
            'أجب بكلمة واحدة فقط: yes أو no\n\n'
            f'الخبر:\n{text[:600]}\n\nالإجابة:'
        )
        for model in (self.model, self.fallback_model):
            try:
                import httpx
                async with httpx.AsyncClient(timeout=20.0) as client:
                    resp = await client.post(
                        f'{self.ollama_url}/api/generate',
                        json={
                            'model': model,
                            'prompt': prompt,
                            'stream': False,
                            'options': {'temperature': 0.0, 'num_predict': 5},
                        },
                    )
                    if resp.status_code == 200:
                        out = resp.json().get('response', '').strip().lower()
                        if 'yes' in out or 'نعم' in out:
                            return True
                        if 'no' in out or 'لا' in out:
                            return False
                        continue
            except Exception as e:
                log.debug(f'AI filter model={model} failed: {e}')
                continue
        return False


filter_instance = KeywordFilter()