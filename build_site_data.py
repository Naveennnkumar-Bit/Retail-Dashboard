"""
GO DESi | Retail P&L website - data builder.

Builds website/data/*.json for the static dashboard.

    python build_site_data.py                       # from retail_pnl.db if it exists, else from the tracker xlsx
    python build_site_data.py some_tracker.xlsx     # from a specific tracker file
    python build_site_data.py --db                  # force the database

The database (retail_pnl.db, see db.py) is the source of truth once created;
the Excel tracker is the import/export format.
"""
import os
import sys
from datetime import datetime

import pandas as pd

import aggregates
import db as dbm
import dump

HERE = os.path.dirname(os.path.abspath(__file__))
TRACKER = os.path.join(HERE, "P_L_tracker_retail_New.xlsx")
OUT = os.path.join(HERE, "website", "data")


def from_excel(path: str) -> pd.DataFrame:
    from python_calamine import CalamineWorkbook
    wb = CalamineWorkbook.from_path(path)
    rows = wb.get_sheet_by_name("Base").to_python()
    head = [str(c).strip() for c in rows[0]]
    raw = pd.DataFrame(rows[1:], columns=head)
    missing = [c for c in dump.BASE_COLS if c not in raw.columns]
    if missing:
        raise SystemExit("Base sheet is missing columns: " + ", ".join(missing))
    return dbm.normalize(raw[dump.BASE_COLS])


def main():
    args = [a for a in sys.argv[1:] if a != "--db"]
    force_db = "--db" in sys.argv[1:]
    src = args[0] if args else None
    out = args[1] if len(args) > 1 else OUT

    if src and not force_db:
        df = from_excel(src)
        meta_src, meta_mod = os.path.basename(src), datetime.fromtimestamp(os.path.getmtime(src)).strftime("%Y-%m-%d %H:%M")
    elif os.path.exists(dbm.DB_PATH) or force_db:
        conn = dbm.connect()
        df = dbm.fetch_df(conn)
        meta_src = "retail_pnl.db (imported from " + str(dbm.get_meta(conn, "source") or "?") + ")"
        meta_mod = dbm.get_meta(conn, "updated") or ""
        conn.close()
    else:
        df = from_excel(TRACKER)
        meta_src, meta_mod = os.path.basename(TRACKER), datetime.fromtimestamp(os.path.getmtime(TRACKER)).strftime("%Y-%m-%d %H:%M")

    print(f"Source: {meta_src} ({len(df):,} rows)")
    aggregates.build(df, out, source=meta_src, source_modified=meta_mod)
    print("Done. Redeploy the website/ folder to publish the new numbers.")


if __name__ == "__main__":
    main()
