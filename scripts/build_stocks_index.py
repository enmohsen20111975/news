"""
يبني config/stocks_index.json من قاعدة بيانات GLMinvestment.

الاستخدام:
    Windows: .\run.ps1 -Once أو python scripts/build_stocks_index.py

شغّل الـ script ده مرة واحدة أو كل ما تضاف أسهم جديدة في GLMinvestment.
"""
import sqlite3
import json
import os
from pathlib import Path

OUT_PATH = Path(__file__).resolve().parents[1] / 'config' / 'stocks_index.json'
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GLM_ROOT = PROJECT_ROOT.parent / 'GLMinvestment'
configured_stocks_db = os.getenv('GLM_STOCKS_DB', '').strip()
GLM_STOCKS_DB = Path(configured_stocks_db or DEFAULT_GLM_ROOT / 'data' / 'all' / 'stocks.db')

# aliases إضافية للأسهم المهمة — الـ DB فيها name_ar، لكن بعض الأسهم ليها أسماء شائعة مختلفة
EXTRA_ALIASES = {
    'COMI': ['cib', 'cib bank', 'التجاري الدولي', 'البنك التجاري الدولي', 'البنك التجاري', 'التجاري'],
    'HRHO': ['هيرمس', 'الهرم', 'الهرم للضيافة', 'إي إف جي هيرمس', 'هيرميس', 'efg', 'efg hermes'],
    'MFPC': ['موبكو', 'مصفاة مصر للبترول', 'مصفاة فلسطين', 'middle east oil'],
    'ABUK': ['أبو قير', 'أبو قير للأسمدة', 'أبو قير للأسمدة والكيماويات'],
    'SWDY': ['سويديك', 'السويدي', 'السويدي إليكتريك', 'elsewedy'],
    'EFIH': ['إي إف جي', 'المصري الخليجي', 'efg finance'],
    'ETEL': ['المصرية للاتصالات', 'we', 'اتصالات'],
    'EAST': ['الشرقية للدخان', 'الشرقية', 'eastern tobacco'],
    'TMGH': ['طلعت مصطفى', 'مجموعة طلعت مصطفى', 'talaat moustafa'],
    'ORWE': ['أوراسكوم', 'أوراسكوم للتنمية', 'orascom development'],
    'EFIN': ['المصري', 'البنك المصري الخليجي'],
    'OCDI': ['سوديك', 'السادس من أكتوبر للتنمية', 'october', 'six of october'],
    'PHAR': ['المصرية للأدوية', 'إيبيكو'],
    'SKPC': ['سيدي كرير', 'الأسكندرية للأسمدة', 'سيديك'],
    'AMER': ['المير', 'أمير'],
    'CCAP': ['كابيتال', 'القلعة', 'qalaa'],
    'HELI': ['هيلين', 'هليوبوليس'],
    'ISPH': ['الإسكندرية', 'alexandria pharma', 'alexandria'],
    'FWRY': ['فوري', 'fawry'],
    'SAIB': ['السعودي', 'البنك السعودي المصري', 'saib'],
    'GOCO': ['العبوات', 'goco', 'التعبئة'],
    'NILE': ['النيل', 'النيل للأدوية', 'nile pharma', 'nile'],
    'KORA': ['كورا', 'kora', 'كورا باور'],
    'EBSC': ['مصر بني سويف', 'بني سويف', 'السويس للأسمنت'],
    'NEDA': ['الإسكندرية للأدوية'],
    'EGCH': ['مصر للألومنيوم', 'الألومنيوم'],
    'AIH': ['العربية للأدوية', 'arab pharma'],
    'CIEB': ['كريستمارك', 'christmark'],
}


def main():
    if not GLM_STOCKS_DB.exists():
        print(f'GLM stocks DB not found at {GLM_STOCKS_DB}')
        return 1

    conn = sqlite3.connect(str(GLM_STOCKS_DB))
    cur = conn.cursor()
    cur.execute("""
        SELECT ticker, name, name_ar, sector, industry
        FROM stocks
        WHERE is_active = 1 AND (is_egx = 1 OR market = 'EGX' OR market = 'EG')
        ORDER BY ticker
    """)
    rows = cur.fetchall()
    conn.close()

    print(f'Loaded {len(rows)} active EGX stocks')

    hints: dict[str, str] = {}
    for ticker, name_en, name_ar, sector, industry in rows:
        if not ticker:
            continue
        tk = ticker.upper()
        hints[tk.lower()] = tk
        hints[tk] = tk
        if name_en:
            hints[name_en.lower().strip()] = tk
        if name_ar:
            hints[name_ar.strip()] = tk

    for ticker, aliases in EXTRA_ALIASES.items():
        for a in aliases:
            if a and a not in hints:
                hints[a] = ticker

    print(f'Index size: {len(hints)} hints')

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps({
            'stocks': [
                {'ticker': r[0], 'name_en': r[1], 'name_ar': r[2],
                 'sector': r[3], 'industry': r[4]}
                for r in rows
            ],
            'index': hints,
        }, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )
    print(f'Saved to {OUT_PATH}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())