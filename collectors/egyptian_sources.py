"""
جامع أخبار من مواقع مصرية متخصصة في البورصة والأسهم
=======================================================
مصادر مدعومة حالياً:
- Alborsaa News (جريدة البورصة): alborsaanews.com — قسم «البورصة والشركات»
- (مُعطّل) Mubasher Markets — محمي بـ Cloudflare
- (مُعطّل) Argaam — robots.txt يمنع البوتات العامة
- (مُعطّل) EGX الرسمي (egx.com.eg) — خلف WAF يتطلب browser session
- (مُعطّل) Beta EGX — Request Rejected

القواعد (CONSTITUTION.md):
- صور حقيقية فقط من og:image / twitter:image / أول <img>
- لا صور مولدة
- rate-limit بين المصادر (3 ثواني افتراضياً)
- User-Agent معروف
- robots.txt محترم (المصادر المفعّلة كلها robots.txt مسموح)

التشغيل:
- متوقف افتراضياً. للتفعيل ضع في .env:
  ENABLE_EGYPTIAN_SOURCES=1
- يمكن تعطيل مصادر فردية:
  ALBORSAA_ENABLED=1   # افتراضي
"""

import os
import re
import json
import time
import logging
import asyncio
from abc import ABC, abstractmethod
from datetime import datetime
from urllib.parse import urljoin, quote
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.sources import registry
from collectors.keyword_filter import filter_instance

import requests
from bs4 import BeautifulSoup

log = logging.getLogger('EgyptianSources')

USER_AGENT = (
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
)
DEFAULT_DELAY_SECONDS = 3.0
REQUEST_TIMEOUT = 20


class EgyptianSource(ABC):
    """واجهة موحدة لأي مصدر مصري"""

    name: str = 'source'
    enabled_env: str = 'SOURCE_ENABLED'

    def __init__(self, store):
        self.store = store
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ar,en;q=0.9',
        })

    @abstractmethod
    def fetch_articles(self, limit: int = 15) -> list[dict]:
        """يرجع list من dicts فيها:
        {title, body, url, image_urls: list[str], source, published_at}
        """

    def is_enabled(self) -> bool:
        return os.getenv(self.enabled_env, '1').lower() in ('1', 'true', 'yes')

    async def collect(self) -> int:
        if not self.is_enabled():
            log.debug(f'{self.name}: معطّل عبر {self.enabled_env}')
            return 0
        try:
            articles = await asyncio.get_event_loop().run_in_executor(
                None, self.fetch_articles
            )
        except Exception as e:
            log.warning(f'{self.name}: خطأ في الجلب — {e}')
            return 0

        saved = 0
        for article in articles:
            title = article.get('title', '')
            body = article.get('body', '')
            ok, reason = await filter_instance.is_relevant(body, title=title)
            if not ok:
                log.debug(f'{self.name} رفض: {title[:60]} ({reason})')
                continue
            try:
                nid = self.store.add(
                    source=article['source'],
                    source_type='web',
                    body=body,
                    title=title,
                    url=article['url'],
                    published_at=article.get('published_at', ''),
                    image_urls=json.dumps(
                        article.get('image_urls', []), ensure_ascii=False
                    ),
                )
                if nid:
                    saved += 1
            except Exception as e:
                log.warning(f'{self.name}: خطأ تخزين — {e}')
        if saved:
            log.info(f'{self.name}: تم حفظ {saved} خبر جديد من {len(articles)} مرشّح')
        return saved


class AlborsaaSource(EgyptianSource):
    """جريدة البورصة — alborsaanews.com"""

    name = 'alborsaanews'
    enabled_env = 'ALBORSAA_ENABLED'

    CATEGORIES = [
        ('البورصة-والشركات', 'البورصة والشركات'),
        ('أسواق', 'أسواق'),
    ]

    def fetch_articles(self, limit: int = 15) -> list[dict]:
        delay = float(os.getenv('EGYPTIAN_DELAY_SECONDS', DEFAULT_DELAY_SECONDS))
        articles: list[dict] = []
        seen_urls: set[str] = set()

        for slug, label in self.CATEGORIES:
            if len(articles) >= limit:
                break
            url = f'https://www.alborsaanews.com/category/{quote(slug)}'
            try:
                resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
            except Exception as e:
                log.warning(f'Alborsaa[{label}]: network error — {e}')
                continue
            if resp.status_code != 200:
                log.warning(f'Alborsaa[{label}]: HTTP {resp.status_code}')
                continue

            page_articles = self._parse_category_page(
                resp.text, source_label=label, limit=limit - len(articles)
            )
            for art in page_articles:
                if art['url'] not in seen_urls:
                    seen_urls.add(art['url'])
                    articles.append(art)

            time.sleep(delay)

        return articles[:limit]

    def _parse_category_page(self, html: str, source_label: str, limit: int) -> list[dict]:
        soup = BeautifulSoup(html, 'html.parser')
        articles: list[dict] = []
        for art_tag in soup.find_all('article'):
            if len(articles) >= limit:
                break
            article = self._parse_article_tag(art_tag, source_label)
            if article:
                articles.append(article)
        return articles

    def _parse_article_tag(self, tag, source_label: str) -> dict | None:
        link = tag.find('a', href=True)
        if not link:
            return None
        url = link['href']
        if 'alborsaanews.com' not in url:
            return None

        title_tag = tag.find(['h2', 'h3'])
        title = title_tag.get_text(strip=True) if title_tag else link.get_text(strip=True)
        title = self._clean_html_entities(title)
        if len(title) < 15:
            return None

        image_urls: list[str] = self._extract_image_urls(tag)

        return {
            'title': title,
            'body': title,
            'url': url,
            'image_urls': image_urls[:2],
            'source': registry.get_web_display('web_alborsaa', 'جريدة البورصة'),
            'published_at': '',
        }

    @staticmethod
    def _extract_image_urls(tag) -> list[str]:
        """يستخرج الصور من <img src>, <img data-src>, و <div data-src> (lazy load)"""
        urls: list[str] = []

        # 1) <img> tag — الأولوية لـ data-src (الصورة الحقيقية في lazy loading)
        for img in tag.find_all('img'):
            for attr in ('data-src', 'data-lazy-src', 'src'):
                src = img.get(attr)
                if src and src.startswith('http') and 'data:image' not in src:
                    if src not in urls:
                        urls.append(src)
                    break

        # 2) <div data-src> — يستخدمه JNews theme في الـ hero items
        for div in tag.find_all('div'):
            src = div.get('data-src')
            if src and src.startswith('http') and 'data:image' not in src:
                if src not in urls:
                    urls.append(src)

        return urls[:2]

    @staticmethod
    def _clean_html_entities(text: str) -> str:
        if not text:
            return ''
        return (text
                .replace('&#8220;', '«').replace('&#8221;', '»')
                .replace('&quot;', '"').replace('&amp;', '&')
                .replace('&#8217;', '’').replace('&#8216;', '‘')
                .strip())


class EgyptianSourcesCollector:
    """يدير كل المصادر المصرية المتخصصة"""

    name = 'egyptian_sources'

    def __init__(self, store):
        self.store = store
        self.sources: list[EgyptianSource] = [
            AlborsaaSource(store),
        ]

    def is_enabled(self) -> bool:
        return os.getenv('ENABLE_EGYPTIAN_SOURCES', '0').lower() in ('1', 'true', 'yes')

    async def collect(self) -> int:
        if not self.is_enabled():
            return 0
        log.info('بدء جمع الأخبار من المصادر المصرية المتخصصة...')
        total = 0
        for source in self.sources:
            try:
                count = await source.collect()
                total += count
            except Exception as e:
                log.warning(f'{source.name}: خطأ غير متوقع — {e}')
        if total == 0:
            log.info('لم يُجمع أي خبر جديد من المصادر المصرية')
        return total