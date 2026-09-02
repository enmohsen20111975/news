"""
جامع أخبار من RSS Feeds
"""

import os
import logging
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.sources import registry
from collectors.keyword_filter import filter_instance

log = logging.getLogger('RSSCollector')

DEFAULT_FEEDS = [
    'https://www.mubasher.info/api/news/ar/feed/EG',
    'https://argaam.com/ar/rss',
    'https://www.amwalalghad.com/feed/',
    'https://www.youm7.com/Section/56/RSS',  # اقتصاد
]


class RSSCollector:
    """يجمع أخبار من RSS Feeds"""

    def __init__(self, store):
        self.store = store
        feeds_env = os.getenv('RSS_FEEDS', '')
        self.feeds = [f.strip() for f in feeds_env.split(',') if f.strip()] \
                     or DEFAULT_FEEDS

async def collect(self) -> int:
        total = 0
        for url in self.feeds:
            try:
                count = self._parse_feed(url)
                total += count
            except Exception as e:
                log.warning(f'RSS error {url}: {e}')
        return total

    def _parse_feed(self, url: str) -> int:
        import feedparser
        import asyncio
        saved = 0
        try:
            feed = feedparser.parse(url)
            display_name = registry.get_rss_display(url, fallback_title=feed.feed.get('title', url))

            for entry in feed.entries[:15]:
                body = entry.get('summary', '') or entry.get('description', '')
                title = entry.get('title', '')
                if len(body) < 30:
                    continue

                # فلترة المحتوى
                if not filter_instance.quick_match(f'{title}\n{body}'):
                    log.debug(f'RSS رفض: {title[:60]}')
                    continue

                published = entry.get('published', datetime.now().isoformat())

                news_id = self.store.add(
                    source=display_name,
                    source_type='rss',
                    body=body,
                    title=title,
                    url=entry.get('link', ''),
                    published_at=str(published),
                )
                if news_id:
                    saved += 1
        except Exception as e:
            log.debug(f'RSS parse error {url}: {e}')
        return saved
