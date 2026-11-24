"""
GO DESi | Retail P&L - push the local database up to Supabase.

The website (on Cloudflare) reads from Supabase; this script keeps Supabase equal
to the local retail_pnl.db. add_month.py and server.py call it automatically after
every change, and it can be run by hand:

    python supa_sync.py --check        # is Supabase reachable and the schema in place?
    python supa_sync.py --full         # wipe Supabase and push everything (first time)
    python supa_sync.py                # same as --full

Credentials (the SERVICE key, never the anon key - it must stay off the website):
    either environment variables  SUPABASE_URL  and  SUPABASE_SERVICE_KEY
    or a file supabase_creds.json next to this script:
        {"url": "https://xxxx.supabase.co", "service_key": "eyJ..."}
    Keep that file out of GitHub and out of the website/ folder.
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime

import db as dbm
import dump

HERE = os.path.dirname(os.path.abspath(__file__))
CREDS_FILE = os.path.join(HERE, "supabase_creds.json")
CHUNK = 1000


def _creds():
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not (url and key) and os.path.exists(CREDS_FILE):
        try:
            with open(CREDS_FILE, encoding="utf-8") as fh:
                j = json.load(fh)
            url, key = url or j.get("url", ""), key or j.get("service_key", "")
        except Exception:  # noqa: BLE001
            pass
    return url.rstrip("/"), key


def configured() -> bool:
    url, key = _creds()
    return bool(url and key)


def client():
    from supabase import create_client
    url, key = _creds()
    if not (url and key):
        raise SystemExit("Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_KEY, "
                         "or create supabase_creds.json (see the top of supa_sync.py).")
    return create_client(url, key)


def _rows_for(df):
    """SQLite rows -> JSON-safe dicts in the Supabase column layout."""
    cols = [c for c in dbm.ALL_COLS]
    out = []
    for r in df[cols].itertuples(index=False):
        d = {}
        for c, v in zip(cols, r):
            if isinstance(v, float) and math.isnan(v):
                v = None
            if c in ("year", "mnum") and v is not None:
                v = int(v)
            d[c] = v
        out.append(d)
    return out


def _insert(cl, rows, label=""):
    for i in range(0, len(rows), CHUNK):
        cl.table("base").insert(rows[i:i + CHUNK]).execute()
        print(f"    {label}{min(i + CHUNK, len(rows)):,} of {len(rows):,} rows sent", end="\r")
    if rows:
        print()


def _touch_meta(cl, source=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    cl.table("meta").upsert({"key": "updated", "value": now}).execute()
    if source:
        cl.table("meta").upsert({"key": "source", "value": source}).execute()


def full_sync():
    """Wipe Supabase's base table and push everything from retail_pnl.db."""
    conn = dbm.connect()
    df = dbm.fetch_df(conn)
    src = dbm.get_meta(conn, "source") or "retail_pnl.db"
    conn.close()
    cl = client()
    print(f"Pushing {len(df):,} rows to Supabase (full replace)…")
    cl.rpc("truncate_base").execute()
    _insert(cl, _rows_for(df))
    _touch_meta(cl, src)
    cl.table("uploads").insert({"what": "full sync", "months": "all", "rows_added": int(len(df)),
                                "rows_replaced": 0, "source": src}).execute()
    print("Done. The website now reads these rows.")


def sync_months(kind: str, months: list, source: str = ""):
    """Replace one kind's rows for the given (year, month-index-0) pairs on Supabase,
    taking the fresh rows from the local database. Returns a one-line summary."""
    conn = dbm.connect()
    df = dbm.fetch_df(conn)
    conn.close()
    cl = client()
    sent = 0
    for y, mi in months:
        sub = df[(df.kind == kind) & (df.year == int(y)) & (df.mnum == int(mi) + 1)]
        cl.table("base").delete().eq("kind", kind).eq("year", int(y)).eq("mnum", int(mi) + 1).execute()
        _insert(cl, _rows_for(sub), f"{dump.MONTHS[mi]} {y}: ")
        sent += len(sub)
    _touch_meta(cl)
    label = ", ".join(f"{dump.MONTHS[mi]} {y}" for y, mi in months)
    cl.table("uploads").insert({"what": kind, "months": label, "rows_added": sent,
                                "rows_replaced": 0, "source": source[:200]}).execute()
    return f"Supabase: {sent:,} {kind} rows for {label}"


def check():
    cl = client()
    url, _ = _creds()
    print(f"Supabase: {url}")
    meta = cl.rpc("dash_meta").execute().data
    print(f"  schema: OK | rows on Supabase: {meta.get('base_rows', 0):,} "
          f"({meta.get('sales_rows', 0):,} sales, {meta.get('cost_rows', 0):,} cost)")
    conn = dbm.connect()
    local = conn.execute("SELECT COUNT(*) FROM base").fetchone()[0]
    conn.close()
    print(f"  local retail_pnl.db: {local:,} rows" +
          ("  -> run  python supa_sync.py --full  to push" if local != meta.get("base_rows", 0) else "  (in sync)"))


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Sync retail_pnl.db to Supabase")
    ap.add_argument("--check", action="store_true", help="test the connection and compare row counts")
    ap.add_argument("--full", action="store_true", help="wipe Supabase and push everything")
    a = ap.parse_args()
    if a.check:
        check()
    else:
        full_sync()
