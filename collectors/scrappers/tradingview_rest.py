#!/usr/bin/env python3
"""
TradingView REST Fetcher — Lightweight (NO Playwright)
========================================================

الوظيفة:
  - يجيب أسعار الأسهم من TradingView عن طريق الـ Scanner REST endpoint
    (https://scanner.tradingview.com/{market}/scan) بدون ما يفتح browser ولا
    Playwright — بـ HTTP POST عادي باستخدام urllib (stdlib only).
  - أخف بكتير من tradingview_scraper.py (اللي بيستخدم Playwright في subprocess
    وبياخد 60-120 ثانية) — الـ REST endpoint بيرجع الـ data في ثواني.
  - بيرجّع list of dicts بنفس شكل باقي الـ scrapers في الـ fallback chain:
    {symbol, name, price, change_percent, volume, market_cap, sector, market, tabs_data}
  - بيحفظ في /home/z/my-project/db/data_engine.db (نفس schema بتاع الـ chain).

الـ Endpoint المدعوم:
  POST https://scanner.tradingview.com/{market}/scan
  Headers: {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0 ..."}
  Body:
    {
      "range": [0, 300],
      "columns": ["name","description","close","change","change_abs",
                  "volume","market_cap_basic","sector",
                  "Recommend.All","RSI","RSI[1]","MACD.macd","MACD.signal"],
      "sort": {"sortBy": "name", "sortOrder": "asc"},
      "markets": ["{market}"]
    }
  Response: {"data": [{"d": {"name":"COMI","close":..., ...}}, ...]}

الأسواق المدعومة (slug الـ TradingView):
  - egypt  (EGX — الأساسي)
  - saudi  (TADAWUL)
  - kuwait (Boursa Kuwait)
  - qatar  (QSE)

@author M2y Platform
@version 1.0.0 — يوليو 2026 (Phase 1 Data Sources Cleanup)
"""
from __future__ import annotations

import os
import sys
import json
import sqlite3
import logging
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any

# ============================================================================
# Paths
# ============================================================================
_THIS_DIR = Path(__file__).resolve().parent                  # data_engine/scrapers/
_DATA_ENGINE_DIR = _THIS_DIR.parent                          # data_engine/
_PROJECT_ROOT = _DATA_ENGINE_DIR.parent                      # my-project/
DB_FILE = str(_PROJECT_ROOT / 'db' / 'data_engine.db')

# ============================================================================
# Config
# ============================================================================
DEFAULT_TIMEOUT = float(os.environ.get('TRADINGVIEW_REST_TIMEOUT', '20'))

# Market slug mapping (the platform uses Arabic market labels in DB; TradingView
# uses latin slugs in its scanner URL). The PRIMARY use case is Egypt = 'egypt'.
_MARKET_SLUG_MAP = {
    'egypt': 'egypt',
    'saudi': 'saudi',
    'kuwait': 'kuwait',
    'qatar': 'qatar',
    # Arabic-friendly aliases (in case caller passes Arabic label)
    'مصر': 'egypt',
    'السعودية': 'saudi',
    'الكويت': 'kuwait',
    'قطر': 'qatar',
}

# Arabic display labels per TV slug (written to the `market` column in DB).
_MARKET_AR_LABEL = {
    'egypt': 'مصر',
    'saudi': 'السعودية',
    'kuwait': 'الكويت',
    'qatar': 'قطر',
}

# Scanner columns we request. We map these to our stock dict in `_map_row`.
_TV_COLUMNS = [
    'name', 'description', 'close', 'change', 'change_abs',
    'volume', 'market_cap_basic', 'sector',
    'Recommend.All', 'RSI', 'RSI[1]', 'MACD.macd', 'MACD.signal',
]

# ============================================================================
# Logging
# ============================================================================
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter(
        '[%(asctime)s] [%(levelname)s] [TV-REST] %(message)s',
        datefmt='%H:%M:%S',
    ))
    logger.addHandler(_h)


def log(msg: str, level: str = 'info') -> None:
    ts = datetime.now().strftime('%H:%M:%S')
    print(f"[{ts}] {msg}")
    getattr(logger, level.lower(), logger.info)(msg)


# ============================================================================
# HTTP — POST JSON via urllib (stdlib only, no requests dependency)
# ============================================================================

def _http_post_json(url: str, body: Dict, timeout: float = DEFAULT_TIMEOUT) -> Optional[Dict]:
    """POST JSON to a URL and return parsed JSON, or None on error."""
    try:
        payload = json.dumps(body).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=payload,
            method='POST',
            headers={
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'User-Agent': (
                    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
                ),
                'Origin': 'https://www.tradingview.com',
                'Referer': 'https://www.tradingview.com/',
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                log(f"HTTP {resp.status} from {url}", 'error')
                return None
            raw = resp.read().decode('utf-8', errors='replace')
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        log(f"HTTPError {e.code} from {url}: {e.reason}", 'error')
        return None
    except urllib.error.URLError as e:
        log(f"URLError fetching {url}: {e}", 'error')
        return None
    except json.JSONDecodeError as e:
        log(f"JSON decode error from {url}: {e}", 'error')
        return None
    except Exception as e:
        log(f"Unexpected error fetching {url}: {e}", 'error')
        return None


# ============================================================================
# Helpers
# ============================================================================

def _normalize_market(market: str) -> str:
    """Map any alias (arabic or latin) to the canonical TradingView slug."""
    if not market:
        return 'egypt'
    key = market.strip().lower()
    if key in _MARKET_SLUG_MAP:
        return _MARKET_SLUG_MAP[key]
    if market in _MARKET_SLUG_MAP:
        return _MARKET_SLUG_MAP[market]
    # Pass through if already a slug (e.g. 'america', 'vietnam', ...)
    return key


def _to_float(val: Any) -> float:
    if val is None:
        return 0.0
    try:
        if isinstance(val, str):
            s = val.strip().replace(',', '').replace('%', '').replace('+', '')
            s = s.replace('−', '-').replace('K', '').replace('M', '').replace('B', '')
            return float(s) if s else 0.0
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _to_str(val: Any) -> str:
    if val is None:
        return ''
    try:
        s = str(val).strip()
        return s if s else ''
    except Exception:
        return ''


def _is_index_symbol(symbol: str) -> bool:
    """فلتر الـ indices (مثل .EGX30) — مش أسهم قابلة للتداول."""
    if not symbol:
        return False
    return symbol.startswith('.') or symbol.upper().startswith('EGX')


# ============================================================================
# Row mapping
# ============================================================================

def _map_row(row: Any, market_label: str) -> Optional[Dict]:
    """
    Map a single TradingView scanner row to our unified stock dict.

    TradingView's scanner returns rows in two possible shapes:
      1. {"s": "EGX:COMI", "d": ["COMI", "desc", 30.5, ...]}   # positional list
      2. {"s": "EGX:COMI", "d": {"name": "COMI", "close": 30.5, ...}}  # keyed dict

    The positional list is the most common in practice: the values in `d` are in
    the SAME ORDER as the `columns` field in the request body. We handle both.
    """
    try:
        if not isinstance(row, dict):
            return None
        d = row.get('d')
        if d is None:
            return None

        # Build a column-index → value lookup that works for both shapes.
        if isinstance(d, list):
            # positional: zip with the columns list we requested
            vals = dict(zip(_TV_COLUMNS, d))
        elif isinstance(d, dict):
            vals = d
        else:
            return None

        symbol = _to_str(vals.get('name')).strip()
        if not symbol or _is_index_symbol(symbol):
            return None

        price = _to_float(vals.get('close'))
        if price <= 0:
            return None  # skip empty / zero-price rows

        change_pct = _to_float(vals.get('change'))
        change_abs = _to_float(vals.get('change_abs'))
        volume = _to_float(vals.get('volume'))
        market_cap = _to_float(vals.get('market_cap_basic'))
        sector = _to_str(vals.get('sector'))
        description = _to_str(vals.get('description')) or symbol

        # Optional technicals — packed into tabs_data for downstream consumers.
        recommend = vals.get('Recommend.All')
        rsi = vals.get('RSI')
        rsi_prev = vals.get('RSI[1]')
        macd = vals.get('MACD.macd')
        macd_signal = vals.get('MACD.signal')

        tabs_data = {
            'recommendation': _to_float(recommend),
            'rsi': _to_float(rsi),
            'rsi_prev': _to_float(rsi_prev),
            'macd': _to_float(macd),
            'macd_signal': _to_float(macd_signal),
            'change_abs': change_abs,
            'source': 'tradingview_rest',
        }

        return {
            'symbol': symbol,
            'name': description,
            'price': price,
            'change_percent': change_pct,
            'volume': str(int(volume)) if volume > 0 else '',
            'market_cap': str(market_cap) if market_cap > 0 else '',
            'sector': sector,
            'market': market_label,
            'tabs_data': tabs_data,
        }
    except Exception as e:
        log(f"⚠️ Map error on row {str(row)[:60]}: {e}", 'warning')
        return None


# ============================================================================
# DB Save (same schema as egxpilot_scraper / tradingview_scraper)
# ============================================================================

def save_to_db(stocks: List[Dict], market: str = 'مصر') -> int:
    """
    حفظ الأسهم في data_engine.db (نفس schema بتاع الـ chain).
    Returns: عدد الأسهم المحفوظة.
    """
    if not stocks:
        return 0

    # Ensure parent dir exists
    try:
        Path(DB_FILE).parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    conn = sqlite3.connect(DB_FILE, timeout=30.0)
    try:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA busy_timeout=30000')
    except Exception:
        pass
    cursor = conn.cursor()

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

    saved = 0
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    for s in stocks:
        try:
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
                    tabs_data = excluded.tabs_data,
                    last_update = excluded.last_update
            ''', (
                s.get('symbol', ''), s.get('name', ''),
                float(s.get('price', 0) or 0),
                float(s.get('change_percent', 0) or 0),
                s.get('volume', ''), s.get('market_cap', ''),
                s.get('sector', ''), market,
                json.dumps(s.get('tabs_data', {}), ensure_ascii=False), now,
            ))
            saved += 1
        except Exception as e:
            log(f"⚠️ DB save error for {s.get('symbol', '?')}: {e}", 'warning')

    conn.commit()
    conn.close()
    return saved


# ============================================================================
# Public API
# ============================================================================

def fetch_tradingview_stocks(market: str = 'egypt') -> Tuple[List[Dict], str]:
    """
    جلب أسعار الأسهم من TradingView Scanner REST endpoint (بدون Playwright).

    Args:
        market: TradingView market slug ('egypt' | 'saudi' | 'kuwait' | 'qatar')
                أو الاسم العربي ('مصر', 'السعودية', ...). الافتراضي: 'egypt'.

    Returns:
        Tuple[List[Dict], str]:
          - stocks_list: قائمة الـ stock dicts (نفس شكل الـ chain).
          - status_message: 'success' أو رسالة خطأ.
          على الفشل بيرجّع ([], error_msg) — ما بيرمي exception أبداً.
    """
    slug = _normalize_market(market)
    ar_label = _MARKET_AR_LABEL.get(slug, slug)
    url = f"https://scanner.tradingview.com/{slug}/scan"

    body = {
        'range': [0, 300],
        'columns': _TV_COLUMNS,
        'sort': {'sortBy': 'name', 'sortOrder': 'asc'},
        'markets': [slug],
    }

    log(f"📡 TradingView REST → POST {url} (market={slug})")
    data = _http_post_json(url, body, timeout=DEFAULT_TIMEOUT)
    if not data:
        return [], f"TradingView REST ({slug}): لا استجابة من الـ endpoint"

    rows = data.get('data') or []
    if not rows:
        return [], f"TradingView REST ({slug}): استجابة فاضية (data=[])"

    stocks: List[Dict] = []
    for row in rows:
        mapped = _map_row(row, market_label=ar_label)
        if mapped:
            stocks.append(mapped)

    if not stocks:
        return [], f"TradingView REST ({slug}): 0 سهم صالح من {len(rows)} صف"

    log(f"✅ TradingView REST ({slug}): تم استلام {len(stocks)} سهم")
    return stocks, 'success'


def fetch_tradingview_stocks_and_save(market: str = 'egypt') -> Dict:
    """
    Fetch + save in one shot (مفيد للـ standalone testing).

    Returns:
        Dict: {success, source, stocks_count, market, message}
    """
    slug = _normalize_market(market)
    ar_label = _MARKET_AR_LABEL.get(slug, slug)

    stocks, status = fetch_tradingview_stocks(market=slug)
    if not stocks:
        return {
            'success': False,
            'source': 'tradingview_rest',
            'stocks_count': 0,
            'market': ar_label,
            'message': status,
        }

    saved = save_to_db(stocks, market=ar_label)
    return {
        'success': True,
        'source': 'tradingview_rest',
        'stocks_count': saved,
        'market': ar_label,
        'message': f'تم حفظ {saved} سهم من TradingView REST ({slug})',
    }


# ============================================================================
# CLI Entry
# ============================================================================

def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description='TradingView REST fetcher (no Playwright)')
    parser.add_argument('--market', default='egypt',
                        help='TradingView market slug: egypt|saudi|kuwait|qatar (default: egypt)')
    args = parser.parse_args()

    log("=" * 60)
    log("📡 TradingView REST Fetcher (no Playwright)")
    log(f"Market: {args.market}")
    log("=" * 60)

    result = fetch_tradingview_stocks_and_save(market=args.market)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result['success'] else 1


if __name__ == '__main__':
    sys.exit(main())
