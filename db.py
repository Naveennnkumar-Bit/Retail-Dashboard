"""
GO DESi | Retail P&L - the database.

SQLite, one file: retail_pnl.db. The `base` table mirrors the tracker's Base sheet,
one row per invoice line (kind='sales') or per employee-cost line (kind='cost').
The Excel tracker becomes an import/export format; the database is the source of truth.

Command line:

    python db.py --import P_L_tracker_retail_New.xlsx   # load the tracker into the DB (replaces everything)
    python db.py --export out.xlsx                      # write the DB back out as a tracker workbook
    python db.py --stats                                # what's inside

Programmatic: connect(), fetch_df(), replace_months(), version().
"""
from __future__ import annotations

import argparse
import os
import sqlite3
from datetime import datetime

import numpy as np
import pandas as pd

import dump

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "retail_pnl.db")

# tracker header -> db column (same mapping the dashboards use)
RENAME = {
    "Date": "date", "Month": "month", "Year": "year", "Customer Name": "customer", "Sub-Channel": "sub_channel",
    "Customer Group": "cust_group", "Customer City": "city", "Customer State": "state", "Customer Zone": "zone",
    "FA RSM": "rsm", "ASM Name": "asm", "Item Name": "sku", "L0 - Parent Category": "l0", "L1 - Parent Category": "l1",
    "L2 - Parent Category": "l2", "L3 - Sub-Category": "l3", "Packaging Type": "pack", "Type": "type", "Returns": "is_return",
    "Qty Sold": "qty", "Revenue": "revenue", "COGS Total": "cogs", "Transportaion Cost": "transport", "Operatinal Exp": "opex",
    "RSM salary": "rsm_salary", "RSM  Travel": "rsm_travel", "RSM  Incentive": "rsm_incentive",
    "ASM salary": "asm_salary", "ASM Travel": "asm_travel", "ASM Incentive": "asm_incentive", "DB Claim": "db_claim",
    "SO salary": "so_salary", "SO Incentive": "so_incentive", "SO Travel": "so_travel", "Invoice Number": "invoice",
    "Keka Name": "employee", "Part of Scheme SKU List?": "scheme",
}
BACK = {v: k for k, v in RENAME.items()}
NUM_COLS = ["qty", "revenue", "cogs", "transport", "opex", "rsm_salary", "rsm_travel", "rsm_incentive",
            "asm_salary", "asm_travel", "asm_incentive", "db_claim", "so_salary", "so_incentive", "so_travel"]
TEXT_COLS = [c for c in RENAME.values() if c not in NUM_COLS and c not in ("year",)]
ALL_COLS = list(RENAME.values()) + ["kind", "mnum"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS base (
    id INTEGER PRIMARY KEY,
    {text_cols},
    year INTEGER,
    mnum INTEGER,
    {num_cols},
    kind TEXT NOT NULL CHECK (kind IN ('sales', 'cost'))
);
CREATE INDEX IF NOT EXISTS ix_base_period ON base (year, mnum, kind);
CREATE INDEX IF NOT EXISTS ix_base_rsm ON base (rsm);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS uploads (
    id INTEGER PRIMARY KEY,
    at TEXT NOT NULL,
    what TEXT NOT NULL,
    months TEXT NOT NULL,
    rows_added INTEGER NOT NULL,
    rows_replaced INTEGER NOT NULL,
    source TEXT
);
""".format(
    text_cols=",\n    ".join(f"{c} TEXT" for c in TEXT_COLS),
    num_cols=",\n    ".join(f"{c} REAL" for c in NUM_COLS),
)


def connect(path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def _bump(conn, n_added=0, n_replaced=0, what="", months="", source=""):
    v = int(get_meta(conn, "version") or 0) + 1
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('version', ?)", (str(v),))
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('updated', ?)", (datetime.now().strftime("%Y-%m-%d %H:%M"),))
    if what:
        conn.execute("INSERT INTO uploads (at, what, months, rows_added, rows_replaced, source) VALUES (?,?,?,?,?,?)",
                     (datetime.now().strftime("%Y-%m-%d %H:%M"), what, months, n_added, n_replaced, source))


def get_meta(conn, key: str):
    r = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return r[0] if r else None


def version(conn) -> int:
    return int(get_meta(conn, "version") or 0)


# ---------------------------------------------------------------- frames in and out
def normalize(base_cols_df: pd.DataFrame) -> pd.DataFrame:
    """A BASE_COLS frame (tracker spelling) -> db columns, typed, with kind and mnum."""
    df = base_cols_df.rename(columns=RENAME).copy()
    df = df[df["month"].astype(str).str[:3].isin(dump.MONTHS)].copy()
    for c in NUM_COLS:
        df[c] = pd.to_numeric(df[c].replace("", np.nan), errors="coerce")
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype(int)
    df["mnum"] = df["month"].astype(str).str[:3].str.title().map({m: i + 1 for i, m in enumerate(dump.MONTHS)})
    def iso(v):
        if v in ("", None) or (isinstance(v, float) and np.isnan(v)):
            return ""
        t = pd.to_datetime(v, errors="coerce", dayfirst=isinstance(v, str) and "-" in str(v)[:3])
        return "" if pd.isna(t) else t.strftime("%Y-%m-%d")
    parsed = dump.parse_dates(df["date"])
    df["date"] = [p.strftime("%Y-%m-%d") if pd.notna(p) else "" for p in parsed]
    df["kind"] = np.where(df["date"].astype(str).str.len() > 0, "sales", "cost")
    for c in TEXT_COLS:
        df[c] = df[c].astype(object).where(df[c].notna(), "").astype(str).replace("nan", "")
    return df[ALL_COLS]


def denormalize(df: pd.DataFrame) -> pd.DataFrame:
    """db rows -> a BASE_COLS frame the dump helpers understand."""
    out = df.rename(columns=BACK).copy()
    for c in dump.BASE_COLS:
        if c not in out.columns:
            out[c] = ""
    out = out[dump.BASE_COLS]
    num_back = [BACK[c] for c in NUM_COLS]
    for c in num_back:
        out[c] = out[c].where(out[c].notna(), "")
    return out.astype(object).fillna("")


def fetch_df(conn) -> pd.DataFrame:
    return pd.read_sql_query(f"SELECT {', '.join(ALL_COLS)} FROM base", conn)


def import_excel(conn, path: str):
    """Replace the whole database with the tracker's Base sheet."""
    from python_calamine import CalamineWorkbook
    wb = CalamineWorkbook.from_path(path)
    rows = wb.get_sheet_by_name("Base").to_python()
    head = [str(c).strip() for c in rows[0]]
    raw = pd.DataFrame(rows[1:], columns=head)
    missing = [c for c in dump.BASE_COLS if c not in raw.columns]
    if missing:
        raise SystemExit("Base sheet is missing columns: " + ", ".join(missing))
    df = normalize(raw[dump.BASE_COLS])
    with conn:
        conn.execute("DELETE FROM base")
        df.to_sql("base", conn, if_exists="append", index=False)
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('source', ?)", (os.path.basename(path),))
        _bump(conn, len(df), 0, "import", "all", os.path.basename(path))
    return len(df)


def replace_months(conn, kind: str, months: list, base_cols_rows: pd.DataFrame, source: str = "") -> tuple:
    """Replace all rows of `kind` for the given (year, month-index-0) pairs with the new rows. Returns (added, replaced)."""
    df = normalize(base_cols_rows)
    with conn:
        replaced = 0
        for y, mi in months:
            cur = conn.execute("DELETE FROM base WHERE kind = ? AND year = ? AND mnum = ?", (kind, int(y), int(mi) + 1))
            replaced += cur.rowcount
        df.to_sql("base", conn, if_exists="append", index=False)
        label = ", ".join(f"{dump.MONTHS[mi]} {y}" for y, mi in months)
        _bump(conn, len(df), replaced, kind, label, source)
    return len(df), replaced


def export_xlsx(conn) -> bytes:
    return dump.to_base_xlsx(denormalize(fetch_df(conn)))


def stats(conn) -> dict:
    q = lambda sql: conn.execute(sql).fetchall()
    months = q("SELECT year, mnum, kind, COUNT(*) FROM base GROUP BY year, mnum, kind ORDER BY year, mnum")
    return {
        "rows": q("SELECT kind, COUNT(*) FROM base GROUP BY kind"),
        "span": q("SELECT MIN(year*100+mnum), MAX(year*100+mnum) FROM base"),
        "months": len({(y, m) for y, m, _, _ in months}),
        "source": get_meta(conn, "source"),
        "updated": get_meta(conn, "updated"),
        "version": version(conn),
        "uploads": q("SELECT at, what, months, rows_added, rows_replaced FROM uploads ORDER BY id DESC LIMIT 10"),
    }


def main():
    ap = argparse.ArgumentParser(description="Retail P&L database")
    ap.add_argument("--db", default=DB_PATH)
    ap.add_argument("--import", dest="imp", metavar="XLSX", help="replace the DB with this tracker's Base sheet")
    ap.add_argument("--export", metavar="XLSX", help="write the DB out as a tracker workbook")
    ap.add_argument("--stats", action="store_true")
    args = ap.parse_args()
    conn = connect(args.db)
    if args.imp:
        n = import_excel(conn, args.imp)
        print(f"Imported {n:,} rows from {args.imp} into {args.db}")
    if args.export:
        data = export_xlsx(conn)
        with open(args.export, "wb") as fh:
            fh.write(data)
        print(f"Wrote {args.export} ({len(data)/1e6:.1f} MB)")
    if args.stats or not (args.imp or args.export):
        s = stats(conn)
        print(f"Database: {args.db}")
        print(f"  rows: " + ", ".join(f"{k}={n:,}" for k, n in s["rows"]) + f" | months: {s['months']}")
        print(f"  imported from: {s['source']} | last change: {s['updated']} | version: {s['version']}")
        if s["uploads"]:
            print("  recent changes:")
            for at, what, months, na, nr in s["uploads"]:
                print(f"    {at}  {what:7s} {months}  +{na:,} rows, replaced {nr:,}")


if __name__ == "__main__":
    main()
