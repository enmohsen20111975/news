#!/usr/bin/env python3
"""
🔥 TradingView Screener Lists Scraper - القوائم المتخصصة
=======================================================

يسحب القوائم الذكية من TradingView بعد الجلسة (مرة واحدة يومياً):
  - most_active       (الأكثر نشاطاً)        → سيولة المؤسسات = بوابة المضارب
  - unusual_volume    (زخم غير اعتيادي)       → نمط تجميع خفي / انفجار صاعد
  - high_dividend     (أعلى عائد توزيعات)     → أمان المستثمر طويل الأجل
  - high_net_income   (أعلى صافي دخل)         → ربحية تشغيلية حقيقية
  - undervalued       (أقل من قيمته العادلة)  → صمام أمان المستثمر القيمي
  - top_losers        (الأكثر خسارة)          → صيد قيعان / ارتداد محتمل
  - penny             (أسهم رخيصة/قرشية)      → فخ: EXCLUDED في المحرك
  - top_gainers       (الأكثر ارتفاعاً)       → فخ: FOMO / تشبع شرائي

كل قائمة namespaced لكل سوق (مصر/السعودية/الكويت/قطر) لأن TradingView
مفيش فيها قائمة عربية موحّدة — كل سوق له صفحته المستقلة.

البيانات بتتخزّن في data_engine.db جدول `screener_lists` مع عمود `category`
و `market` و `rank` (الترتيب جوه القائمة) عشان المحرك يحللها.
"""

import json
import re
import sqlite3
import asyncio
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

DATA_DIR = Path(__file__).parent.parent.parent / 'db'
DB_FILE = str(DATA_DIR / 'data_engine.db')

# الأسواق الأربعة + slug بتاعها في URL بتاع TradingView
MARKETS = {
    'مصر': 'egypt',
    'السعودية': 'ksa',
    'الكويت': 'kuwait',
    'قطر': 'qatar',
}

# القوائم المتخصصة: (category_key, slug في URL, وصف عربي, نوع القائمة)
# list_type: 'gold' = فرصة حقيقية | 'trap' = فخ يُستبعد | 'reversal' = ارتداد | 'value' = قيمة
SCREENER_LISTS = [
    ('most_active',    'active',         'الأكثر نشاطاً',            'gold'),
    ('unusual_volume', 'unusual-volume', 'زخم غير اعتيادي',          'gold'),
    ('high_dividend',  'high-dividend',  'أعلى عائد توزيعات',        'gold'),
    ('high_net_income','high-net-income','أعلى صافي دخل',            'gold'),
    ('undervalued',    'undervalued',    'أقل من القيمة العادلة',    'value'),
    ('top_losers',     'losers',         'الأكثر خسارة',             'reversal'),
    ('penny',          'penny',          'أسهم رخيصة (قرشية)',       'trap'),
    ('top_gainers',    'gainers',        'الأكثر ارتفاعاً',          'trap'),
]


# عدد الأسهم الأقصى اللي بنسحبه من كل قائمة (القوائم دي طويلة جداً)
MAX_ROWS_PER_LIST = 100

_SYMBOL_RE = re.compile(r'^[A-Z0-9][A-Z0-9.\-]{1,14}$')
_ARABIC_RE = re.compile(r'[\u0600-\u06FF]')


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def normalize_symbol(raw_symbol, raw_name):
    """فصل الرمز (latin ticker) عن الاسم (عربي/محلي) بشكل آمن."""
    sym = (raw_symbol or '').strip()
    name = (raw_name or '').strip()

    if _ARABIC_RE.search(sym) and not _ARABIC_RE.search(name):
        sym, name = name, sym

    if ':' in sym:
        sym = sym.split(':')[-1].strip()

    sym = sym.upper()

    if not _SYMBOL_RE.match(sym) and _SYMBOL_RE.match(name.upper()):
        sym, name = name.upper(), sym

    return sym, name


async def click_load_more(page):
    """اضغط 'تحميل المزيد' لحد ما التابل يخلص أو نوصل الحد الأقصى."""
    prev_rows = -1
    for i in range(25):
        try:
            btn = await page.wait_for_selector('button:has-text("تحميل المزيد")', timeout=2500)
            if not btn:
                break
            await btn.click()
            await asyncio.sleep(0.8)
            rows = await page.evaluate('() => document.querySelectorAll("table tbody tr").length')
            if rows >= MAX_ROWS_PER_LIST or rows == prev_rows:
                break
            prev_rows = rows
        except Exception:
            break


async def scrape_list(page, market_ar, market_slug, category, list_slug):
    """يسحب قائمة واحدة من سوق واحد ويرجّع list من dicts.

    ملاحظة: القوائم دي مجرد تصنيف (رمز + اسم + ترتيب). البيانات
    fundamental الكاملة بتُسحب أصلاً من السكرابر الأصلي (tradingview_scraper.py)
    فمبناخدش هنا غير الرمز والاسم والترتيب.
    """
    url = f"https://ar.tradingview.com/markets/stocks-{market_slug}/market-movers-{list_slug}/"
    try:
        await page.goto(url, timeout=90000)
        await asyncio.sleep(2)
        await click_load_more(page)

        rows = await page.evaluate('''
            (MAX) => {
                const SYMBOL_RE = /^[A-Z0-9][A-Z0-9.\\-]{1,14}$/;
                const ARABIC = /[\\u0600-\\u06FF]/;
                function pickSymbolName(links) {
                    const texts = Array.from(links).map(a => a.textContent.trim()).filter(t => t && t !== '★' && t !== '☆');
                    let sym = '';
                    for (const t of texts) {
                        if (SYMBOL_RE.test(t.toUpperCase()) && !ARABIC.test(t)) { sym = t.toUpperCase(); break; }
                    }
                    if (!sym) for (const t of texts) { if (SYMBOL_RE.test(t.toUpperCase())) { sym = t.toUpperCase(); break; } }
                    if (!sym && texts.length) sym = texts[texts.length - 1].toUpperCase();
                    const name = texts.find(t => t.toUpperCase() !== (sym || 'ZZZ')) || '';
                    return [sym, name];
                }
                const out = [];
                const trs = document.querySelectorAll('table tbody tr');
                for (let i = 0; i < Math.min(trs.length, MAX); i++) {
                    const row = trs[i];
                    const aTags = row.querySelectorAll('td')[0]?.querySelectorAll('a');
                    if (!aTags || aTags.length < 1) continue;
                    const [symRaw, nameRaw] = pickSymbolName(aTags);
                    const sym = (symRaw || '').split(':').pop();
                    if (!sym) continue;
                    out.push({ symbol: sym, name: nameRaw || sym });
                }
                return out;
            }
        ''', MAX_ROWS_PER_LIST)

        # normalize
        cleaned = []
        for r in rows:
            sym, name = normalize_symbol(r['symbol'], r['name'])
            if sym:
                cleaned.append({'symbol': sym, 'name': name})
        log(f"  📋 {category}: {len(cleaned)} سهم")
        return cleaned
    except Exception as e:
        log(f"  ⚠️ {category}: {str(e)[:50]}")
        return []


def save_to_db(all_entries):
    """يخزّن كل القوائم في جدول screener_lists (يستبدل بيانات اليوم).

    ملاحظة: الجدول بيحتوي الرمز + الاسم + الترتيب بس. البيانات
    fundamental (السعر/الحجم/القطاع/التبويبات) بتُسحب من السكرابر الأصلي
    ومرتبطة بنفس الرمز.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS screener_lists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            list_type TEXT,
            market TEXT,
            rank INTEGER,
            symbol TEXT,
            name TEXT,
            scraped_at TEXT,
            UNIQUE(category, market, symbol)
        )
    ''')
    cursor.execute('DELETE FROM screener_lists')

    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    for entry in all_entries:
        cursor.execute('''
            INSERT OR REPLACE INTO screener_lists
            (category, list_type, market, rank, symbol, name, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            entry['category'], entry['list_type'], entry['market'], entry['rank'],
            entry['symbol'], entry['name'], ts
        ))
    conn.commit()
    conn.close()


async def main():
    log("=" * 50)
    log("🔥 TradingView Screener Lists Scraper (بعد الجلسة)")
    log(f"📊 Markets: {len(MARKETS)}, Lists: {len(SCREENER_LISTS)}")
    log("ℹ️ بسحب الرمز + الاسم + الترتيب (البياناتfundamental من السكرابر الأصلي)")
    log("=" * 50)

    all_entries = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width': 1920, 'height': 1080})

        for market_ar, market_slug in MARKETS.items():
            log(f"🌍 {market_ar}")
            for category, list_slug, label_ar, list_type in SCREENER_LISTS:
                rows = await scrape_list(page, market_ar, market_slug, category, list_slug)
                for rank, r in enumerate(rows, start=1):
                    all_entries.append({
                        'category': category,
                        'list_type': list_type,
                        'market': market_ar,
                        'rank': rank,
                        'symbol': r['symbol'],
                        'name': r['name'],
                    })
                await asyncio.sleep(0.5)
        await browser.close()

    save_to_db(all_entries)

    # Save JSON snapshot (symbol-only)
    out = {}
    for e in all_entries:
        out.setdefault(e['market'], {}).setdefault(e['category'], []).append({
            'rank': e['rank'], 'symbol': e['symbol'], 'name': e['name']
        })
    with open(DATA_DIR / 'screener_lists.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    log("=" * 50)
    log(f"🎉 Done! {len(all_entries)} entries across {len(MARKETS)} markets × {len(SCREENER_LISTS)} lists")
    log("=" * 50)


if __name__ == '__main__':
    asyncio.run(main())
