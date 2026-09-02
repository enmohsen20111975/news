"""
محلل رؤية محلي (Ollama Vision)
يفهم الصور وينتج وصفاً عربي/إنجليزي + استخراج نص OCR
النماذج المدعومة: llava, moondream, llama3.2-vision, bakllava
"""

import os
import json
import logging
import base64
from pathlib import Path

import httpx

log = logging.getLogger('VisionAnalyzer')


class VisionAnalyzer:
    """محلل صور محلي عبر Ollama Vision"""

    def __init__(self):
        self.ollama_url = os.getenv('OLLAMA_URL', 'http://localhost:11434')
        self.vision_model = os.getenv('OLLAMA_VISION_MODEL', '')
        self._available = None

    def is_available(self) -> bool:
        """تحقق من توفر نموذج رؤية"""
        if self._available is not None:
            return self._available
        if not self.vision_model:
            self._available = False
            return False
        try:
            with httpx.Client(timeout=5) as client:
                resp = client.get(f"{self.ollama_url}/api/tags")
                if resp.status_code == 200:
                    models = [m['name'] for m in resp.json().get('models', [])]
                    self._available = any(self.vision_model in m for m in models)
                    if not self._available:
                        log.warning(f"نموذج الرؤية {self.vision_model} غير متاح — تحقق من `ollama pull {self.vision_model}`")
                    return self._available
        except Exception as e:
            log.warning(f"لا يمكن الاتصال بـ Ollama: {e}")
        self._available = False
        return False

    def analyze_image(self, image_path: str, prompt: str = None) -> dict:
        """تحليل صورة واحدة"""
        if not self.is_available():
            return {'error': 'vision_model_unavailable', 'description': '', 'ocr_text': ''}

        if not Path(image_path).exists():
            return {'error': 'file_not_found', 'description': '', 'ocr_text': ''}

        prompt = prompt or (
            "أنت محلل مالي متخصص في بورصة EGX. "
            "حلّل هذه الصورة وأخرج JSON فقط:\n"
            "{\n"
            '  "description": "وصف مفصل للصورة بالعربية",\n'
            '  "ocr_text": "النص الظاهر في الصورة إن وجد",\n'
            '  "is_chart": true/false,\n'
            '  "is_screenshot": true/false,\n'
            '  "sentiment": "bullish/bearish/neutral",\n'
            '  "relevant_tickers": ["COMI", ...],\n'
            '  "confidence": 0-100\n'
            "}\n"
            "JSON فقط بدون أي نص إضافي."
        )

        try:
            image_b64 = self._encode_image(image_path)
            with httpx.Client(timeout=120) as client:
                resp = client.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self.vision_model,
                        "prompt": prompt,
                        "images": [image_b64],
                        "stream": False,
                        "options": {"temperature": 0.1, "num_predict": 400}
                    }
                )
                if resp.status_code != 200:
                    return {'error': f'http_{resp.status_code}', 'description': '', 'ocr_text': ''}

                raw = resp.json().get('response', '')
                return self._parse_response(raw)
        except Exception as e:
            log.error(f"خطأ تحليل الصورة {image_path}: {e}")
            return {'error': str(e), 'description': '', 'ocr_text': ''}

    def analyze_images_batch(self, image_paths: list[str]) -> dict:
        """تحليل مجموعة صور — ندمج النتائج"""
        if not image_paths:
            return {'description': '', 'ocr_text': '', 'sentiment': 'neutral', 'tickers': []}

        descriptions = []
        all_ocr = []
        sentiments = []
        tickers = set()

        for path in image_paths[:3]:  # حد أقصى 3 صور لسرعة الاستجابة
            result = self.analyze_image(path)
            if result.get('error'):
                continue
            if result.get('description'):
                descriptions.append(result['description'])
            if result.get('ocr_text'):
                all_ocr.append(result['ocr_text'])
            if result.get('sentiment') in ('bullish', 'bearish', 'neutral'):
                sentiments.append(result['sentiment'])
            for t in result.get('relevant_tickers', []):
                tickers.add(t.upper())

        sentiment = 'neutral'
        if sentiments.count('bullish') > sentiments.count('bearish'):
            sentiment = 'bullish'
        elif sentiments.count('bearish') > sentiments.count('bullish'):
            sentiment = 'bearish'

        return {
            'description': ' | '.join(descriptions),
            'ocr_text': '\n'.join(all_ocr),
            'sentiment': sentiment,
            'tickers': list(tickers),
        }

    def _encode_image(self, path: str) -> str:
        """ترميز الصورة كـ base64"""
        with open(path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')

    def _parse_response(self, raw: str) -> dict:
        """استخراج JSON من رد Ollama"""
        import re
        match = re.search(r'\{[\s\S]*\}', raw)
        if match:
            try:
                data = json.loads(match.group())
                data.setdefault('description', '')
                data.setdefault('ocr_text', '')
                data.setdefault('sentiment', 'neutral')
                data.setdefault('relevant_tickers', [])
                data.setdefault('is_chart', False)
                data.setdefault('is_screenshot', False)
                data.setdefault('confidence', 0)
                return data
            except json.JSONDecodeError:
                pass
        return {'description': raw[:300], 'ocr_text': '', 'sentiment': 'neutral', 'tickers': []}
