import requests
import json
import sys
import hashlib
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

BASE_URL = 'https://beta.egx.com.eg'
DB_PATH = Path(__file__).parent.parent.parent / 'data' / 'news.db'

HEADERS = {
    'Content-Type': 'application/json',
    'x-egx-bff-request': '1',
    'Accept': 'application/json',
    'Origin': 'https://beta.egx.com.eg',
    'Referer': 'https://beta.egx.com.eg/ar/media-center',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'ar-SA',
}

TABS_CONFIG = {
    'listing': {'secIds': [11, 12, 13]},
    'disclosure': {'secIds': [3, 4, 5, 6, 7, 8, 16]},
    'financials': {'secIds': [3, 4, 5, 6, 7, 8, 16]},
    'members': {'secIds': [10]},
}

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30, check_same_thread=False)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout = 30000')
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS news (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            source_type TEXT NOT NULL DEFAULT 'web',
            title TEXT,
            body TEXT NOT NULL,
            url TEXT,
            published_at TEXT,
            collected_at TEXT NOT NULL DEFAULT (datetime('now')),
            status TEXT NOT NULL DEFAULT 'pending',
            tickers TEXT,
            importance INTEGER DEFAULT 0,
            sentiment TEXT DEFAULT 'neutral',
            impact_type TEXT,
            summary_ar TEXT,
            summary_en TEXT,
            raw_analysis TEXT,
            image_paths TEXT,
            image_urls TEXT,
            ocr_text TEXT,
            published_links TEXT,
            sent_at TEXT,
            sent_ok INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_news_status ON news(status);
        CREATE INDEX IF NOT EXISTS idx_news_collected ON news(collected_at);
    ''')
    conn.commit()
    return conn

def add_news(conn, source, source_type, body, title='', url='', published_at=''):
    nid = hashlib.sha256(body[:200].encode()).hexdigest()[:16]
    try:
        conn.execute('''
            INSERT OR IGNORE INTO news (id, source, source_type, title, body, url, published_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (nid, source, source_type, title, body, url, published_at or datetime.now().isoformat()))
        conn.commit()
        return nid
    except sqlite3.IntegrityError:
        return None
    except sqlite3.OperationalError as e:
        if 'locked' in str(e).lower():
            print(f'DB locked, retrying...', flush=True)
            import time
            time.sleep(2)
            try:
                conn.execute('''
                    INSERT OR IGNORE INTO news (id, source, source_type, title, body, url, published_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (nid, source, source_type, title, body, url, published_at or datetime.now().isoformat()))
                conn.commit()
                return nid
            except Exception:
                return None
        raise

def fetch_egx_news(tab, sec_ids, date_from, date_to, page=1, page_size=20):
    payload = {
        'marketSessionNews': False,
        'secIds': sec_ids,
        'interval': 50,
        'pageNumber': page,
        'pageSize': page_size,
        'dateFrom': date_from,
        'dateTo': date_to,
        'count': 50
    }
    
    try:
        resp = requests.post(
            f'{BASE_URL}/api/bff/egx/news-search',
            headers=HEADERS,
            json=payload,
            timeout=30
        )
        if 'application/json' in resp.headers.get('Content-Type', ''):
            return resp.json()
    except Exception as e:
        print(f'Error fetching {tab} page {page}: {e}', flush=True)
    
    return None

def main():
    print('=== EGX News Scraper ===', flush=True)
    conn = init_db()
    
    date_from = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    date_to = datetime.now().strftime('%Y-%m-%d')
    
    total_saved = 0
    
    for tab, config in TABS_CONFIG.items():
        print(f'\n--- Processing tab: {tab} ---', flush=True)
        page = 1
        while True:
            print(f'  Page {page}...', flush=True)
            data = fetch_egx_news(tab, config['secIds'], date_from, date_to, page)
            
            if not data or 'data' not in data or not data['data']:
                print(f'  No more data for {tab}', flush=True)
                break
            
            items = data['data']
            print(f'  Found {len(items)} items', flush=True)
            
            for item in items:
                title = item.get('headingArabic') or item.get('heading') or ''
                body = item.get('contentArabic') or item.get('content') or ''
                date_stamp = item.get('dateStamp', '')
                
                news_id = add_news(
                    conn,
                    source='egx.com.eg',
                    source_type='web',
                    body=body,
                    title=title,
                    url=f"{BASE_URL}/ar/media-center?tab={tab}",
                    published_at=date_stamp
                )
                
                if news_id:
                    total_saved += 1
            
            if len(items) < 20:
                break
            
            page += 1
    
    print(f'\n=== Summary ===', flush=True)
    print(f'Total saved: {total_saved}', flush=True)
    
    row = conn.execute('''
        SELECT COUNT(*) as total,
               SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) as pending
        FROM news
    ''').fetchone()
    print(f'Total in database: {row[0]}', flush=True)
    print(f'Pending analysis: {row[1]}', flush=True)
    
    conn.close()

if __name__ == '__main__':
    main()
