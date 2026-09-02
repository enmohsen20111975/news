import os
import tempfile
import unittest
from pathlib import Path

import data.news_store as news_store_module
from data.news_store import NewsStore


class NewsStoreMediaPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / 'news.db'
        news_store_module.DB_PATH = self.db_path

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_add_and_save_analysis_persist_images_and_details(self):
        store = NewsStore()
        news_id = store.add(
            source='test_source',
            source_type='telegram',
            body='خبر كامل مع تفاصيل وتفاصيل إضافية',
            title='عنوان خبر طويل',
            url='https://example.com/news/1',
            published_at='2026-09-02T10:00:00',
            image_urls='["https://example.com/image.jpg"]',
        )

        self.assertIsNotNone(news_id)
        row = store.conn.execute(
            'SELECT image_urls, title, body, source FROM news WHERE id = ?',
            (news_id,),
        ).fetchone()
        self.assertEqual(row['image_urls'], '["https://example.com/image.jpg"]')

        store.save_analysis(news_id, {
            'tickers': ['COMI'],
            'importance': 92,
            'sentiment': 'bullish',
            'impact_type': 'earnings',
            'summary_ar': 'ملخص كامل يشرح التأثير على الشركة.',
            'summary_en': 'Detailed summary describing the impact on the company.',
            'raw_analysis': {'reasoning': 'full explanation'},
            'image_paths': ['/tmp/a.jpg'],
            'ocr_text': 'نص مستخرج من الصورة',
        })

        saved = store.conn.execute(
            'SELECT image_paths, summary_ar, summary_en, ocr_text, raw_analysis FROM news WHERE id = ?',
            (news_id,),
        ).fetchone()
        self.assertEqual(saved['summary_ar'], 'ملخص كامل يشرح التأثير على الشركة.')
        self.assertEqual(saved['ocr_text'], 'نص مستخرج من الصورة')
        self.assertIn('reasoning', saved['raw_analysis'])


if __name__ == '__main__':
    unittest.main()
