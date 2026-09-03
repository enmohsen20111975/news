import asyncio
import json
import sys
from playwright.async_api import async_playwright
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

OUTPUT_PATH = 'D:\\My WebStie Applications\\news_agent\\data\\marketmaker_news.json'

async def scrape_page(page, page_num):
    """Scrape a single page of MarketMaker news"""
    url = f'https://marketmakerseg.com/news?page={page_num}'
    print(f'Scraping page {page_num}: {url}', flush=True)
    
    await page.goto(url, timeout=90000, wait_until='domcontentloaded')
    await page.wait_for_timeout(5000)
    
    # Scroll to load all content
    await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
    await page.wait_for_timeout(3000)
    await page.evaluate('window.scrollTo(0, 0)')
    await page.wait_for_timeout(2000)
    
    articles = await page.evaluate('''() => {
        const articles = [];
        const seen = new Set();
        
        // Find all links containing /news/ and numbers
        document.querySelectorAll('a').forEach(a => {
            const text = a.innerText?.trim();
            const href = a.getAttribute('href') || '';
            
            if (text && text.length > 15 && href.includes('/news/')) {
                const match = href.match(/\\/news\\/(\\d+)/);
                if (match && !seen.has(match[1])) {
                    seen.add(match[1]);
                    articles.push({
                        id: match[1],
                        title: text,
                        url: href.startsWith('http') ? href : 'https://marketmakerseg.com' + href
                    });
                }
            }
        });
        
        return articles;
    }''')
    
    return articles

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='ar-SA'
        )
        page = await context.new_page()
        
        all_articles = {}
        
        # Scrape multiple pages
        max_pages = 100  # Safety limit
        for page_num in range(1, max_pages + 1):
            articles = await scrape_page(page, page_num)
            
            if not articles:
                print(f'No articles found on page {page_num}, stopping.', flush=True)
                break
            
            # Add to collection
            for article in articles:
                all_articles[article['id']] = article
            
            print(f'Page {page_num}: found {len(articles)} articles, total unique: {len(all_articles)}', flush=True)
            
            # Check if we should stop (less than 10 articles means likely last page)
            if len(articles) < 10:
                print(f'Less than 10 articles on page {page_num}, assuming last page.', flush=True)
                break
            
            # Small delay between pages
            await page.wait_for_timeout(1500)
        
        # Convert to list and sort by ID descending (newest first)
        final_articles = sorted(all_articles.values(), key=lambda x: int(x['id']), reverse=True)
        
        result = {
            'source': 'marketmakerseg.com',
            'scraped_at': datetime.now().isoformat(),
            'total_articles': len(final_articles),
            'articles': final_articles
        }
        
        with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        print(f'\nSaved {len(final_articles)} articles to {OUTPUT_PATH}', flush=True)
        
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
