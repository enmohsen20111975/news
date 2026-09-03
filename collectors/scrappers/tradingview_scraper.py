#!/usr/bin/env python3
"""
🔥 TradingView Full Scraper - كل الأسواق والتبويبات
"""

import json
import sqlite3
import asyncio
import sys
import os
import subprocess
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

# Get the data directory path - all unified in /db folder
DATA_DIR = Path(__file__).parent.parent.parent / 'db'
# Database path - unified in /db folder
DB_FILE = str(DATA_DIR / 'data_engine.db')

MARKETS = {
    'السعودية': 'https://ar.tradingview.com/markets/stocks-ksa/market-movers-all-stocks/',
    'مصر': 'https://ar.tradingview.com/markets/stocks-egypt/market-movers-all-stocks/',
    'الكويت': 'https://ar.tradingview.com/markets/stocks-kuwait/market-movers-all-stocks/',
    'قطر': 'https://ar.tradingview.com/markets/stocks-qatar/market-movers-all-stocks/'
}

TABS = ['الأداء', 'القيمة', 'أرباح', 'الربحية', 'بيانات الدخل', 'بَيَانُ المُوَازَنَة', 'التدفقات النقدية', 'تحليلات فنية']

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

async def click_load_more(page, market_name):
    prev_rows = -1
    for i in range(50):
        try:
            btn = await page.wait_for_selector('button:has-text("تحميل المزيد"), [data-test="load-more-button"], .load-more-button, button:has-text("Load More")', timeout=3000)
            if not btn:
                break
            await btn.click()
            await page.wait_for_load_state('networkidle', timeout=15000)
            rows = await page.evaluate('''() => document.querySelectorAll('table tbody tr, [data-name="row"], .row-Rf3yeq1F, [class*="row"]').length''')
            if rows == prev_rows:
                break
            prev_rows = rows
            # if i % 10 == 0 and rows > 0:
            #     await page.screenshot(path=str(DATA_DIR / f'debug_{market_name}_{i}.png'), full_page=False)
        except Exception:
            break
    return prev_rows

async def scrape_market(page, market, url):
    log(f"🌍 {market}")

    try:
        await page.goto(url, timeout=90000)
        await page.wait_for_load_state('networkidle', timeout=30000)
        total_rows = await click_load_more(page, market.replace(' ', '_'))
        log(f"  🔄 load-more finished at {total_rows} rows")

        # Get main table - robust selector for TradingView's dynamic DOM
        stocks = await page.evaluate(r'''
            () => {
                const stocks = [];
                const rows = document.querySelectorAll('table tbody tr, [data-name="row"], .row-Rf3yeq1F, [class*="row"]');
                rows.forEach(row => {
                    const cells = row.querySelectorAll('td, [data-name="cell"], .cell');
                    if (cells.length >= 4) {
                        // Robust symbol & name extraction
                        let sym = '';
                        let name = '';
                        const link = cells[0].querySelector('a[href*="/symbols/"]');
                        if (link) {
                            const href = link.getAttribute('href') || '';
                             const m = href.match(/symbols\/[A-Z0-9_]+-([A-Z0-9_]+)/i);

                            if (m) sym = m[1].toUpperCase();
                        }
                        if (!sym) {
                            const raw = cells[0].querySelector('[class*="tickerName"], a')?.textContent?.trim() || '';
                            const m = raw.match(/^[A-Z0-9_]{2,8}|^\d{4,5}/);
                            sym = m ? m[0] : '';
                        }
                        const nameElem = cells[0].querySelector('[class*="tickerDescription"], [class*="description"]');
                        name = nameElem ? nameElem.textContent.trim() : (cells[0].querySelectorAll('a')[1]?.textContent?.trim() || sym);
                        const priceText = cells[1]?.textContent || '0';
                        const price = parseFloat(priceText.match(/[\\d.]+/)?.[0] || 0);
                        const changeText = cells[2]?.textContent || '0';
                        const changeVal = changeText.replace('−', '-').replace('+', '');
                        const change = parseFloat(changeVal.match(/[-+]?[\\d.]+/)?.[0] || 0);
                        if (sym && price > 0) {
                            stocks.push({
                                symbol: sym, name, price,
                                change_percent: change,
                                volume: cells[3]?.textContent?.trim() || '',
                                market_cap: cells[5]?.textContent?.trim() || '',
                                sector: '',
                                tabs_data: {}
                            });
                        }
                    }
                });
                return stocks;
            }
        ''')
        log(f"  📊 {len(stocks)} stocks")

        lookup = {s['symbol']: s for s in stocks}

        # Scrape each tab
        for tab in TABS:
            try:
                btn = await page.wait_for_selector(f'button:has-text("{tab}"), [data-test="{tab}"], [class*="{tab}"]', timeout=5000)
                if not btn:
                    log(f'  ⚠️ {tab}: button not found')
                    continue
                await btn.click()
                await page.wait_for_load_state('networkidle', timeout=10000)
                await click_load_more(page, market.replace(' ', '_'))

                data = await page.evaluate('''
                    () => {
                        const result = {};
                        document.querySelectorAll('table tbody tr, [data-name="row"], .row-Rf3yeq1F, [class*="row"]').forEach((row) => {
                            const cells = row.querySelectorAll('td, [data-name="cell"], .cell');
                            if (cells.length > 0) {
                                const aTags = cells[0].querySelectorAll('a');
                                const sym = aTags[0]?.textContent?.trim() || '';
                                const vals = Array.from(cells).map(c => c.textContent?.trim() || '');
                                if (sym) result[sym] = vals;
                            }
                        });
                        return result;
                    }
                ''')

                matched = sum(1 for s in lookup if s in data)
                for sym in lookup:
                    if sym in data:
                        lookup[sym]['tabs_data'][tab] = data[sym]

                log(f"  📑 {tab}: {matched}/{len(stocks)}")
            except Exception as e:
                log(f"  ⚠️ {tab}: {str(e)[:60]}")

        return stocks

    except Exception as e:
        log(f"  ❌ Error: {str(e)[:60]}")
        try:
            await page.screenshot(path=str(DATA_DIR / 'debug_screenshot.png'), full_page=False)
            log(f'  📸 screenshot saved to debug_screenshot.png')
        except Exception:
            pass
        return []

def save_to_db(stocks, market):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Create tables if not exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stocks (
            symbol TEXT PRIMARY KEY,
            name TEXT,
            price REAL,
            change_percent REAL,
            volume TEXT,
            market_cap TEXT,
            sector TEXT,
            market TEXT,
            tabs_data TEXT,
            last_update TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create tab tables
    tab_tables = [
        ('tab_technical_analysis', 'symbol TEXT PRIMARY KEY, data TEXT'),
        ('tab_profitability', 'symbol TEXT PRIMARY KEY, data TEXT'),
        ('tab_valuation', 'symbol TEXT PRIMARY KEY, data TEXT'),
        ('tab_dividends', 'symbol TEXT PRIMARY KEY, data TEXT'),
        ('tab_performance', 'symbol TEXT PRIMARY KEY, data TEXT'),
        ('tab_balance_sheet', 'symbol TEXT PRIMARY KEY, data TEXT'),
        ('tab_income_statement', 'symbol TEXT PRIMARY KEY, data TEXT'),
        ('tab_cash_flow', 'symbol TEXT PRIMARY KEY, data TEXT')
    ]
    for table_name, cols in tab_tables:
        cursor.execute(f'CREATE TABLE IF NOT EXISTS {table_name} ({cols})')

    for s in stocks:
        cursor.execute('''
            INSERT INTO stocks
            (symbol, name, price, change_percent, volume, market_cap, sector, market, tabs_data, last_update)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                price = excluded.price,
                change_percent = excluded.change_percent,
                volume = excluded.volume,
                market_cap = excluded.market_cap,
                sector = CASE WHEN excluded.sector != '' THEN excluded.sector ELSE stocks.sector END,
                name = CASE WHEN excluded.name != '' AND excluded.name != excluded.symbol THEN excluded.name ELSE stocks.name END,
                name_ar = CASE WHEN excluded.name != '' AND excluded.name GLOB '*[\u0600-\u06ff]*' THEN excluded.name ELSE stocks.name_ar END,
                tabs_data = excluded.tabs_data,
                last_update = excluded.last_update
        ''', (
            s.get('symbol', ''), s.get('name', ''), s.get('price', 0),
            s.get('change_percent', 0), s.get('volume', ''), s.get('market_cap', ''),
            s.get('sector', ''), market,
            json.dumps(s.get('tabs_data', {}), ensure_ascii=False),
            datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ))

    conn.commit()
    conn.close()

async def main():
    log("=" * 50)
    log("🔥 TradingView Full Scraper")
    log(f"📊 Markets: {len(MARKETS)}, Tabs: {len(TABS)}")
    log("=" * 50)

    all_stocks = []

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

        page.on('console', lambda msg: log(f'  🖥️ console: {msg.text}') if 'error' in msg.type.lower() else None)
        page.on('response', lambda resp: log(f'  🚫 blocked: {resp.status} {resp.url}') if resp.status in (403, 429, 503) else None)

        for market, url in MARKETS.items():
            stocks = await scrape_market(page, market, url)
            if stocks:
                save_to_db(stocks, market)
                has_tabs = sum(1 for s in stocks if s.get('tabs_data'))
                log(f"  💾 Saved: {len(stocks)} stocks, {has_tabs} with tabs")
            all_stocks.extend(stocks)
            await asyncio.sleep(1)

        await browser.close()

    # Save JSON
    with open(DATA_DIR / 'stocks_full_data.json', 'w', encoding='utf-8') as f:
        json.dump(all_stocks, f, indent=2, ensure_ascii=False)

    # Summary
    has_tabs = sum(1 for s in all_stocks if s.get('tabs_data'))
    log("=" * 50)
    log(f"🎉 Done! {len(all_stocks)} stocks, {has_tabs} with tabs")
    log("=" * 50)

    # ============================================================
    # STOPSILENT-FAIL (يوليو 2026): لا تسجّل "نجاح" لو الـ scraper رجع فاضي.
    # ------------------------------------------------------------
    # المشكلة: الكود القديم كان بيرجّع exit 0 حتى لو ما جابش أي سهم،
    # فالـ main.py كان بيشوف "نجح" وبيـ skip الـ fallback chain.
    # الحل: لو ما اتسجّلش أي سهم جديد، نخرج بـ exit 1 عشان الـ fallback
    # chain يشتغل (TV فشل → EGXPilot → Yahoo).
    # ============================================================
    if not all_stocks:
        log("🚨 FATAL: TradingView scraper returned 0 stocks!")
        log("🚨 This is NOT a success — fallback chain should kick in.")
        sys.exit(1)

    # Auto-sync to data_engine.db after successful scrape
    # NOTE: sync.py was removed in v1.1 — the scrapers now write directly to
    # db/data_engine.db via save_to_db(). This call is a no-op placeholder
    # preserved for backward compatibility with existing orchestration scripts.
    if all_stocks:
        try:
            sync_path = str(Path(__file__).resolve().parent.parent / 'sync.py')
            if Path(sync_path).exists():
                log("🔄 Auto-syncing to stocks.db...")
                result = subprocess.run(
                    [sys.executable, sync_path],
                    capture_output=True, text=True, timeout=120,
                    cwd=str(Path(__file__).resolve().parent.parent)
                )
                if result.returncode == 0:
                    log("✅ Auto-sync completed")
                else:
                    log(f"⚠️ Auto-sync warning: {result.stderr[:100]}")
            else:
                log("ℹ️ sync.py not found — data already in data_engine.db")
        except Exception as e:
            log(f"⚠️ Auto-sync error: {str(e)[:60]}")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log("⛔ Interrupted by user")
        sys.exit(130)
    except SystemExit:
        raise  # re-raise sys.exit() from main()
    except Exception as _fatal:
        log(f"🚨 FATAL: {_fatal}")
        sys.exit(1)
