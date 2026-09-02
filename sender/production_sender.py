"""
المُرسِل: يبعت الأخبار المحللة مباشرة لـ GLMinvestment
بدون تكرار — GLMinvestment يتولى الـ dedup بـ UNIQUE(title, source)
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path

import httpx

log = logging.getLogger('ProductionSender')


class ProductionSender:
    """يبعت الأخبار المحللة لـ GLMinvestment مباشرة"""

    def __init__(self):
        endpoints = []
        local = os.getenv('LOCAL_SITE_URL', 'http://localhost:3000').strip()
        if local:
            endpoints.append(f"{local.rstrip('/')}/api/news")
        prod = os.getenv('PRODUCTION_SERVER_URL', '').strip()
        if prod and prod != local:
            endpoints.append(f"{prod.rstrip('/')}/api/news")
        self.endpoints = list(dict.fromkeys(endpoints)) or ['http://localhost:3000/api/news']
        self.local_news_endpoint = self.endpoints[0]
        self.api_key = os.getenv('PRODUCTION_API_KEY', '')

        self.base_urls = [e.rsplit('/api/', 1)[0] for e in self.endpoints]
        self.base_urls = list(dict.fromkeys(self.base_urls))

    async def send_batch(self, items: list[dict]) -> int:
        """إرسال مباشرة لـ GLMinvestment (محلياً وللسيرفر الإنتاجي معاً)"""
        if not items:
            return 0

        sent = 0
        for item in items:
            item_sent = False
            formatted = self._format_for_site(item)
            headers = {
                'Content-Type': 'application/json',
                'x-agent-key': self.api_key,
                'X-News-Agent-Key': self.api_key,
            }

            for endpoint in self.endpoints:
                try:
                    async with httpx.AsyncClient(timeout=15.0) as client:
                        resp = await client.post(endpoint, json=formatted, headers=headers)
                        if resp.status_code in (200, 201):
                            data = resp.json()
                            if data.get('duplicate'):
                                log.debug(f"  ↳ مكرر على {endpoint}: {item.get('title', '')[:40]}")
                            else:
                                log.info(f"  ✓ استلم ({endpoint}): {item.get('title', '')[:40]}")
                            item_sent = True
                        else:
                            log.warning(f"الخادم {endpoint} رجّع {resp.status_code}: {resp.text[:100]}")
                except httpx.ConnectError:
                    log.debug(f"⚠️ تعذر الاتصال بـ {endpoint}")
                except Exception as e:
                    log.error(f"خطأ إرسال إلى {endpoint}: {e}")

            if item_sent:
                sent += 1

        return sent

    async def send_recommendation(self, rec: dict) -> str | None:
        """أرسل توصية خبراء واحدة لـ /api/expert-recommendations/import."""
        if not rec:
            return None
        items = [self._format_recommendation(rec)]
        payload = {
            'session_date': rec.get('session_date') or datetime.now().strftime('%Y-%m-%d'),
            'session_type': 'صباحية',
            'expert_name': rec.get('expert_name', 'محلل محلي'),
            'expert_source': rec.get('expert_source', 'news_agent'),
            'recommendations': items,
        }
        headers = {
            'Content-Type': 'application/json',
            'x-agent-key': self.api_key,
            'X-News-Agent-Key': self.api_key,
        }
        for base in self.base_urls:
            import_url = base.rstrip('/') + '/api/expert-recommendations/import'
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(import_url, json=payload, headers=headers)
                    if resp.status_code in (200, 201):
                        data = resp.json()
                        recs = data.get('recommendations') or []
                        if recs:
                            rec_id = recs[0].get('id')
                            log.info(f'  ✓ توصية ({import_url}): {rec.get("stock_symbol")} → {rec_id}')
                            return rec_id
                        errors = data.get('errors') or []
                        log.warning(
                            f'الخادم رفض التوصية ({import_url}): {rec.get("stock_symbol")} — {errors}'
                        )
                        return None
                    log.warning(f'الخادم {import_url} رجّع {resp.status_code}: {resp.text[:120]}')
            except httpx.ConnectError:
                log.debug(f'⚠️ تعذر الاتصال بـ {import_url}')
            except Exception as e:
                log.error(f'خطأ إرسال توصية إلى {import_url}: {e}')
        return None

    def _format_recommendation(self, rec: dict) -> dict:
        """وَفّر توصية لـ API."""
        return {
            'stock_symbol': rec.get('stock_symbol', ''),
            'stock_name_ar': rec.get('stock_name_ar'),
            'action': rec.get('action', 'BUY'),
            'recommendation_type': rec.get('recommendation_type'),
            'entry_price': rec.get('entry_price'),
            'entry_price_from': rec.get('entry_price_from'),
            'entry_price_to': rec.get('entry_price_to'),
            'target_price': rec.get('target_price'),
            'target_price_2': rec.get('target_price_2'),
            'stop_loss': rec.get('stop_loss'),
            'support_level': rec.get('support_level'),
            'resistance_level': rec.get('resistance_level'),
            'technical_analysis': rec.get('technical_analysis'),
            'recommendation_reason': rec.get('recommendation_reason'),
        }

    def _format_for_site(self, news: dict) -> dict:
        """تنسيق الخبر لـ GLMinvestment"""
        raw = news.get('raw_analysis', '{}')
        try:
            analysis = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            analysis = {}

        tickers = news.get('tickers', [])
        if isinstance(tickers, str):
            try:
                tickers = json.loads(tickers)
            except Exception:
                tickers = []

        image_paths = news.get('image_paths', [])
        if isinstance(image_paths, str):
            try:
                image_paths = json.loads(image_paths)
            except Exception:
                image_paths = []

        image_urls = news.get('image_urls', [])
        if isinstance(image_urls, str):
            try:
                image_urls = json.loads(image_urls)
            except Exception:
                image_urls = []

        all_images = list(dict.fromkeys(
            image for image in image_urls + image_paths
            if isinstance(image, str) and image.startswith(('http://', 'https://'))
        ))

        # استخدم الخبر النظيف لو متوفر
        clean_news = analysis.get('news_text', '') or news.get('body', '')[:800]
        relevant_image_idx = analysis.get('relevant_image_index', 0)
        
        # رتب الصور: الصورة المتعلقة بالخبر أولاً
        if all_images and relevant_image_idx < len(all_images):
            relevant_img = all_images[relevant_image_idx]
            other_imgs = [img for i, img in enumerate(all_images) if i != relevant_image_idx]
            all_images = [relevant_img] + other_imgs

        return {
            'title':       news.get('title', '') or clean_news[:80],
            'content':     clean_news,
            'summary_ar':  analysis.get('summary_ar', '') or news.get('summary_ar', ''),
            'summary_en':  analysis.get('summary_en', '') or news.get('summary_en', ''),
            'source':      news.get('source', 'news_agent'),
            'source_type': news.get('source_type', 'telegram'),
            'url':         news.get('url', ''),
            'tickers':     tickers,
            'importance':  news.get('importance', 0),
            'sentiment':   news.get('sentiment', 'neutral'),
            'impact_type': news.get('impact_type', 'general'),
            'market':      'EGX',
            'image_paths': all_images,
            'ocr_text':    news.get('ocr_text', ''),
            'raw_analysis':analysis,
            'published_at':news.get('published_at', ''),
            'is_valid_news': analysis.get('is_valid_news', True),
        }
