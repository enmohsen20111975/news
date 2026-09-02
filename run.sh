#!/bin/bash
# ================================================
# تثبيت وتشغيل وكيل الأخبار المحلي
# ================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── إنشاء البيئة الافتراضية ───────────────────────
echo "🔧 إنشاء بيئة Python..."
python3 -m venv .venv 2>/dev/null || true
source .venv/bin/activate

# ── تثبيت المتطلبات ───────────────────────────────
echo "📦 تثبيت المكتبات..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

# ── التحقق من .env ────────────────────────────────
if [ ! -f ".env" ]; then
    echo "⚠️  ملف .env مش موجود — بنعمل نسخة من .env.example"
    cp .env.example .env
    echo "✏️  افتح .env وعدّل الإعدادات، ثم شغّل run.sh مجدداً"
    exit 1
fi

# ── التحقق من Ollama ─────────────────────────────
echo "🤖 التحقق من Ollama..."
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "⚠️  Ollama مش شغال — بنشغّله..."
    ollama serve &
    sleep 3
fi

echo "✅ كل شيء جاهز!"
echo "🚀 تشغيل وكيل الأخبار..."
python3 main.py "$@"
