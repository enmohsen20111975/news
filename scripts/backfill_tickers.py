#!/usr/bin/env python3
"""
Backfill Tickers Script — إعادة استخراج tickers على الأخبار الموجودة
====================================================================
توجيه المالك: "إصلاح استخراج وتخزين الـ tickers في الـ news agent"

السكربت ده بـ:
1. يقرأ كل الأخبار من news.db.
2. يـ re-extract tickers بالـ logic المحسّن (regex + Arabic patterns).
3. يـ update الـ tickers في الـ DB.
4. يطبع تقرير: كم خبر حصل على tickers جديدة.
"""
import sys
import os
import json
import sqlite3
from pathlib import Path

# Add news repo to path
NEWS_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(NEWS_ROOT))

# Add GLMinvestment vps-service to path (for EGX_TICKER_NAMES)
GLM_VPS = os.getenv('GLMINVESTMENT_PATH', str(NEWS_ROOT.parent / 'GLMinvestment' / 'vps-service'))
if Path(GLM_VPS).exists():
    sys.path.insert(0, str(GLM_VPS))


def main():
    print("=" * 80)
    print("Backfill Tickers — إعادة استخراج tickers على الأخبار الموجودة")
    print("=" * 80)

    db_path = NEWS_ROOT / 'data' / 'news.db'
    if not db_path.exists():
        print(f"❌ news.db not found at {db_path}")
        return

    # Import the enhanced extraction
    try:
        from analyzer.news_analyzer import _extract_tickers_enhanced, TICKER_HINTS
        print(f"✓ TICKER_HINTS loaded: {len(TICKER_HINTS)} hints")
    except Exception as e:
        print(f"❌ Failed to import _extract_tickers_enhanced: {e}")
        return

    # Connect to news.db
    c = sqlite3.connect(str(db_path))
    c.row_factory = sqlite3.Row

    # Get all news
    rows = c.execute('''
        SELECT id, title, body, source, tickers, importance, sentiment, status
        FROM news
        ORDER BY id
    ''').fetchall()

    print(f"\n📊 Total news in DB: {len(rows)}")
    analyzed = [r for r in rows if r['status'] == 'analyzed']
    print(f"   Analyzed: {len(analyzed)}")
    print(f"   Pending: {len(rows) - len(analyzed)}")

    # Re-extract tickers for each
    updated_count = 0
    news_with_tickers = 0
    ticker_stats = {}

    for r in rows:
        title = r['title'] or ''
        body = r['body'] or ''
        original_text = f"{title}\n{body}"
        clean_text = original_text
        text_lower = original_text.lower()

        # Extract with enhanced logic
        new_tickers = _extract_tickers_enhanced(original_text, clean_text, text_lower)

        # Parse old tickers
        old_tickers_str = r['tickers'] or '[]'
        try:
            old_tickers = json.loads(old_tickers_str) if old_tickers_str else []
        except Exception:
            old_tickers = []

        # If we found new tickers, update
        if new_tickers and new_tickers != old_tickers:
            new_tickers_json = json.dumps(new_tickers, ensure_ascii=False)
            c.execute('UPDATE news SET tickers = ? WHERE id = ?', (new_tickers_json, r['id']))
            updated_count += 1
            news_with_tickers += 1

            print(f"\n  ✅ {r['source']} | {title[:50]}...")
            print(f"     OLD tickers: {old_tickers}")
            print(f"     NEW tickers: {new_tickers}")

            # Update stats
            for t in new_tickers:
                ticker_stats[t] = ticker_stats.get(t, 0) + 1
        elif new_tickers:
            news_with_tickers += 1
            for t in new_tickers:
                ticker_stats[t] = ticker_stats.get(t, 0) + 1

    c.commit()

    # Summary
    print(f"\n{'='*80}")
    print(f"📊 BACKFILL SUMMARY")
    print(f"{'='*80}")
    print(f"  Total news processed: {len(rows)}")
    print(f"  News updated (new tickers found): {updated_count}")
    print(f"  News with tickers (after backfill): {news_with_tickers}")
    print(f"  News without tickers: {len(rows) - news_with_tickers}")

    if ticker_stats:
        print(f"\n📈 Ticker frequency (top 15):")
        for ticker, cnt in sorted(ticker_stats.items(), key=lambda x: -x[1])[:15]:
            print(f"  {ticker:10s}: {cnt} mentions")

    c.close()
    print(f"\n✓ Backfill complete — news.db updated")


if __name__ == '__main__':
    main()
