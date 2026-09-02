import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
import sqlite3
import socket

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env')
DB_PATH = ROOT / 'data' / 'news.db'
LOG_PATH = ROOT / 'data' / 'agent.log'
UI_DIR = ROOT / 'ui'
IMAGES_DIR = ROOT / 'data' / 'telegram_images'
CHANNELS_FILE = ROOT / 'data' / 'telegram_channels.json'

from data.news_store import NewsStore
_store = NewsStore()

_telegram_auth = {
    'client': None,
    'phone': '',
    'phone_code_hash': '',
}

app = FastAPI(title='News Agent Dashboard', version='1.0.0')

app.mount('/ui', StaticFiles(directory=str(UI_DIR)), name='ui')
app.mount('/images', StaticFiles(directory=str(IMAGES_DIR)), name='images')

security = HTTPBearer(auto_error=False)
DASHBOARD_API_KEY = os.getenv('DASHBOARD_API_KEY', 'change-me-dashboard-key')


def _require_auth(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials or credentials.credentials != DASHBOARD_API_KEY:
        raise HTTPException(status_code=401, detail='unauthorized')
    return True


def _db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _stats() -> dict:
    if not DB_PATH.exists():
        return {'total': 0, 'pending': 0, 'analyzed': 0, 'sent': 0}

    conn = _db_connect()
    try:
        row = conn.execute('''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status='analyzed' THEN 1 ELSE 0 END) as analyzed,
                SUM(CASE WHEN sent_ok=1 THEN 1 ELSE 0 END) as sent
            FROM news
        ''').fetchone()
        return dict(row) if row else {'total': 0, 'pending': 0, 'analyzed': 0, 'sent': 0}
    finally:
        conn.close()


def _latest_news(limit: int = 10) -> list[dict]:
    if not DB_PATH.exists():
        return []

    conn = _db_connect()
    try:
        rows = conn.execute('''
            SELECT title, source, source_type, importance, sentiment, impact_type, summary_ar, collected_at, status, sent_ok, tickers, image_paths, image_urls, ocr_text, published_links, raw_analysis
            FROM news
            ORDER BY collected_at DESC
            LIMIT ?
        ''', (limit,)).fetchall()
        result = []
        for r in rows:
            raw_analysis = r['raw_analysis'] or {}
            if isinstance(raw_analysis, str):
                try:
                    raw_analysis = json.loads(raw_analysis)
                except Exception:
                    raw_analysis = {}
            result.append({
                'title': r['title'] or 'بدون عنوان',
                'source': r['source'] or 'غير معروف',
                'source_type': r['source_type'] or 'web',
                'importance': r['importance'] or 0,
                'sentiment': r['sentiment'] or 'neutral',
                'impact_type': r['impact_type'] or 'general',
                'summary_ar': r['summary_ar'] or '',
                'collected_at': r['collected_at'] or '',
                'status': r['status'] or 'pending',
                'sent_ok': bool(r['sent_ok']),
                'tickers': r['tickers'] or [],
                'image_paths': r['image_paths'] or [],
                'image_urls': r['image_urls'] or [],
                'ocr_text': r['ocr_text'] or '',
                'published_links': r['published_links'] or {},
                'raw_analysis': raw_analysis,
                'news_text': raw_analysis.get('news_text', '') or r['summary_ar'] or '',
                'is_valid_news': raw_analysis.get('is_valid_news', True),
            })
        return result
    finally:
        conn.close()


def _last_log_lines(limit: int = 5) -> list[str]:
    if not LOG_PATH.exists():
        return ['لا يوجد سجل بعد']
    try:
        with LOG_PATH.open('r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]
        return lines[-limit:]
    except Exception:
        return ['لا يمكن قراءة السجل الآن']


def _process_running() -> bool:
    try:
        result = subprocess.run(
            ['bash', '-lc', "pgrep -af 'python3 main.py' | grep -v grep >/dev/null 2>&1"],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        return result.returncode == 0
    except Exception:
        return False


def _telegram_session_path() -> str:
    return str(ROOT / 'data' / f'telegram_ui_{socket.gethostname()}')


def _clear_session_file(session_path: str):
    """يمسح ملف الجلسة الفاسد"""
    for suffix in ['', '.session', '.session-journal']:
        p = Path(session_path + suffix)
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass


async def _telegram_client():
    from telethon import TelegramClient
    from telethon.errors import SessionPasswordNeededError

    api_id = os.getenv('TELEGRAM_API_ID', '')
    api_hash = os.getenv('TELEGRAM_API_HASH', '')
    if not api_id or not api_hash:
        raise ValueError('TELEGRAM_API_ID و TELEGRAM_API_HASH غير مضبوطين')

    client = _telegram_auth.get('client')
    if client is None:
        client = TelegramClient(_telegram_session_path(), int(api_id), api_hash)
        await client.connect()
        # تحقق من صلاحية الجلسة — إذا فاسدة، امسحها
        try:
            if not await client.is_user_authorized():
                raise SessionPasswordNeededError('session not authorized')
        except (SessionPasswordNeededError, Exception):
            _clear_session_file(_telegram_session_path())
            client = TelegramClient(_telegram_session_path(), int(api_id), api_hash)
            await client.connect()
        _telegram_auth['client'] = client
    return client


def _save_telegram_channels(channels: list[str]):
    env_path = ROOT / '.env'
    lines = env_path.read_text(encoding='utf-8').splitlines() if env_path.exists() else []
    value = ','.join(channels)
    for index, line in enumerate(lines):
        if line.startswith('TELEGRAM_CHANNELS='):
            lines[index] = f'TELEGRAM_CHANNELS={value}'
            break
    else:
        lines.append(f'TELEGRAM_CHANNELS={value}')
    if any(line.startswith('ENABLE_TELEGRAM=') for line in lines):
        lines = [
            'ENABLE_TELEGRAM=1' if line.startswith('ENABLE_TELEGRAM=') else line
            for line in lines
        ]
    else:
        lines.append('ENABLE_TELEGRAM=1')
    env_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def _load_channels_file() -> list[dict]:
    if not CHANNELS_FILE.exists():
        return []
    try:
        data = json.loads(CHANNELS_FILE.read_text(encoding='utf-8'))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_channels_file(channels: list[dict]):
    CHANNELS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CHANNELS_FILE.write_text(json.dumps(channels, ensure_ascii=False, indent=2), encoding='utf-8')


@app.get('/api/telegram/status')
async def telegram_status(auth: bool = Depends(_require_auth)):
    try:
        client = await _telegram_client()
        authorized = await client.is_user_authorized()
        return {'ok': True, 'authorized': authorized, 'phone': _telegram_auth['phone']}
    except Exception as exc:
        return JSONResponse({'ok': False, 'authorized': False, 'message': str(exc)}, status_code=400)


@app.post('/api/telegram/send-code')
async def telegram_send_code(request: Request):
    body = await request.json()
    phone = (body.get('phone') or '').strip()
    if not phone:
        return JSONResponse({'ok': False, 'message': 'أدخل رقم الهاتف بصيغة دولية مثل +201xxxxxxxxx'}, status_code=400)
    try:
        client = await _telegram_client()
        if await client.is_user_authorized():
            _telegram_auth['phone'] = phone
            return {'ok': True, 'authorized': True, 'message': 'الجلسة مسجلة بالفعل'}
        sent = await client.send_code_request(phone)
        _telegram_auth.update(phone=phone, phone_code_hash=sent.phone_code_hash)
        return {'ok': True, 'authorized': False, 'message': 'تم إرسال كود Telegram إلى حسابك'}
    except Exception as exc:
        return JSONResponse({'ok': False, 'message': str(exc)}, status_code=400)


@app.post('/api/telegram/verify')
async def telegram_verify(request: Request):
    body = await request.json()
    code = (body.get('code') or '').strip()
    password = body.get('password') or ''
    if not code:
        return JSONResponse({'ok': False, 'message': 'أدخل كود Telegram'}, status_code=400)
    try:
        from telethon.errors import SessionPasswordNeededError

        client = await _telegram_client()
        try:
            await client.sign_in(
                phone=_telegram_auth['phone'],
                code=code,
                phone_code_hash=_telegram_auth['phone_code_hash'],
            )
        except SessionPasswordNeededError:
            if not password:
                return {'ok': False, 'needs_password': True, 'message': 'الحساب محمي بكلمة مرور التحقق بخطوتين'}
            await client.sign_in(password=password)
        return {'ok': True, 'authorized': True, 'message': 'تم تسجيل الدخول بنجاح'}
    except Exception as exc:
        return JSONResponse({'ok': False, 'message': str(exc)}, status_code=400)


@app.post('/api/telegram/send-code')
async def telegram_send_code(request: Request, auth: bool = Depends(_require_auth)):
    body = await request.json()
    phone = (body.get('phone') or '').strip()
    if not phone:
        return JSONResponse({'ok': False, 'message': 'أدخل رقم الهاتف بصيغة دولية مثل +201xxxxxxxxx'}, status_code=400)
    try:
        client = await _telegram_client()
        if await client.is_user_authorized():
            _telegram_auth['phone'] = phone
            return {'ok': True, 'authorized': True, 'message': 'الجلسة مسجلة بالفعل'}
        sent = await client.send_code_request(phone)
        _telegram_auth.update(phone=phone, phone_code_hash=sent.phone_code_hash)
        return {'ok': True, 'authorized': False, 'message': 'تم إرسال كود Telegram إلى حسابك'}
    except Exception as exc:
        return JSONResponse({'ok': False, 'message': str(exc)}, status_code=400)


@app.post('/api/telegram/verify')
async def telegram_verify(request: Request, auth: bool = Depends(_require_auth)):
    body = await request.json()
    code = (body.get('code') or '').strip()
    password = body.get('password') or ''
    if not code:
        return JSONResponse({'ok': False, 'message': 'أدخل كود Telegram'}, status_code=400)
    try:
        from telethon.errors import SessionPasswordNeededError

        client = await _telegram_client()
        try:
            await client.sign_in(
                phone=_telegram_auth['phone'],
                code=code,
                phone_code_hash=_telegram_auth['phone_code_hash'],
            )
        except SessionPasswordNeededError:
            if not password:
                return {'ok': False, 'needs_password': True, 'message': 'الحساب محمي بكلمة مرور التحقق بخطوتين'}
            await client.sign_in(password=password)
        return {'ok': True, 'authorized': True, 'message': 'تم تسجيل الدخول بنجاح'}
    except Exception as exc:
        return JSONResponse({'ok': False, 'message': str(exc)}, status_code=400)


@app.get('/api/telegram/channels')
async def telegram_channels(auth: bool = Depends(_require_auth)):
    try:
        client = await _telegram_client()
        if not await client.is_user_authorized():
            return JSONResponse({'ok': False, 'message': 'سجل الدخول أولاً'}, status_code=401)
        channels = []
        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            if getattr(entity, 'broadcast', False) or getattr(entity, 'megagroup', False):
                username = getattr(entity, 'username', '')
                channels.append({
                    'id': str(entity.id),
                    'title': dialog.title,
                    'username': f'@{username}' if username else '',
                    'value': f'@{username}' if username else str(entity.id),
                })
        return {'ok': True, 'channels': channels}
    except Exception as exc:
        return JSONResponse({'ok': False, 'message': str(exc)}, status_code=400)


@app.post('/api/telegram/channels')
async def save_telegram_channels(request: Request, auth: bool = Depends(_require_auth)):
    body = await request.json()
    channels = [str(value).strip() for value in body.get('channels', []) if str(value).strip()]
    if not channels:
        return JSONResponse({'ok': False, 'message': 'اختر قناة واحدة على الأقل'}, status_code=400)
    _save_telegram_channels(channels)
    saved = [
        {'value': c, 'title': c, 'username': c if c.startswith('@') else ''}
        for c in channels
    ]
    _save_channels_file(saved)
    return {'ok': True, 'channels': channels, 'message': 'تم حفظ قنوات جمع الأخبار'}


@app.get('/api/telegram/managed-channels')
async def managed_channels(auth: bool = Depends(_require_auth)):
    channels = _load_channels_file()
    return {'ok': True, 'channels': channels}


@app.post('/api/telegram/managed-channels')
async def upsert_managed_channel(request: Request, auth: bool = Depends(_require_auth)):
    body = await request.json()
    channel = {
        'value': str(body.get('value', '')).strip(),
        'title': str(body.get('title', '')).strip(),
        'username': str(body.get('username', '')).strip(),
    }
    if not channel['value']:
        return JSONResponse({'ok': False, 'message': 'قيمة القناة مطلوبة'}, status_code=400)

    channels = _load_channels_file()
    existing_index = next((i for i, c in enumerate(channels) if c.get('value') == channel['value']), -1)
    if existing_index >= 0:
        channels[existing_index] = channel
    else:
        channels.append(channel)
    _save_channels_file(channels)
    return {'ok': True, 'channel': channel, 'message': 'تم حفظ القناة'}


@app.delete('/api/telegram/managed-channels')
async def delete_managed_channel(request: Request, auth: bool = Depends(_require_auth)):
    body = await request.json()
    value = str(body.get('value', '')).strip()
    if not value:
        return JSONResponse({'ok': False, 'message': 'قيمة القناة مطلوبة للحذف'}, status_code=400)
    channels = [c for c in _load_channels_file() if c.get('value') != value]
    _save_channels_file(channels)
    return {'ok': True, 'message': 'تم حذف القناة'}


@app.get('/')
def index() -> HTMLResponse:
    html_path = ROOT / 'ui' / 'index.html'
    return HTMLResponse(html_path.read_text(encoding='utf-8'))


@app.get('/api/status')
def status():
    data = {
        'timestamp': datetime.utcnow().isoformat(),
        'running': _process_running(),
        'stats': {k: int(v or 0) for k, v in _stats().items()},
        'latest': _latest_news(10),
        'last_log': _last_log_lines(5),
    }
    return data


@app.post('/api/monitor/start')
def start_monitor():
    if _process_running():
        return JSONResponse({'ok': True, 'running': True, 'message': 'المشروع يعمل بالفعل'})

    subprocess.Popen(
        ["bash", "-lc", "source .venv/bin/activate && python3 main.py >> data/agent.log 2>&1"],
        cwd=str(ROOT),
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return JSONResponse({'ok': True, 'running': True, 'message': 'تم تشغيل المشروع'})


@app.post('/api/monitor/stop')
def stop_monitor():
    subprocess.run(['bash', '-lc', "pkill -f 'python3 main.py' || true"], cwd=str(ROOT), capture_output=True)
    return JSONResponse({'ok': True, 'running': False, 'message': 'تم إيقاف المشروع'})


@app.post('/api/ingest')
async def ingest(request: Request):
    """استقبال نص خبر نسخ يدوياً (من فيسبوك، واتساب، مجموعات...) للتحليل بالذكاء الاصطناعي المحلي"""
    import json as _json
    try:
        body = _json.loads(await request.body())
    except Exception:
        return JSONResponse({'ok': False, 'message': 'بيانات غير صالحة'}, status_code=400)

    text = (body.get('text') or '').strip()
    source = body.get('source', 'manual_copy')
    title = body.get('title', '')

    if not text:
        return JSONResponse({'ok': False, 'message': 'النص فارغ'}, status_code=400)

    nid = _store.add(
        source=source,
        source_type='copy',
        body=text,
        title=title or text[:80].replace('\n', ' '),
    )

    if nid:
        return JSONResponse({'ok': True, 'id': nid, 'message': 'تم إضافة الخبر للتحليل'})
    return JSONResponse({'ok': False, 'message': 'الخبر مكرر'}, status_code=200)


@app.get('/api/recommendations')
def recommendations():
    if not DB_PATH.exists():
        return {'groups': [], 'total': 0, 'group_count': 0}

    conn = _db_connect()
    try:
        rows = conn.execute('''
            SELECT * FROM expert_recommendations
            ORDER BY created_at DESC
        ''').fetchall()

        recs = []
        for r in rows:
            source_ids = r['source_news_ids'] or '[]'
            try:
                source_ids_list = json.loads(source_ids)
            except Exception:
                source_ids_list = []

            recs.append({
                'id': r['id'],
                'stock_symbol': r['stock_symbol'] or '',
                'stock_name_ar': r['stock_name_ar'] or '',
                'expert_name': r['expert_name'] or '',
                'expert_source': r['expert_source'] or '',
                'action': r['action'] or 'BUY',
                'recommendation_type': r['recommendation_type'] or '',
                'entry_price': r['entry_price'],
                'entry_price_from': r['entry_price_from'],
                'entry_price_to': r['entry_price_to'],
                'target_price': r['target_price'],
                'target_price_2': r['target_price_2'],
                'stop_loss': r['stop_loss'],
                'support_level': r['support_level'],
                'resistance_level': r['resistance_level'],
                'technical_analysis': r['technical_analysis'] or '',
                'recommendation_reason': r['recommendation_reason'] or '',
                'session_date': r['session_date'] or '',
                'status': r['status'] or 'PENDING',
                'sent_ok': bool(r['sent_ok']),
                'source_count': len(source_ids_list),
                'created_at': r['created_at'] or '',
            })

        groups = {}
        for rec in recs:
            key = rec['stock_symbol']
            if key not in groups:
                groups[key] = {
                    'symbol': key,
                    'name_ar': rec['stock_name_ar'],
                    'count': 0,
                    'recommendations': []
                }
            groups[key]['count'] += 1
            groups[key]['recommendations'].append(rec)

        return {
            'groups': list(groups.values()),
            'total': len(recs),
            'group_count': len(groups),
        }
    finally:
        conn.close()


@app.get('/health')
def health():
    return {'ok': True, 'service': 'news-agent-dashboard'}
