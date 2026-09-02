"""
قاعدة بيانات SQLite محلية لتخزين الأخبار قبل إرسالها
"""

import sqlite3
import hashlib
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / 'data' / 'news.db'


class NewsStore:
    """مخزن الأخبار المحلي"""

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self):
        self.conn.executescript('''
            CREATE TABLE IF NOT EXISTS news (
                id          TEXT PRIMARY KEY,
                source      TEXT NOT NULL,
                source_type TEXT NOT NULL DEFAULT 'web',
                title       TEXT,
                body        TEXT NOT NULL,
                url         TEXT,
                published_at TEXT,
                collected_at TEXT NOT NULL DEFAULT (datetime('now')),
                status      TEXT NOT NULL DEFAULT 'pending',
                tickers     TEXT,
                importance  INTEGER DEFAULT 0,
                sentiment   TEXT DEFAULT 'neutral',
                impact_type TEXT,
                summary_ar  TEXT,
                summary_en  TEXT,
                raw_analysis TEXT,
                image_paths TEXT,
                image_urls  TEXT,
                ocr_text    TEXT,
                published_links TEXT,
                sent_at     TEXT,
                sent_ok     INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_news_status    ON news(status);
            CREATE INDEX IF NOT EXISTS idx_news_collected ON news(collected_at);
            CREATE INDEX IF NOT EXISTS idx_news_tickers   ON news(tickers);

            CREATE TABLE IF NOT EXISTS expert_recommendations (
                id          TEXT PRIMARY KEY,
                stock_symbol TEXT NOT NULL,
                stock_name_ar TEXT,
                expert_name TEXT NOT NULL,
                expert_source TEXT,
                action      TEXT NOT NULL DEFAULT 'BUY',
                recommendation_type TEXT,
                entry_price REAL,
                entry_price_from REAL,
                entry_price_to   REAL,
                target_price     REAL,
                target_price_2   REAL,
                stop_loss        REAL,
                support_level    REAL,
                resistance_level REAL,
                technical_analysis TEXT,
                recommendation_reason TEXT,
                session_date TEXT,
                notes        TEXT,
                source_news_ids TEXT,
                status       TEXT NOT NULL DEFAULT 'PENDING',
                sent_ok      INTEGER DEFAULT 0,
                sent_at      TEXT,
                remote_id    TEXT,
                created_at   TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_rec_symbol  ON expert_recommendations(stock_symbol);
            CREATE INDEX IF NOT EXISTS idx_rec_session ON expert_recommendations(session_date);
            CREATE INDEX IF NOT EXISTS idx_rec_status  ON expert_recommendations(status);
        ''')

        columns = {
            row['name'] for row in self.conn.execute('PRAGMA table_info(news)').fetchall()
        }
        for column, query in (
            ('image_urls', "ALTER TABLE news ADD COLUMN image_urls TEXT"),
            ('published_links', "ALTER TABLE news ADD COLUMN published_links TEXT"),
            ('ocr_text', "ALTER TABLE news ADD COLUMN ocr_text TEXT"),
            ('image_paths', "ALTER TABLE news ADD COLUMN image_paths TEXT"),
        ):
            if column not in columns:
                self.conn.execute(query)
        self.conn.commit()

    def _make_id(self, text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def add(self, source: str, source_type: str, body: str,
            title: str = '', url: str = '', published_at: str = '',
            image_urls: str = '', image_paths: str = '') -> str | None:
        """أضف خبر جديد — ارجع ID أو None لو موجود"""
        nid = self._make_id(body[:200])
        try:
            self.conn.execute('''
                INSERT INTO news (id, source, source_type, title, body, url, published_at, image_urls, image_paths)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (nid, source, source_type, title, body, url,
                  published_at or datetime.now().isoformat(),
                  image_urls, image_paths))
            self.conn.commit()
            return nid
        except sqlite3.IntegrityError:
            return None  # خبر مكرر

    def get_pending_analysis(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM news WHERE status = 'pending' ORDER BY collected_at ASC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def save_analysis(self, news_id: str, result: dict):
        image_paths = result.get('image_paths', [])
        if isinstance(image_paths, (list, tuple)):
            image_paths_json = json.dumps(list(image_paths), ensure_ascii=False)
        elif isinstance(image_paths, str):
            image_paths_json = image_paths
        else:
            image_paths_json = '[]'

        self.conn.execute('''
            UPDATE news SET
                status       = 'analyzed',
                tickers      = ?,
                importance   = ?,
                sentiment    = ?,
                impact_type  = ?,
                summary_ar   = ?,
                summary_en   = ?,
                ocr_text     = ?,
                image_paths  = ?,
                raw_analysis = ?
            WHERE id = ?
        ''', (
            json.dumps(result.get('tickers', []), ensure_ascii=False),
            result.get('importance', 0),
            result.get('sentiment', 'neutral'),
            result.get('impact_type', 'general'),
            result.get('summary_ar', ''),
            result.get('summary_en', ''),
            result.get('ocr_text', ''),
            image_paths_json,
            json.dumps(result, ensure_ascii=False),
            news_id
        ))
        self.conn.commit()

    def save_published_links(self, news_id: str, links: dict):
        """حفظ روابط المنصات المنشورة عليها الخبر"""
        if not links:
            return
        existing = self.conn.execute('SELECT published_links FROM news WHERE id = ?', (news_id,)).fetchone()
        current = json.loads(existing['published_links']) if existing and existing['published_links'] else {}
        current.update(links)
        self.conn.execute('UPDATE news SET published_links = ? WHERE id = ?', (json.dumps(current, ensure_ascii=False), news_id))
        self.conn.commit()

    def get_important_unsent(self, min_score: int = 55, limit: int = 20) -> list[dict]:
        rows = self.conn.execute('''
            SELECT * FROM news
            WHERE status = 'analyzed'
              AND importance >= ?
              AND sent_ok = 0
            ORDER BY importance DESC, collected_at DESC
            LIMIT ?
        ''', (min_score, limit)).fetchall()
        return [dict(r) for r in rows]

    def mark_sent(self, ids: list[str]):
        if not ids:
            return
        ph = ','.join('?' * len(ids))
        self.conn.execute(f'''
            UPDATE news SET sent_ok = 1, sent_at = datetime('now'), status = 'sent'
            WHERE id IN ({ph})
        ''', ids)
        self.conn.commit()

    def stats(self) -> dict:
        row = self.conn.execute('''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status='analyzed' THEN 1 ELSE 0 END) as analyzed,
                SUM(CASE WHEN sent_ok=1 THEN 1 ELSE 0 END) as sent
            FROM news
        ''').fetchone()
        return dict(row) if row else {}

    def add_recommendation(self, rec: dict) -> str | None:
        """أضف توصية خبراء — يميز التكرار بناءً على stock_symbol + session_date + entry_price."""
        session_date = rec.get('session_date') or ''
        symbol = rec.get('stock_symbol') or ''
        entry = rec.get('entry_price') or 0
        rid_seed = f"{symbol}|{session_date}|{entry}"
        rid = hashlib.sha256(rid_seed.encode()).hexdigest()[:16]
        try:
            self.conn.execute('''
                INSERT INTO expert_recommendations (
                    id, stock_symbol, stock_name_ar, expert_name, expert_source,
                    action, recommendation_type,
                    entry_price, entry_price_from, entry_price_to,
                    target_price, target_price_2, stop_loss,
                    support_level, resistance_level,
                    technical_analysis, recommendation_reason,
                    session_date, notes, source_news_ids, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                rid,
                rec.get('stock_symbol', ''),
                rec.get('stock_name_ar'),
                rec.get('expert_name', 'محلل محلي'),
                rec.get('expert_source', 'news_agent'),
                rec.get('action', 'BUY'),
                rec.get('recommendation_type', 'detailed'),
                rec.get('entry_price'),
                rec.get('entry_price_from'),
                rec.get('entry_price_to'),
                rec.get('target_price'),
                rec.get('target_price_2'),
                rec.get('stop_loss'),
                rec.get('support_level'),
                rec.get('resistance_level'),
                rec.get('technical_analysis'),
                rec.get('recommendation_reason'),
                rec.get('session_date'),
                rec.get('notes'),
                json.dumps(rec.get('source_news_ids') or [], ensure_ascii=False),
                rec.get('status', 'PENDING'),
            ))
            self.conn.commit()
            return rid
        except sqlite3.IntegrityError:
            return None

    def get_unsent_recommendations(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            'SELECT * FROM expert_recommendations WHERE sent_ok = 0 ORDER BY created_at ASC LIMIT ?',
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_recommendations_sent(self, ids: list[str]):
        if not ids:
            return
        ph = ','.join('?' * len(ids))
        self.conn.execute(
            f'UPDATE expert_recommendations SET sent_ok = 1, sent_at = datetime("now") WHERE id IN ({ph})',
            ids,
        )
        self.conn.commit()

    def update_recommendation_remote_id(self, local_id: str, remote_id: str):
        self.conn.execute(
            'UPDATE expert_recommendations SET remote_id = ? WHERE id = ?',
            (remote_id, local_id),
        )
        self.conn.commit()

    def get_recommendation_candidates(self, since_hours: int = 48) -> list[dict]:
        """يرجع الأخبار المحللة اللي ممكن تحتوي توصيات (للمجمّع)."""
        rows = self.conn.execute('''
            SELECT id, source, title, body, tickers, raw_analysis, importance,
                   collected_at
              FROM news
             WHERE status = 'analyzed'
               AND collected_at >= datetime('now', ?)
             ORDER BY collected_at DESC
             LIMIT 200
        ''', (f'-{since_hours} hours',)).fetchall()
        return [dict(r) for r in rows]
