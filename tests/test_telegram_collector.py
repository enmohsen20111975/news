import asyncio
import os
import sys
import types
import unittest
from unittest.mock import patch

from collectors.telegram_collector import TelegramCollector


class DummyTelegramClient:
    def __init__(self, session_path, api_id, api_hash):
        self.session_path = session_path
        self.api_id = api_id
        self.api_hash = api_hash
        self.kwargs = None

    async def start(self, **kwargs):
        self.kwargs = kwargs
        return True


class TelegramCollectorBotTokenTests(unittest.TestCase):
    def test_init_client_uses_bot_token(self):
        os.environ['TELEGRAM_API_ID'] = '12345'
        os.environ['TELEGRAM_API_HASH'] = 'hash123'
        os.environ['TELEGRAM_BOT_TOKEN'] = 'test_bot_token'

        fake_telethon = types.SimpleNamespace(TelegramClient=DummyTelegramClient)
        with patch.dict(sys.modules, {'telethon': fake_telethon}):
            collector = TelegramCollector(store=object())
            result = asyncio.run(collector._init_client())

        self.assertTrue(result)
        self.assertEqual(collector.client.kwargs, {'bot_token': 'test_bot_token'})


if __name__ == '__main__':
    unittest.main()
