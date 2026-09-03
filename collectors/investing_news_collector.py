import asyncio
import json
import sys
import time
from pathlib import Path
from playwright.async_api import async_playwright
from datetime import datetime

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.news_store import NewsStore

sys.stdout.reconfigure(encoding='utf-8')

async def extract_news(page):
    """Extract news from sa.investing.com/news"""
    await page.goto('https://sa.investing.com/news', timeout=90000, wait_until='domcontentloaded')
    await page.wait_for_timeout(5000)
    
    # Scroll to load all content
    await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
    await page.wait_for_timeout(3000)
    await page.evaluate('window.scrollTo(0, 0)')
    await page.wait_for_timeout(2000)
    
    news_data = await page.evaluate('''() => {
        const articles = new Map();
        
        // Try to find article cards/links
        document.querySelectorAll('article, .article, .news-item, [data-test="article"], a[href*="article"]').forEach(el => {
            const title = el.innerText?.trim().split('\\n')[0]?.trim();
            const link = el.href || el.querySelector('a')?.href;
            if (title && title.length > 10 && link) {
                articles.set(link, {title, link});
            }
        });
        
        // Also try to find from generic links
        if (articles.size === 0) {
            document.querySelectorAll('a').forEach(a => {
                const text = a.innerText?.trim();
                const href = a.getAttribute('href') || '';
                if (text && text.length > 20 && (href.includes('/news/') || href.includes('/article/'))) {
                    const fullLink = href.startsWith('http') ? href : 'https://sa.investing.com' + href;
                    articles.set(fullLink, {title: text, link: fullLink});
                }
            });
        }
        
        return Array.from(articles.values());
    }''')
    
    return news_data

async def main():
    store = None
    for attempt in range(3):
        try:
            store = NewsStore()
            break
        except Exception as e:
            print(f'Database connection attempt {attempt+1} failed: {e}')
            time.sleep(2)
    
    if not store:
        print('Failed to connect to database')
        return
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='ar-SA'
        )
        page = await context.new_page()
        
        print('Fetching news from sa.investing.com/news ...')
        news_data = await extract_news(page)
        
        print(f'\nFound {len(news_data)} unique articles')
        
        saved_count = 0
        for article in news_data:
            try:
                news_id = store.add(
                    source='investing.com',
                    source_type='web',
                    body=article['title'],
                    title=article['title'],
                    url=article['link']
                )
                if news_id:
                    saved_count += 1
            except Exception as e:
                print(f'Error saving article: {e}')
                continue
        
        print(f'Saved {saved_count} new articles to database')
        print(f'Total in database: {store.stats()["total"]}')
        print(f'Pending analysis: {store.stats()["pending"]}')
        
        await browser.close()
        store.close()

if __name__ == '__main__':
    asyncio.run(main())
