import asyncio
import json
import sys
from pathlib import Path
from playwright.async_api import async_playwright
from datetime import datetime, time

sys.stdout.reconfigure(encoding='utf-8')

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = _PROJECT_ROOT / 'data'

def is_trading_hours():
    now = datetime.now()
    weekday = now.weekday()
    current_time = now.time()
    start = time(10, 0)
    end = time(15, 0)
    if weekday in [4, 5]:
        return False
    return start <= current_time <= end

async def extract_table_data(page, table_selector):
    return await page.evaluate(f"""() => {{
        const table = document.querySelector('{table_selector}');
        if (!table) return [];
        const rows = Array.from(table.querySelectorAll('tr'));
        const data = [];
        rows.forEach(row => {{
            const cells = Array.from(row.querySelectorAll('td, th'));
            if (cells.length === 0) return;
            const rowData = cells.map(cell => cell.innerText.trim());
            data.push(rowData);
        }});
        return data;
    }}""")

async def main():
    if not is_trading_hours():
        print('خارج ساعات التداول')
        return
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='ar-SA'
        )
        page = await context.new_page()
        
        print('Navigating to sa.investing.com/markets/egypt ...')
        try:
            await page.goto('https://sa.investing.com/markets/egypt', timeout=90000, wait_until='domcontentloaded')
        except Exception as e:
            print(f'Navigation warning: {e}')
        
        await page.wait_for_timeout(5000)
        await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        await page.wait_for_timeout(2000)
        await page.evaluate('window.scrollTo(0, 0)')
        await page.wait_for_timeout(2000)
        
        # Extract sector table
        all_tables = await page.query_selector_all('table')
        sector_data = None
        for tbl in all_tables:
            rows = await tbl.evaluate('''(table) => {
                const rows = Array.from(table.querySelectorAll('tr'));
                const data = [];
                rows.forEach(row => {
                    const cells = Array.from(row.querySelectorAll('td, th'));
                    if (cells.length === 0) return;
                    const rowData = cells.map(cell => cell.innerText.trim());
                    data.push(rowData);
                });
                return data;
            }''')
            if rows and len(rows) > 2:
                first_row_text = ' '.join(rows[0]).lower()
                if 'مواد البناء' in first_row_text or 'قطاع' in first_row_text or 'خدمات' in first_row_text:
                    sector_data = rows
                    break
        
        # Extract commodities
        commodities = await page.evaluate('''() => {
            const results = [];
            const rows = document.querySelectorAll('tr');
            rows.forEach(row => {
                const cells = Array.from(row.querySelectorAll('td'));
                if (cells.length >= 4) {
                    const text = cells.map(c => c.innerText.trim()).join(' | ');
                    if (/ذهب|فضة|نفط|WTI|برنت|نحاس|ألومنيوم|غاز/.test(text)) {
                        results.push(text);
                    }
                }
            });
            return results;
        }''')
        
        # Try to click currencies tab
        currencies = []
        try:
            currency_tab = await page.query_selector('text=عملات')
            if currency_tab:
                await currency_tab.click()
                await page.wait_for_timeout(3000)
                
                currencies = await page.evaluate('''() => {
                    const results = [];
                    const rows = document.querySelectorAll('tr');
                    rows.forEach(row => {
                        const cells = Array.from(row.querySelectorAll('td'));
                        if (cells.length >= 4) {
                            const text = cells.map(c => c.innerText.trim()).join(' | ');
                            if (/دولار|يورو|جنيه|ريال|ليرة|شيكل/.test(text)) {
                                results.push(text);
                            }
                        }
                    });
                    return results;
                }''')
        except Exception as e:
            print(f'Currency tab error: {e}')
        
        result = {
            'timestamp': datetime.now().isoformat(),
            'sectors': sector_data,
            'commodities': commodities,
            'currencies': currencies
        }
        
        output_path = DATA_DIR / 'investing_egypt.json'
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        print(f'\nSaved to {output_path}')
        print(f'Sectors: {len(sector_data) if sector_data else 0} rows')
        print(f'Commodities: {len(commodities)} items')
        print(f'Currencies: {len(currencies)} items')
        
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
