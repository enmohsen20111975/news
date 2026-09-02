"""
واجهة مراقبة بسيطة (CLI) لوكيل الأخبار
"""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
from data.news_store import NewsStore

console = Console()


def show_stats():
    store = NewsStore()
    s = store.stats()
    console.print(Panel(
        f"[bold]الإجمالي:[/bold] {s.get('total', 0)} خبر\n"
        f"[yellow]انتظار التحليل:[/yellow] {s.get('pending', 0)}\n"
        f"[cyan]تم تحليلها:[/cyan] {s.get('analyzed', 0)}\n"
        f"[green]تم الإرسال:[/green] {s.get('sent', 0)}",
        title="📊 إحصائيات وكيل الأخبار",
        border_style="blue"
    ))


def show_latest(limit: int = 10):
    store = NewsStore()
    rows = store.conn.execute('''
        SELECT title, source, importance, sentiment, impact_type, summary_ar, collected_at, status
        FROM news WHERE importance > 0
        ORDER BY importance DESC, collected_at DESC
        LIMIT ?
    ''', (limit,)).fetchall()

    table = Table(title="📰 أحدث الأخبار المحللة", box=box.ROUNDED, show_lines=True)
    table.add_column("العنوان", max_width=35)
    table.add_column("المصدر", max_width=15)
    table.add_column("أهمية", justify="center")
    table.add_column("مشاعر", justify="center")
    table.add_column("النوع", max_width=12)
    table.add_column("ملخص", max_width=30)
    table.add_column("الحالة", max_width=8)

    for r in rows:
        sentiment_color = {'bullish': 'green', 'bearish': 'red', 'neutral': 'yellow'}.get(r[3], 'white')
        importance_color = 'red' if r[2] >= 75 else 'yellow' if r[2] >= 50 else 'white'
        table.add_row(
            r[0][:35] if r[0] else '',
            r[1][:15] if r[1] else '',
            f"[{importance_color}]{r[2]}[/{importance_color}]",
            f"[{sentiment_color}]{r[3]}[/{sentiment_color}]",
            r[4] or '',
            r[5][:30] if r[5] else '',
            r[7] or '',
        )

    console.print(table)


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'latest':
        show_latest(int(sys.argv[2]) if len(sys.argv) > 2 else 10)
    else:
        show_stats()
        show_latest(5)
