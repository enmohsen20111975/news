import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
import hashlib

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = _PROJECT_ROOT / 'data'

PENDING_FILE = str(DATA_DIR / 'investing_news_pending.json')
DB_PATH = str(DATA_DIR / 'news.db')


def import_pending_news():
    print('1. Reading pending news file...', flush=True)

    try:
        with open(PENDING_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f'2. Loaded {len(data.get("articles", []))} articles', flush=True)
    except FileNotFoundError:
        print('No pending news file found', flush=True)
        return
    except Exception as e:
        print(f'Error reading file: {e}', flush=True)
        return

    articles = data.get('articles', [])
    if not articles:
        print('No articles to import', flush=True)
        return

    print('3. Connecting to database...', flush=True)
    try:
        conn = sqlite3.connect(DB_PATH, timeout=60)
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA busy_timeout = 30000')
        print('4. Database connected', flush=True)
    except Exception as e:
        print(f'Database connection error: {e}', flush=True)
        return

    saved_count = 0
    for idx, article in enumerate(articles):
        try:
            nid = hashlib.sha256(article['title'][:200].encode()).hexdigest()[:16]
            conn.execute('''
                INSERT OR IGNORE INTO news (id, source, source_type, title, body, url, published_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (nid, 'investing.com', 'web', article['title'], article['title'], article['link'], datetime.now().isoformat()))
            saved_count += 1
            if idx % 10 == 0:
                print(f'5. Processed {idx}/{len(articles)} articles...', flush=True)
        except Exception as e:
            print(f'Error saving article {idx}: {e}', flush=True)
            continue

    print('6. Committing changes...', flush=True)
    conn.commit()

    print('7. Getting stats...', flush=True)
    row = conn.execute('''
        SELECT COUNT(*) as total,
               SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) as pending
        FROM news
    ''').fetchone()

    print(f'Imported {saved_count} articles', flush=True)
    print(f'Total in database: {row[0]}', flush=True)
    print(f'Pending analysis: {row[1]}', flush=True)

    conn.close()
    print('Done', flush=True)


if __name__ == '__main__':
    import_pending_news()
