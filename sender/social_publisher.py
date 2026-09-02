"""
ناشر الأخبار على منصات التواصل الاجتماعي
حالياً: Telegram فقط
"""

import os
import json
import logging
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime

log = logging.getLogger('SocialPublisher')


class SocialPublisher:
    """ينشر الأخبار على منصات التواصل بعد التحليل"""

    def __init__(self):
        self.telegram_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
        self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID', '')

    async def publish(self, news: dict, platforms: list[str] = None) -> dict:
        """نشر خبر على المنصات المحددة"""
        if platforms is None:
            platforms = ['telegram']

        results = {}
        title = news.get('title', '') or news.get('summary_ar', 'خبر جديد')
        body = news.get('body', '') or news.get('summary_ar', '')
        url = news.get('url', '')
        image_paths = news.get('image_paths', [])
        if isinstance(image_paths, str):
            try:
                image_paths = json.loads(image_paths)
            except Exception:
                image_paths = []
        image_urls = news.get('image_urls', [])
        if isinstance(image_urls, str):
            try:
                image_urls = json.loads(image_urls)
            except Exception:
                image_urls = []

        message = f"📰 {title}\n\n{body[:200]}\n\n🔗 {url}" if url else f"📰 {title}\n\n{body[:200]}"

        for platform in platforms:
            try:
                if platform == 'telegram':
                    result = await self._publish_telegram(message, image_paths, image_urls)
                    results['telegram'] = result
                else:
                    results[platform] = {'skipped': True, 'reason': 'not_implemented'}
            except Exception as e:
                log.error(f"خطأ النشر على {platform}: {e}")
                results[platform] = {'error': str(e)}

        return results

    async def _publish_telegram(self, message: str, image_paths: list, image_urls: list) -> dict:
        """النشر على Telegram"""
        if not self.telegram_token or not self.telegram_chat_id:
            return {'skipped': True, 'reason': 'missing_credentials'}

        image_sent = False
        for img in (image_paths + image_urls)[:1]:
            try:
                if img.startswith('http'):
                    sent = self._telegram_send_photo_url(self.telegram_token, self.telegram_chat_id, img, message)
                else:
                    sent = self._telegram_send_photo_file(self.telegram_token, self.telegram_chat_id, img, message)
                if sent:
                    image_sent = True
                    break
            except Exception as e:
                log.debug(f"فشل إرسال صورة Telegram: {e}")

        if not image_sent:
            sent = self._telegram_send_message(self.telegram_token, self.telegram_chat_id, message)
            if not sent:
                return {'error': 'failed_to_send'}

        return {'platform': 'telegram', 'status': 'sent'}

    def _telegram_send_message(self, token: str, chat_id: str, text: str) -> bool:
        """إرسال رسالة نصية لـ Telegram"""
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode({
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML',
        }).encode()
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/x-www-form-urlencoded'})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except Exception:
            return False

    def _telegram_send_photo_url(self, token: str, chat_id: str, photo_url: str, caption: str) -> bool:
        """إرسال صورة عبر URL لـ Telegram"""
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        data = urllib.parse.urlencode({
            'chat_id': chat_id,
            'photo': photo_url,
            'caption': caption[:1024],
            'parse_mode': 'HTML',
        }).encode()
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/x-www-form-urlencoded'})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status == 200
        except Exception:
            return False

    def _telegram_send_photo_file(self, token: str, chat_id: str, file_path: str, caption: str) -> bool:
        """إرسال صورة من ملف لـ Telegram"""
        try:
            import mimetypes
            boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
            with open(file_path, 'rb') as f:
                file_data = f.read()
            filename = os.path.basename(file_path)
            mime_type = mimetypes.guess_type(file_path)[0] or 'application/octet-stream'

            body = (
                f'--{boundary}\r\n'
                f'Content-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'
                f'--{boundary}\r\n'
                f'Content-Disposition: form-data; name="caption"\r\n\r\n{caption[:1024]}\r\n'
                f'--{boundary}\r\n'
                f'Content-Disposition: form-data; name="photo"; filename="{filename}"\r\n'
                f'Content-Type: {mime_type}\r\n\r\n'
            ).encode() + file_data + f'\r\n--{boundary}--\r\n'.encode()

            req = urllib.request.Request(
                f"https://api.telegram.org/bot{token}/sendPhoto",
                data=body,
                headers={'Content-Type': f'multipart/form-data; boundary={boundary}'},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.status == 200
        except Exception:
            return False
