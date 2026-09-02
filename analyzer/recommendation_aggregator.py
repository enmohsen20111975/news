"""
مجمّع توصيات الخبراء المحلي (Ollama)
=====================================
يجمع التوصيات المشابهة من عدة قنوات تيليجرام (وأي مصدر) ويطلع توصية واحدة
موحّدة لكل سهم بناءً على الأغلبية.

الأنابيب:
1. اختيار الأخبار المرشّحة من news.db (تحتوي توصية/دعم/مقاومة/استهدف/...).
2. إرسال دفعة لكل سهم لـ Ollama لتحليل موحّد.
3. تخزين التوصيات النهائية في expert_recommendations المحلية.
4. ProductionSender يرفعها لـ GLMinvestment عبر /api/expert-recommendations/import.

يعمل حتى لو AI غير متاح — في كل حالة يختار أسهم واضحة ويُسجّلها من النص الأصلي.
"""

import os
import re
import json
import logging
import asyncio
import httpx
import hashlib
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger('RecommendationAggregator')

RECOMMENDATION_HINTS = [
    'توصية', 'توصيات', 'نوصي', 'موصى', 'شراء', 'بيع', 'احتفاظ',
    'دعم', 'مقاومة', 'استهدف', 'هدف', 'وقف', 'متوسط', 'TP', 'SL',
    'تريدة', 'مضاربة', 'شراء مع وقف',
]

ACTION_BUY = {'شراء', 'شراء مع وقف', 'شراء واحتفاظ', 'احتفاظ', 'تريدة', 'مضاربة'}
ACTION_SELL = {'بيع', 'تخارج', 'تصريف'}


def _build_ticker_index() -> dict[str, str]:
    """خريطة (نص → ticker) من EGX_TICKER_NAMES إن أمكن، وإلا قائمة بسيطة."""
    try:
        import importlib.util
        from pathlib import Path
        project = Path(__file__).resolve().parents[1]
        glm_vps = os.getenv('GLMINVESTMENT_PATH', str(project.parent / 'GLMinvestment' / 'vps-service'))
        spec = importlib.util.spec_from_file_location(
            'news_fetcher_analyzer',
            Path(glm_vps) / 'analyzers' / 'news_fetcher_analyzer.py',
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        idx: dict[str, str] = {}
        for tk, names in mod.EGX_TICKER_NAMES.items():
            idx[names['ar']] = tk
            idx[names['en'].lower()] = tk
        return idx
    except Exception:
        return {
            'cib': 'COMI', 'التجاري الدولي': 'COMI', 'البنك التجاري': 'COMI',
            'أموك': 'AMOC', 'طلعت مصطفى': 'TMGH',
            'مدينة نصر': 'MNHD', 'سيدبك': 'SKPC',
            'أبو قير': 'ABUK', 'موبكو': 'MFPC', 'سيدي كرير': 'SKPC',
            'إعمار': 'EMFD', 'مصر الجديدة': 'MNHD',
            'مصر الألومنيوم': 'EGAL', 'سوديك': 'OCDI',
        }


TICKER_INDEX = _build_ticker_index()


class RecommendationAggregator:
    """يجمّع توصيات الأسهم المتشابهة من كل المصادر ويطلع توصية محسّنة."""

    def __init__(self, store):
        self.store = store
        self.ollama_url = os.getenv('OLLAMA_URL', 'http://localhost:11434')
        self.model = os.getenv('OLLAMA_MODEL', 'glm-fast:latest')
        self.fallback_model = os.getenv('OLLAMA_FALLBACK_MODEL', 'qwen2.5:1.5b')
        self.expert_name = os.getenv('EXPERT_AGGREGATOR_NAME', 'تحليل مجمّع (AI محلي)')
        self.expert_source = os.getenv('EXPERT_AGGREGATOR_SOURCE', 'news_agent_aggregator')
        self.min_sources = int(os.getenv('RECOMMENDATION_MIN_SOURCES', '1'))
        self.lookback_hours = int(os.getenv('RECOMMENDATION_LOOKBACK_HOURS', '48'))
        self.session_date = datetime.now().strftime('%Y-%m-%d')

    async def run(self) -> int:
        """نفّذ خطوة التجميع: استخرج → جمّع → خزّن محلياً. يرجع عدد التوصيات المُضافة."""
        candidates = self.store.get_recommendation_candidates(since_hours=self.lookback_hours)
        if not candidates:
            log.info('Aggregator: لا يوجد مرشحين')
            return 0

        grouped = self._group_by_symbol(candidates)
        if not grouped:
            log.info('Aggregator: لا توجد مجموعات بعد التجميع')
            return 0

        log.info(f'Aggregator: {len(grouped)} سهم مرشح ({sum(len(v) for v in grouped.values())} خبر)')

        added = 0
        skipped_no_price = 0
        for symbol, items in grouped.items():
            if len(items) < self.min_sources:
                continue
            try:
                rec = await self._aggregate_symbol(symbol, items)
                if rec:
                    if not rec.get('entry_price'):
                        skipped_no_price += 1
                        log.debug(f'Aggregator: تخطّي {symbol} — لا يوجد سعر دخول')
                        continue
                    rid = self.store.add_recommendation(rec)
                    if rid:
                        added += 1
                        log.info(
                            f'Aggregator: ➕ {symbol} → {rec["action"]} '
                            f'(entry={rec.get("entry_price")}, target={rec.get("target_price")}, '
                            f'stop={rec.get("stop_loss")}, sources={len(items)})'
                        )
            except Exception as e:
                log.warning(f'Aggregator: فشل {symbol}: {e}')

        log.info(f'Aggregator: {added} توصية جديدة ({skipped_no_price} بدون سعر دخول)')
        return added

    def _group_by_symbol(self, candidates: list[dict]) -> dict[str, list[dict]]:
        """اجمع الأخبار حسب الـ ticker."""
        groups: dict[str, list[dict]] = {}
        for item in candidates:
            tickers = self._parse_tickers(item.get('tickers'))
            if not tickers:
                tickers = self._extract_tickers_from_text(item.get('title', ''), item.get('body', ''))
            if not tickers:
                continue
            text = (item.get('title') or '') + ' ' + (item.get('body') or '')
            if not self._looks_like_recommendation(text):
                continue
            for tk in tickers[:2]:
                groups.setdefault(tk, []).append(item)
        return groups

    @staticmethod
    def _parse_tickers(raw) -> list[str]:
        if not raw:
            return []
        try:
            if isinstance(raw, str):
                loaded = json.loads(raw)
            else:
                loaded = raw
            return [str(t).upper() for t in loaded if t]
        except Exception:
            return []

    @staticmethod
    def _extract_tickers_from_text(title: str, body: str) -> list[str]:
        """استخرج tickers على شكل XXX أو XXX.CA أو XXX-CA أو اسم عربي من العنوان والجسم."""
        text = f"{title}\n{body}"
        candidates: list[str] = []
        for m in re.finditer(r'\b([A-Z]{3,5})(?:\.[CA]|-CA)\b', text):
            tk = m.group(1)
            if tk not in candidates:
                candidates.append(tk)
        for hint, tk in TICKER_INDEX.items():
            if hint and len(hint) >= 3 and hint in text and tk not in candidates:
                candidates.append(tk)
        for m in re.finditer(r'\b([A-Z]{4})\b', text):
            word = m.group(1)
            if word in {'HTTP', 'HTTPS', 'POST', 'NEWS', 'INFO', 'HTML'}:
                continue
            if word not in candidates:
                candidates.append(word)
        return candidates[:4]

    @staticmethod
    def _looks_like_recommendation(text: str) -> bool:
        """فحص سريع: هل النص يحوي كلمات توصية؟"""
        if not text or len(text) < 30:
            return False
        text_lower = text.lower()
        score = sum(1 for h in RECOMMENDATION_HINTS if h.lower() in text_lower)
        return score >= 2

    async def _aggregate_symbol(self, symbol: str, items: list[dict]) -> dict | None:
        """حلل مجموعة أخبار لسهم واحد بـ Ollama."""
        combined_text = self._combine_items(items)
        ai_result = await self._ask_ollama(combined_text, symbol)

        sources_ids = list({i['id'] for i in items})
        sources_labels = sorted({i.get('source', '') for i in items if i.get('source')})

        if ai_result:
            ai_result.setdefault('stock_symbol', symbol)
            ai_result.setdefault('stock_name_ar', '')
            ai_result.setdefault('action', 'BUY')
            ai_result.setdefault('recommendation_type', 'aggregated')
            ai_result['session_date'] = self.session_date
            ai_result['expert_name'] = self.expert_name
            ai_result['expert_source'] = self.expert_source
            ai_result['source_news_ids'] = sources_ids
            ai_result['notes'] = (
                f"مجمّع من {len(items)} خبر عبر القنوات: {', '.join(sources_labels)[:200]}. "
                f"⚠️ تحليل آلي محلي — ليس توصية مالية."
            )
            return ai_result

        return self._fallback_from_text(symbol, items, sources_ids, sources_labels)

    def _combine_items(self, items: list[dict]) -> str:
        parts = []
        for i in items[:8]:
            title = (i.get('title') or '').strip()
            body = (i.get('body') or '').strip()[:400]
            src = i.get('source', '')
            parts.append(f"[{src}] العنوان: {title}\nالنص: {body}")
        return '\n---\n'.join(parts)

    async def _ask_ollama(self, text: str, symbol: str) -> dict | None:
        prompt = self._build_prompt(text, symbol)
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f'{self.ollama_url}/api/generate',
                    json={
                        'model': self.model,
                        'prompt': prompt,
                        'stream': False,
                        'options': {'temperature': 0.1, 'num_predict': 350},
                    },
                )
                if resp.status_code != 200:
                    raise Exception(f'HTTP {resp.status_code}')
                raw = resp.json().get('response', '')
                return self._parse_response(raw)
        except Exception as e:
            log.warning(f'Aggregator: Ollama error: {e}')
            if self.model != self.fallback_model:
                try:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        resp = await client.post(
                            f'{self.ollama_url}/api/generate',
                            json={
                                'model': self.fallback_model,
                                'prompt': prompt,
                                'stream': False,
                                'options': {'temperature': 0.1, 'num_predict': 250},
                            },
                        )
                        raw = resp.json().get('response', '')
                        return self._parse_response(raw)
                except Exception as e2:
                    log.warning(f'Aggregator: fallback failed: {e2}')
            return None

    def _build_prompt(self, text: str, symbol: str) -> str:
        return f"""أنت محلل أسهم محترف في البورصة المصرية. السهم المطلوب: {symbol}.
عندك عدة رسائل/تغريدات من قنوات تيليجرام مختلفة عن نفس السهم.
مهمتك: استخرج توصية موحّدة واحدة فقط.

القواعد:
- action = "BUY" لو أغلب المصادر اشترت/وصّت بالشراء، "SELL" لو أغلبها بيع، "HOLD" لو متوسطة.
- entry_price: سعر الدخول الأهم المذكور في النصوص (رقم موجب فقط، بدون عملة).
- target_price: الهدف الأول المذكور، target_price_2: الهدف الثاني.
- stop_loss: وقف الخسارة المذكور.
- support_level / resistance_level: مستويات الدعم/المقاومة إن ظهرت.
- لازم يكون عندك entry_price وإلا الـ recommendation غير مقبول.
- technical_analysis: جملة أو جملتين فنيين بالعربي.
- recommendation_reason: سبب التوصية بجملة واحدة.
- summary_ar: ملخص قصير جداً.

⚠️ لا تضف نص أو كلام خارج JSON. أخرج JSON صالح فقط:

{{
  "stock_symbol": "{symbol}",
  "stock_name_ar": "الاسم العربي إن ظهر",
  "action": "BUY" | "SELL" | "HOLD",
  "recommendation_type": "شراء واحتفاظ" | "دعم / ارتداد" | "T+1 / مضاربة" | "متوسط / تجميع" | "تفريغ",
  "entry_price": 0,
  "entry_price_from": 0,
  "entry_price_to": 0,
  "target_price": 0,
  "target_price_2": 0,
  "stop_loss": 0,
  "support_level": 0,
  "resistance_level": 0,
  "technical_analysis": "...",
  "recommendation_reason": "...",
  "summary_ar": "..."
}}

النصوص من القنوات:
{text}
"""

    @staticmethod
    def _parse_response(raw: str) -> dict | None:
        match = re.search(r'\{[\s\S]*\}', raw)
        if not match:
            return None
        try:
            data = json.loads(match.group())
        except json.JSONDecodeError:
            return None
        cleaned = {}
        for k, v in data.items():
            if v in (None, '', 'null'):
                continue
            if k in ('entry_price', 'entry_price_from', 'entry_price_to',
                     'target_price', 'target_price_2', 'stop_loss',
                     'support_level', 'resistance_level'):
                try:
                    num = float(v)
                    if num > 0:
                        cleaned[k] = num
                except (TypeError, ValueError):
                    continue
            else:
                cleaned[k] = v
        return cleaned or None

    def _fallback_from_text(self, symbol: str, items: list[dict],
                            sources_ids: list[str], sources_labels: list[str]) -> dict | None:
        """Fallback لو AI فشل: يستخرج أرقام من النص مباشرة."""
        text = ' '.join((i.get('title', '') + ' ' + i.get('body', '')) for i in items)
        prices = [float(x) for x in re.findall(r'\b\d{1,3}(?:[.,]\d{1,2})?\b', text)]
        prices = [p for p in prices if 0.1 < p < 5000]
        if not prices:
            return None
        prices.sort()
        entry = prices[len(prices) // 2]
        target = max(prices) if len(prices) > 1 else None
        stop = min(prices) if len(prices) > 1 else None
        buy_words = sum(1 for w in ACTION_BUY if w in text)
        sell_words = sum(1 for w in ACTION_SELL if w in text)
        action = 'BUY' if buy_words >= sell_words else 'SELL'
        return {
            'stock_symbol': symbol,
            'action': action,
            'recommendation_type': 'aggregated_fallback',
            'entry_price': entry,
            'target_price': target,
            'stop_loss': stop,
            'technical_analysis': 'استخراج آلي للأرقام من النصوص (بدون AI)',
            'recommendation_reason': 'لم يستطع النموذج اللغوي التحليل — تم استخدام استخراج رقمي بسيط',
            'summary_ar': f'توصية مجمّعة (fallback) للسهم {symbol} بناءً على {len(items)} خبر.',
            'session_date': self.session_date,
            'expert_name': self.expert_name + ' (fallback)',
            'expert_source': self.expert_source,
            'source_news_ids': sources_ids,
            'notes': (
                f'Fallback من {len(items)} خبر. المصادر: {", ".join(sources_labels)[:200]}. '
                '⚠️ يجب مراجعة يدوية.'
            ),
        }