"""
جامع أخبار من الويب
- يستورد من GLMinvestment مباشرة
- يستخرج صور المقالات
- مكافحة تكرار تلقائية
"""

import os
import json
import logging
import asyncio
import importlib.util
from datetime import datetime
from pathlib import Path

log = logging.getLogger('WebScraper')

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GLM_VPS = os.getenv('GLMINVESTMENT_PATH', str(PROJECT_ROOT.parent / 'GLMinvestment' / 'vps-service'))

_GLM_AVAILABLE = False
EGX_TICKER_NAMES = {}
_fetch_news_for_ticker = None
_fetch_egx_market_news = None

try:
    nfa_path = Path(GLM_VPS) / "analyzers" / "news_fetcher_analyzer.py"
    spec = importlib.util.spec_from_file_location("news_fetcher_analyzer", nfa_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    EGX_TICKER_NAMES = mod.EGX_TICKER_NAMES
    _fetch_news_for_ticker = mod.fetch_news_for_ticker
    _fetch_egx_market_news = mod.fetch_egx_market_news
    _GLM_AVAILABLE = True
except Exception:
    pass


class WebScraper:
    """يبحث عن أخبار البورصة على الإنترنت"""

    def __init__(self, store):
        self.store = store

    async def collect(self) -> int:
        """جمع أخبار من DuckDuckGo عبر GLMinvestment analyzer"""
        if not _GLM_AVAILABLE:
            log.warning("GLMinvestment news_fetcher غير متاح")
            return 0

        total = 0
        loop = asyncio.get_event_loop()

        try:
            count = await loop.run_in_executor(None, self._fetch_market_news)
            total += count
        except Exception as e:
            log.warning(f"خطأ في جلب أخبار السوق: {e}")

        try:
            top_tickers = list(EGX_TICKER_NAMES.keys())[:5]
            for ticker in top_tickers:
                try:
                    count = await loop.run_in_executor(None, self._fetch_ticker_news, ticker)
                    total += count
                except Exception as e:
                    log.debug(f"خطأ جلب أخبار {ticker}: {e}")
        except Exception as e:
            log.warning(f"خطأ في جلب أخبار الأسهم: {e}")

        return total

    def _fetch_market_news(self) -> int:
        """جلب أخبار السوق المصري مع الصور"""
        saved = 0
        try:
            articles = _fetch_egx_market_news(max_results=10)
            for article in articles:
                image_urls = self._extract_image_urls(article.get('url', ''))
                news_id = self.store.add(
                    source=article.get('source', 'DuckDuckGo'),
                    source_type='web',
                    body=article.get('snippet', '') or article.get('title', ''),
                    title=article.get('title', ''),
                    url=article.get('url', ''),
                    published_at=article.get('published_at', ''),
                    image_urls=json.dumps(image_urls, ensure_ascii=False),
                )
                if news_id:
                    saved += 1
        except Exception as e:
            log.debug(f"DuckDuckGo market news error: {e}")
        return saved

    def _fetch_ticker_news(self, ticker: str) -> int:
        """جلب أخبار سهم معين مع الصور"""
        saved = 0
        try:
            articles = _fetch_news_for_ticker(ticker, max_results=3)
            for article in articles:
                image_urls = self._extract_image_urls(article.get('url', ''))
                news_id = self.store.add(
                    source=article.get('source', 'DuckDuckGo'),
                    source_type='web',
                    body=article.get('snippet', '') or article.get('title', ''),
                    title=article.get('title', ''),
                    url=article.get('url', ''),
                    published_at=article.get('published_at', ''),
                    image_urls=json.dumps(image_urls, ensure_ascii=False),
                )
                if news_id:
                    saved += 1
        except Exception as e:
            log.debug(f"DuckDuckGo ticker news error for {ticker}: {e}")
        return saved

    def _extract_image_urls(self, url: str) -> list[str]:
        """استخراج صور من المقال (og:image + أول صورة في HTML)"""
        if not url or not url.startswith('http'):
            return []
        try:
            import requests
            from bs4 import BeautifulSoup
            from urllib.parse import unquote, urlparse, parse_qs
            
            # Extract actual URL from DuckDuckGo redirect
            actual_url = url
            if 'duckduckgo.com/l/' in url:
                parsed = urlparse(url)
                params = parse_qs(parsed.query)
                if 'uddg' in params:
                    actual_url = unquote(params['uddg'][0])
            
            resp = requests.get(actual_url, timeout=12, headers={
                'User-Agent': 'Mozilla/5.0 (compatible; NewsBot/1.0)'
            })
            if resp.status_code != 200:
                return []
            soup = BeautifulSoup(resp.text, 'html.parser')
            images = []
            og = soup.find('meta', property='og:image')
            if og and og.get('content'):
                images.append(og['content'])
            twitter = soup.find('meta', attrs={'name': 'twitter:image'})
            if twitter and twitter.get('content'):
                images.append(twitter['image'])
            if not images:
                img = soup.find('img')
                if img and img.get('src'):
                    images.append(img['src'])
            return images[:3]
        except Exception:
            return []
