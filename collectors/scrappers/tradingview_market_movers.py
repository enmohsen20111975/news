#!/usr/bin/env python3
"""
🔥 TradingView Market Movers - 9 Tabs Scraper
================================================

يسحب بيانات الأسهم من صفحة Market Movers (gainers / losers / active) على
TradingView مع كل 9 تبويبات (column sets):

1. نظرة عامة          (overview)        — البيانات الأساسية: السعر، التغيير، الحجم، القيمة السوقية
2. الأداء             (performance)     — مؤشرات الأداء (YTD، 1Y، 3Y، 5Y، ...)
3. تحليلات فنية        (technicals)      — مؤشرات فنية (RSI، MACD، Bollinger، ...)
4. القيمة             (valuation)       — مضاربات القيمة (P/E، P/B، EV/EBITDA، ...)
5. توزيعات الأرباح    (dividends)       — بيانات الأرباح (Yield، Payout، Dividend Rank، ...)
6. الربحية            (profitability)   — هوامش الربح (Gross، EBIT، Net Margin، ROE، ROA، ...)
7. بيانات الدخل       (incomeStatement) — بيان الدخل (Revenue، EBIT، Net Income، EPS، ...)
8. بَيَانُ المُوَازَنَة (balanceSheet)   — الميزانية (Assets، Liabilities، Equity، Debt Ratios، ...)
9. التدفقات النقدية   (cashFlow)        — التدفقات النقدية (Operating CF، Investing CF، Financing CF، FCF، ...)

البيانات بتتخزن في:
  - data_engine.db  جدول `market_movers_tabs`
  - JSON snapshot   db/market_movers_tabs.json

@author M2y Platform
@version 1.0 — سبتمبر 2026
"""

import json
import sqlite3
import asyncio
import re
import sys
import codecs
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

# Force UTF-8 stdout for Arabic/emoji output on Windows
if hasattr(sys.stdout, 'encoding') and sys.stdout.encoding != 'utf-8':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)

DATA_DIR = Path(__file__).parent.parent.parent / 'db'
DB_FILE = str(DATA_DIR / 'data_engine.db')
JSON_FILE = DATA_DIR / 'market_movers_tabs.json'

# الـ URLs المدعومة — صفحات Market Movers على البورصة المصرية (كلها فيها 9 تبويبات)
URLS = [
    "https://ar.tradingview.com/markets/stocks-egypt/market-movers-gainers/",
    "https://ar.tradingview.com/markets/stocks-egypt/market-movers-losers/",
    "https://ar.tradingview.com/markets/stocks-egypt/market-movers-active/",
    "https://ar.tradingview.com/markets/stocks-egypt/market-movers-unusual-volume/",
    "https://ar.tradingview.com/markets/stocks-egypt/market-movers-high-dividend/",
]

# الـ 9 تبويبات اللي المستخدم طلبها (data-qa-id)
TABS = [
    {'qa_id': 'overview',         'label': 'نظرة عامة',               'ar': 'نظرة عامة'},
    {'qa_id': 'performance',      'label': 'الأداء',                   'ar': 'الأداء'},
    {'qa_id': 'technicals',       'label': 'تحليلات فنية',             'ar': 'تحليلات فنية'},
    {'qa_id': 'valuation',        'label': 'القيمة',                   'ar': 'القيمة'},
    {'qa_id': 'dividends',        'label': 'توزيعات الأرباح',          'ar': 'توزيعات الأرباح'},
    {'qa_id': 'profitability',    'label': 'الربحية',                 'ar': 'الربحية'},
    {'qa_id': 'incomeStatement',  'label': 'بيانات الدخل',            'ar': 'بيانات الدخل'},
    {'qa_id': 'balanceSheet',     'label': 'بَيَانُ المُوَازَنَة',    'ar': 'بَيَانُ المُوَازَنَة'},
    {'qa_id': 'cashFlow',         'label': 'التدفقات النقدية',        'ar': 'التدفقات النقدية'},
]

MAX_ROWS = 150

# Regex patterns (defined as raw strings to avoid escape warnings)
_RE_SYMBOL_HREF = re.compile(r'/symbols/[A-Z0-9_]+-([A-Z0-9_.]+)', re.IGNORECASE)
_RE_SYMBOL_RAW = re.compile(r'^[A-Z0-9_.]{2,12}')


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


async def click_load_more(page):
    """اضغط 'تحميل المزيد' لحد ما يخلص أو نوصل الحد الأقصى."""
    prev_rows = -1
    for i in range(25):
        try:
            btn = await page.wait_for_selector(
                'button:has-text("تحميل المزيد"), [data-test="load-more-button"], button:has-text("Load More")',
                timeout=2500,
            )
            if not btn:
                break
            await btn.click()
            await asyncio.sleep(0.8)
            rows = await page.evaluate(
                '() => document.querySelectorAll("table tbody tr").length'
            )
            if rows >= MAX_ROWS or rows == prev_rows:
                break
            prev_rows = rows
        except Exception:
            break


# JavaScript for extracting headers and row data — uses raw string to avoid escape warnings
_EXTRACT_HEADERS_JS = r'''
    () => {
        const headers = [];
        // Find the data table (second table without sticky class)
        const tables = document.querySelectorAll('table.table-NI7L99jP');
        let table = null;
        tables.forEach(t => {
            const sticky = t.classList.contains('tableSticky-RWJTYtFF');
            const rows = t.querySelectorAll('tbody tr').length;
            if (!sticky && rows > 0) table = t;
        });
        if (!table) {
            // Fallback: find any table with body rows
            tables.forEach(t => {
                if (!table && t.querySelectorAll('tbody tr').length > 0) table = t;
            });
        }
        if (table) {
            const ths = table.querySelectorAll('thead th');
            ths.forEach(th => {
                const text = th.textContent?.trim() || '';
                const field = th.getAttribute('data-field') || '';
                headers.push({ text, field });
            });
        }
        return headers;
    }
'''

_EXTRACT_ROWS_JS = r'''
    (MAX_ROWS) => {
        const out = [];
        const tables = document.querySelectorAll('table.table-NI7L99jP');
        let table = null;
        tables.forEach(t => {
            const sticky = t.classList.contains('tableSticky-RWJTYtFF');
            const rows = t.querySelectorAll('tbody tr').length;
            if (!sticky && rows > 0) table = t;
        });
        if (!table) {
            tables.forEach(t => {
                if (!table && t.querySelectorAll('tbody tr').length > 0) table = t;
            });
        }
        if (!table) return out;

        const rows = table.querySelectorAll('tbody tr');
        for (let i = 0; i < Math.min(rows.length, MAX_ROWS); i++) {
            const row = rows[i];
            const cells = row.querySelectorAll('td');
            if (cells.length === 0) continue;

            // Extract symbol from data-rowkey attribute
            let sym = '';
            const rowkey = row.getAttribute('data-rowkey');
            if (rowkey) {
                const parts = rowkey.split(':');
                sym = parts[parts.length - 1].toUpperCase();
            }
            // Fallback: extract from href in first cell
            if (!sym) {
                const link = cells[0].querySelector('a[href*="/symbols/"]');
                if (link) {
                    const href = link.getAttribute('href') || '';
                    const m = href.match(/symbols\/[A-Z0-9_]+-([A-Z0-9_.]+)/i);
                    if (m) sym = m[1].toUpperCase();
                }
            }
            // Fallback: text content
            if (!sym) {
                const raw = cells[0].textContent?.trim() || '';
                const m = raw.match(/^[A-Z0-9_.]{2,12}/);
                if (m) sym = m[0].toUpperCase();
            }
            if (!sym) continue;

            // Extract name from the ticker description link
            let name = '';
            const nameLink = cells[0].querySelector('a.tickerDescription-WjYk5eOQ, a.apply-overflow-tooltip');
            if (nameLink) name = nameLink.textContent?.trim() || '';
            if (!name) {
                const links = cells[0].querySelectorAll('a');
                if (links.length > 1) name = links[1].textContent?.trim() || '';
            }

            // Extract all cell values — for the first cell, combine ticker + name cleanly
            const values = Array.from(cells).map((c, idx) => {
                if (idx === 0) {
                    // First cell contains ticker symbol + company name + markers
                    // Combine just the ticker link text and description link text
                    const symLink = c.querySelector('a.tickerName-t7nCkzMw, a.tickerNameBox');
                    const descLink = c.querySelector('a.tickerDescription-WjYk5eOQ, a.apply-overflow-tooltip');
                    let parts = [];
                    if (symLink) {
                        const t = symLink.textContent?.trim();
                        if (t) parts.push(t);
                    }
                    if (descLink) {
                        const t = descLink.textContent?.trim();
                        if (t) parts.push(t);
                    }
                    return parts.join(' — ') || c.textContent?.trim() || '';
                }
                return c.textContent?.trim() || '';
            });

            out.push({ symbol: sym, name, values });
        }
        return out;
    }
'''


async def get_column_headers(page):
    """Extract column headers from the active data table."""
    return await page.evaluate(_EXTRACT_HEADERS_JS)


async def get_table_data(page):
    """Extract all rows from the active data table."""
    return await page.evaluate(_EXTRACT_ROWS_JS, MAX_ROWS)


async def scrape_tab(page, tab_qa_id, tab_label):
    """Click a tab, wait for data, and extract table data."""
    try:
        tab_btn = await page.wait_for_selector(
            f'[data-qa-id="{tab_qa_id}"]',
            timeout=10000,
        )
        if not tab_btn:
            log(f'  ⚠️ {tab_label}: زر التبويب غير موجود')
            return {
                'tab': tab_label,
                'tab_qa_id': tab_qa_id,
                'headers': [],
                'rows': [],
            }

        # Check if this tab is already selected
        is_selected = await tab_btn.get_attribute('aria-selected')
        if is_selected != 'true':
            await tab_btn.click()
            await asyncio.sleep(2)
            await page.wait_for_load_state('networkidle', timeout=15000)

        await click_load_more(page)
        await asyncio.sleep(1)

        headers = await get_column_headers(page)
        rows = await get_table_data(page)

        header_texts = [h['text'] for h in headers] if headers else []
        log(f"  📑 {tab_label}: {len(rows)} صفوف، {len(header_texts)} أعمدة")
        return {
            'tab': tab_label,
            'tab_qa_id': tab_qa_id,
            'headers': header_texts,
            'headers_with_fields': headers,
            'rows': rows,
        }
    except Exception as e:
        log(f"  ⚠️ {tab_label}: {str(e)[:80]}")
        return {
            'tab': tab_label,
            'tab_qa_id': tab_qa_id,
            'headers': [],
            'rows': [],
            'error': str(e)[:100],
        }


async def scrape_page(url, max_retries=2):
    """Scrape all 9 tabs from a single market movers page."""
    market_type = url.split('/')[-2].replace('market-movers-', '')
    log(f"🌐 {market_type}: {url}")

    data = {
        'source': 'tradingview_market_movers',
        'url': url,
        'market_type': market_type,
        'market': 'مصر',
        'scraped_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'tabs': [],
    }

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
                )
                context = await browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
                )
                page = await context.new_page()
                page.on('console', lambda msg: None)

                try:
                    await page.goto(url, timeout=90000)
                    await page.wait_for_load_state('networkidle', timeout=30000)
                    await asyncio.sleep(3)

                    # Verify the tabs container exists before proceeding
                    tabs_container = await page.query_selector('#market-screener-header-columnset-tabs')
                    if not tabs_container:
                        raise Exception("Tabs container not found — page may be rate-limited or blocked")

                    # Click "نظرة عامة" first (it's selected by default, but ensure)
                    overview_btn = await page.wait_for_selector('[data-qa-id="overview"]', timeout=10000)
                    if overview_btn:
                        is_sel = await overview_btn.get_attribute('aria-selected')
                        if is_sel != 'true':
                            await overview_btn.click()
                            await asyncio.sleep(2)

                    # Scrape each of the 9 tabs
                    for tab in TABS:
                        tab_data = await scrape_tab(page, tab['qa_id'], tab['label'])
                        data['tabs'].append(tab_data)

                    await browser.close()
                    return data

                except Exception as e:
                    last_error = e
                    await browser.close()
                    if attempt < max_retries:
                        log(f"  ⏳ Retry {attempt + 1}/{max_retries} for {market_type}...")
                        await asyncio.sleep(3)

        except Exception as e:
            last_error = e
            if attempt < max_retries:
                log(f"  ⏳ Retry {attempt + 1}/{max_retries} for {market_type}...")
                await asyncio.sleep(3)

    log(f"  ❌ Page error: {str(last_error)[:80]}")
    data['error'] = str(last_error)[:200]
    return data


def save_to_db(all_data):
    """Save all tab data to SQLite."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE, timeout=30.0)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS market_movers_tabs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market_type TEXT,
            tab_name TEXT,
            tab_qa_id TEXT,
            symbol TEXT,
            name TEXT,
            column_headers TEXT,
            cell_values TEXT,
            scraped_at TEXT,
            UNIQUE(market_type, tab_qa_id, symbol)
        )
    ''')
    cursor.execute('DELETE FROM market_movers_tabs')

    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    count = 0
    for page_data in all_data:
        market_type = page_data.get('market_type', 'unknown')
        for tab_data in page_data.get('tabs', []):
            tab_name = tab_data.get('tab', '')
            tab_qa_id = tab_data.get('tab_qa_id', '')
            headers = json.dumps(tab_data.get('headers', []), ensure_ascii=False)
            for row in tab_data.get('rows', []):
                cursor.execute('''
                    INSERT OR REPLACE INTO market_movers_tabs
                    (market_type, tab_name, tab_qa_id, symbol, name, column_headers, cell_values, scraped_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    market_type, tab_name, tab_qa_id,
                    row.get('symbol', ''), row.get('name', ''),
                    headers, json.dumps(row.get('values', []), ensure_ascii=False),
                    ts
                ))
                count += 1

    conn.commit()
    conn.close()
    log(f"💾 {count} صفوف محفوظة في data_engine.db")


def save_json(all_data):
    """Save all tab data to JSON."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(JSON_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)
    log(f"📄 JSON محفوظ: {JSON_FILE}")


async def main():
    log("=" * 60)
    log("🔥 TradingView Market Movers — 9 Tabs Scraper")
    log(f"📊 Pages: {len(URLS)}, Tabs per page: {len(TABS)}")
    log("=" * 60)

    all_data = []
    for url in URLS:
        try:
            page_data = await scrape_page(url)
            all_data.append(page_data)
            await asyncio.sleep(1)
        except Exception as e:
            log(f"  ❌ Failed {url}: {str(e)[:80]}")

    save_to_db(all_data)
    save_json(all_data)

    total_rows = sum(
        len(t.get('rows', []))
        for pd in all_data
        for t in pd.get('tabs', [])
    )
    log("=" * 60)
    log(f"✅ Done! {total_rows} إجمالي صفوف من {len(URLS)} صفحات × {len(TABS)} تبويبات")
    log("=" * 60)

    if total_rows == 0:
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
