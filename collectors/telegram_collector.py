"""
جامع أخبار من Telegram
- جلسة خاصة بالجهاز (لتجنب مشاكل IP)
- جمع النصوص + الصور
- استخراج replies و forwards
- معالجة FloodWait
"""

import os
import logging
import asyncio
import socket
from datetime import datetime, timedelta
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.sources import registry
from collectors.keyword_filter import filter_instance

log = logging.getLogger('TelegramCollector')

DEFAULT_CHANNELS = [
    'egyptstock',
    'AlBorsaNews',
    'EGXNews',
]


class TelegramCollector:
    """يجمع رسائل الأخبار من قنوات Telegram"""

    def __init__(self, store):
        self.store = store
        self.client = None
        self._ready = False

        self.api_id   = os.getenv('TELEGRAM_API_ID', '')
        self.api_hash = os.getenv('TELEGRAM_API_HASH', '')
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
        self.use_bot = os.getenv('TELEGRAM_USE_BOT', '0').lower() in ('1', 'true', 'yes', 'on')
        if not self.use_bot and self.bot_token:
            self.use_bot = True
        channels_env  = os.getenv('TELEGRAM_CHANNELS', '')
        self.channels = [c.strip() for c in channels_env.split(',') if c.strip()] \
                        or DEFAULT_CHANNELS

        self.images_dir = Path(__file__).parent.parent / 'data' / 'telegram_images'
        self.images_dir.mkdir(parents=True, exist_ok=True)

        hostname = socket.gethostname()
        # للقراءة: نستخدم جلسة المستخدم دائماً (اللي من شاشة الربط)
        # للإرسال: نستخدم Bot Token لو متوفر
        self._read_session_path = str(Path(__file__).parent.parent / 'data' / f'telegram_ui_{hostname}')
        self._bot_session_path = str(Path(__file__).parent.parent / 'data' / f'telegram_session_{hostname}')
        self._session_path = self._read_session_path  # للقراءة

    def _clear_session_file(self, session_path: str):
        """يمسح ملف الجلسة الفاسد (و .session / -journal)"""
        for suffix in ['', '.session', '.session-journal']:
            p = Path(session_path + suffix)
            if p.exists():
                try:
                    p.unlink()
                except Exception:
                    pass

    async def _init_client(self):
        """تهيئة Telethon client مع جلسة المستخدم للقراءة"""
        if not self.api_id or not self.api_hash:
            log.warning("⚠️ Telegram API_ID/HASH غير مضبوط — تخطي Telegram")
            return False
        try:
            from telethon import TelegramClient
            from telethon.errors import FloodWaitError, AuthKeyError

            # استخدم جلسة المستخدم للقراءة دائماً
            self.client = TelegramClient(self._read_session_path, int(self.api_id), self.api_hash)
            self._flood_wait = FloodWaitError

            # جرب الاتصال بالجلسة المحفوظة
            await self.client.connect()
            if await self.client.is_user_authorized():
                log.info("✓ جلسة Telegram المحفوظة شغالة")
            else:
                # لو مش مسجل، حاول بالـ bot token
                if self.bot_token:
                    log.warning("جلسة المستخدم غير موجودة — محاولة Bot Token...")
                    await self.client.disconnect()
                    self.client = TelegramClient(self._bot_session_path, int(self.api_id), self.api_hash)
                    await self.client.connect()
                    await self.client.start(bot_token=self.bot_token)
                else:
                    log.warning('Telegram غير مسجل — استخدم شاشة ربط Telegram أولاً')
                    await self.client.disconnect()
                    return False

            self._ready = True
            log.info(f"✓ Telegram متصل — {len(self.channels)} قناة")
            return True
        except (Exception, AuthKeyError) as e:
            log.error(f"خطأ في الاتصال بـ Telegram: {e}")
            # إذا كانت الجلسة فاسدة، امسحها وأعد المحاولة مرة واحدة
            if 'Session' in str(type(e).__name__) or 'auth' in str(e).lower():
                self._clear_session_file(self._read_session_path)
                log.warning("✓ تم مسح الجلسة الفاسدة — أعد تشغيل لتسجيل الدخول من جديد")
            return False

    async def collect(self) -> int:
        """جمع آخر الأخبار من كل القنوات"""
        if not self._ready:
            ok = await self._init_client()
            if not ok:
                return 0

        total = 0
        cutoff = datetime.now() - timedelta(hours=6)

        for channel in self.channels:
            try:
                count = await self._collect_from_channel(channel, cutoff)
                total += count
                await asyncio.sleep(1)
            except self._flood_wait as e:
                log.warning(f"⏳ FloodWait: انتظار {e.seconds} ثانية للقناة {channel}")
                await asyncio.sleep(e.seconds + 1)
            except Exception as e:
                log.warning(f"خطأ في قراءة {channel}: {e}")

        return total

    async def _collect_from_channel(self, channel: str, cutoff: datetime) -> int:
        """جمع رسائل من قناة واحدة مع الصور والردود"""
        saved = 0
        try:
            entity = await self._resolve_entity(channel)
            if not entity:
                return 0

            async for msg in self.client.iter_messages(entity, limit=50):
                if msg.date and msg.date.replace(tzinfo=None) < cutoff:
                    break

                if not msg.text and not msg.media:
                    continue

                # جمع الصور
                image_paths = []
                if msg.media:
                    try:
                        path = await self._download_media(msg, channel)
                        if path:
                            image_paths.append(path)
                    except Exception as e:
                        log.debug(f"خطأ تنزيل صورة من {channel}: {e}")

                # جمع نص الرسالة + replies
                body = msg.text or ''
                reply_context = ''
                if msg.reply_to_msg_id:
                    try:
                        reply_msg = await self.client.get_messages(entity, ids=msg.reply_to_msg_id)
                        if reply_msg and reply_msg.text:
                            reply_context = f"\n[رد على: {reply_msg.text[:200]}]"
                    except Exception:
                        pass

                full_text = (body + reply_context).strip()
                if not full_text:
                    continue

                # فلترة المحتوى: نحتفظ بس بأخبار البورصة المصرية
                ok, reason = await filter_instance.is_relevant(full_text, title=full_text[:80])
                if not ok:
                    log.debug(f'  ↳ مرفوض من الفلتر ({channel}): {full_text[:50]}')
                    continue

                source_info = registry.get_telegram_display(channel)

                news_id = self.store.add(
                    source=source_info,
                    source_type='telegram',
                    body=full_text,
                    title=full_text[:80].replace('\n', ' '),
                    url=f"https://t.me/{channel}/{msg.id}",
                    published_at=msg.date.isoformat() if msg.date else '',
                )

                if news_id and image_paths:
                    self._save_images(news_id, image_paths)

                if news_id:
                    saved += 1

        except Exception as e:
            log.debug(f"  {channel}: {e}")
        return saved

    async def _resolve_entity(self, channel: str):
        """تحليل الكيان بعدة استراتيجيات (مثل GLMinvestment)"""
        try:
            return await self.client.get_entity(channel)
        except Exception:
            pass

        try:
            if channel.lstrip('-').isdigit():
                return await self.client.get_entity(int(channel))
        except Exception:
            pass

        try:
            if channel.startswith('@'):
                return await self.client.get_entity(channel)
        except Exception:
            pass

        log.warning(f"لم يتم العثور على القناة: {channel}")
        return None

    async def _download_media(self, msg, channel: str) -> str | None:
        """تنزيل صورة من الرسالة"""
        try:
            from telethon.tl.types import MessageMediaPhoto, MessageMediaWebPage

            has_photo = (
                msg.media and hasattr(msg.media, 'photo')
            ) or (
                msg.media and hasattr(msg.media, 'webpage') and msg.media.webpage
                and hasattr(msg.media.webpage, 'photo') and msg.media.webpage.photo
            )

            if not has_photo:
                return None

            timestamp = msg.date.strftime('%Y%m%d_%H%M%S') if msg.date else 'unknown'
            safe_channel = channel.replace('/', '_').replace('@', '')
            filename = f"{safe_channel}_{msg.id}_{timestamp}.jpg"
            filepath = self.images_dir / filename

            if filepath.exists():
                return str(filepath)

            downloaded = await self.client.download_media(msg, file=str(filepath))
            if downloaded and Path(downloaded).exists():
                log.info(f"  📷 تم تنزيل صورة: {filename}")
                return str(downloaded)
        except Exception as e:
            log.debug(f"خطأ تنزيل صورة: {e}")
        return None

    def _save_images(self, news_id: str, paths: list[str]):
        """حفظ مسارات الصور في البيانات الوصفية"""
        try:
            import json
            meta_path = self.images_dir / f"{news_id}_meta.json"
            meta_path.write_text(json.dumps({'paths': paths, 'news_id': news_id}), encoding='utf-8')
        except Exception as e:
            log.debug(f"خطأ حفظ بيانات الصور: {e}")
