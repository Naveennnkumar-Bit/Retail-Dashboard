"""
GO DESi | Retail P&L - web server.

Serves the dashboard AND lets you update it from the browser: drop the month's raw
files on the Upload page, check the calculated numbers, press "Add to dashboard".
The data lives in retail_pnl.db (see db.py); website/data/*.json is rebuilt from the
database whenever it changes.

Run it:

    python server.py                 # development, http://localhost:8173
    python server.py --port 9000
    waitress-serve --port=8173 server:app      # production

First time: python db.py --import P_L_tracker_retail_New.xlsx

Optional access control: set the environment variable DASH_TOKEN; the Upload page
will ask for it before it can change anything (viewing stays open - put the whole
site behind nginx auth / VPN if viewing must be private too).
"""
from __future__ import annotations

import io
import os
import secrets
import threading
import time

from flask import Flask, jsonify, request, send_file, send_from_directory

import aggregates
import db as dbm
import dump

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(HERE, "website")
DATA = os.path.join(SITE, "data")
TOKEN = os.environ.get("DASH_TOKEN", "")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024

_lock = threading.Lock()
_built_version = -1
_previews: dict = {}  # token -> {"at": ts, "sales": (rows, rep), "costs": {...}, "names": [...]}

LABELS = {"sales": "ERP sales export", "mapping": "Primary Customer Mapping", "trans": "Trans % sheet",
          "salary": "Salary", "expenses": "Expenses", "incentive": "Incentive", "dbclaim": "DB Claim"}


def conn():
    c = dbm.connect()
    return c


def ensure_data():
    """Rebuild website/data from the DB when its version changed."""
    global _built_version
    with _lock:
        c = conn()
        try:
            v = dbm.version(c)
            if v != _built_version or not os.path.exists(os.path.join(DATA, "meta.json")):
                df = dbm.fetch_df(c)
                src = "retail_pnl.db (imported from " + str(dbm.get_meta(c, "source") or "?") + ")"
                aggregates.build(df, DATA, source=src, source_modified=dbm.get_meta(c, "updated") or "", quiet=True)
                _built_version = v
        finally:
            c.close()


def guard():
    """None if allowed, else an error response. Only mutating calls are guarded."""
    if TOKEN and request.headers.get("X-Dash-Token", "") != TOKEN:
        return jsonify({"error": "This server needs the access token. Enter it on the Upload page."}), 401
    return None


# ---------------------------------------------------------------- static site
@app.get("/")
def index():
    ensure_data()
    return send_from_directory(SITE, "index.html")


@app.get("/<path:path>")
def static_files(path):
    if path.startswith("data/"):
        ensure_data()
    return send_from_directory(SITE, path)


# ---------------------------------------------------------------- api
@app.get("/api/status")
def status():
    c = conn()
    try:
        s = dbm.stats(c)
        return jsonify({
            "db": True, "version": s["version"], "updated": s["updated"], "source": s["source"],
            "rows": {k: n for k, n in s["rows"]}, "needs_token": bool(TOKEN),
            "history": [{"at": at, "what": what, "months": months, "added": na, "replaced": nr}
                        for at, what, months, na, nr in s["uploads"]],
        })
    finally:
        c.close()


@app.get("/api/export")
def export():
    c = conn()
    try:
        data = dbm.export_xlsx(c)
    finally:
        c.close()
    return send_file(io.BytesIO(data), as_attachment=True, download_name="P_L_tracker_retail_New.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.post("/api/upload")
def upload():
    err = guard()
    if err:
        return err
    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "No files received."}), 400

    found, file_report, errors = {}, [], []
    blobs = []
    for f in files:
        data = f.read()
        name = f.filename or "file"
        blobs.append((name, data))
        try:
            kinds = dump.detect(data, name)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name}: could not be opened ({e})")
            file_report.append({"name": name, "kinds": [], "error": str(e)})
            continue
        file_report.append({"name": name, "kinds": [LABELS[k] for k in kinds]})
        if not kinds:
            errors.append(f"{name}: not recognised. None of its sheets has the headings of a sales export, "
                          "Salary, Expenses, Incentive, DB Claim, Customer Mapping or Trans % sheet.")
        for k in kinds:
            found.setdefault(k, []).append((name, data, len(kinds)))

    chosen = {k: min(c, key=lambda x: x[2]) for k, c in found.items()}
    rd = lambda kind, fn: fn(chosen[kind][1], chosen[kind][0]) if kind in chosen else None
    out = {"files": file_report, "errors": errors, "sales": None, "costs": None}

    c = conn()
    try:
        base_raw = dbm.denormalize(dbm.fetch_df(c))

        sales = mapping = trans = None
        try:
            sales = rd("sales", dump.read_sales)
            mapping = rd("mapping", dump.read_mapping)
            trans = rd("trans", dump.read_trans)
        except Exception as e:  # noqa: BLE001
            errors.append(str(e))

        token = secrets.token_urlsafe(12)
        stash = {"at": time.time(), "names": [n for n, _ in blobs]}

        if sales is not None:
            rate_tab = dump.rate_table(sales, trans)
            rows, rep = dump.build_sales(sales, mapping, None if mapping is not None else base_raw,
                                         dump.rates_from_table(rate_tab))
            stash["sales"] = (rows, rep)
            out["sales"] = {
                "rows": rep["rows"],
                "months": [f"{dump.MONTHS[m]} {y}" for y, m in rep["months"]],
                "revenue": rep["revenue"], "cogs": rep["cogs"], "transport": rep["transport"],
                "opex": rep["revenue"] * dump.OPEX_PCT,
                "replaced": dump.replaced_count(base_raw, "sales", rep["months"]),
                "unmapped": rep["unmapped"][:20], "unmapped_more": max(0, len(rep["unmapped"]) - 20),
                "bad_date": rep["bad_date"],
                "rate_misses": rate_tab[rate_tab["From sheet"] == "no"][["RSM", "Month", "Year"]].astype(str).values.tolist(),
                "missing_optional": rep["missing_optional"],
            }

        cost_dfs = {}
        for k, fn in [("salary", dump.read_salary), ("expenses", dump.read_expenses),
                      ("incentive", dump.read_incentive), ("dbclaim", dump.read_dbclaim)]:
            if k in chosen:
                try:
                    cost_dfs[k] = fn(chosen[k][1], chosen[k][0])
                except Exception as e:  # noqa: BLE001
                    errors.append(f"{LABELS[k]}: {e}")
        if cost_dfs:
            pool = sorted({p for df in cost_dfs.values() for p in dump.periods_in(df)})
            months_out = []
            for ym in pool:
                rows, rep = dump.build_costs(ym[0], ym[1], cost_dfs.get("salary"), cost_dfs.get("expenses"),
                                             cost_dfs.get("incentive"), cost_dfs.get("dbclaim"), dump.SPLIT_DEFAULT)
                t = rep["totals"]
                months_out.append({
                    "label": f"{dump.MONTHS[ym[1]]} {ym[0]}", "rows": rep["rows"],
                    "salary": t["RSM salary"] + t["ASM salary"] + t["SO salary"],
                    "travel": t["RSM  Travel"] + t["ASM Travel"] + t["SO Travel"],
                    "incentive": t["RSM  Incentive"] + t["ASM Incentive"] + t["SO Incentive"],
                    "db_claim": t["DB Claim"],
                    "replaced": dump.replaced_count(base_raw, "cost", [ym]),
                    "unknown": [f'{sheet}: {n} row(s) with position "{pos}"' for (sheet, pos), n in rep["unknown"].items()],
                })
            stash["cost_dfs"] = cost_dfs
            stash["cost_pool"] = pool
            out["costs"] = {"months": months_out, "default": len(pool) - 1 if pool else None,
                            "has_salary": "salary" in cost_dfs}

        if stash.get("sales") or cost_dfs:
            # keep at most 8 previews, drop stale ones
            now = time.time()
            for k in [k for k, v in _previews.items() if now - v["at"] > 1800]:
                _previews.pop(k, None)
            while len(_previews) >= 8:
                _previews.pop(next(iter(_previews)), None)
            _previews[token] = stash
            out["token"] = token
        out["errors"] = errors
        return jsonify(out)
    finally:
        c.close()


@app.post("/api/commit")
def commit():
    err = guard()
    if err:
        return err
    body = request.get_json(silent=True) or {}
    stash = _previews.get(body.get("token", ""))
    if not stash:
        return jsonify({"error": "This preview has expired. Upload the files again."}), 410

    done = []
    c = conn()
    try:
        source = ", ".join(stash.get("names", []))[:200]
        if body.get("add_sales", True) and stash.get("sales"):
            rows, rep = stash["sales"]
            added, replaced = dbm.replace_months(c, "sales", rep["months"], rows, source)
            done.append(f"Sales: {added:,} lines added for " +
                        ", ".join(f"{dump.MONTHS[m]} {y}" for y, m in rep["months"]) +
                        (f" (replaced {replaced:,})" if replaced else ""))
        if body.get("add_costs", True) and stash.get("cost_dfs"):
            pool = stash["cost_pool"]
            idx = body.get("cost_month_index")
            ym = pool[idx] if isinstance(idx, int) and 0 <= idx < len(pool) else (pool[-1] if pool else None)
            if ym:
                split = dump.SPLIT_DEFAULT if body.get("split", True) else None
                d = stash["cost_dfs"]
                rows, rep = dump.build_costs(ym[0], ym[1], d.get("salary"), d.get("expenses"),
                                             d.get("incentive"), d.get("dbclaim"), split)
                added, replaced = dbm.replace_months(c, "cost", [ym], rows, source)
                done.append(f"Field costs: {added:,} lines added for {dump.MONTHS[ym[1]]} {ym[0]}" +
                            (f" (replaced {replaced:,})" if replaced else ""))
    finally:
        c.close()
    _previews.pop(body.get("token", ""), None)
    ensure_data()  # rebuild the JSONs now so the next page load is fresh

    # push the changed months to Supabase, when it is set up
    try:
        import supa_sync
        if supa_sync.configured():
            if body.get("add_sales", True) and stash.get("sales"):
                done.append(supa_sync.sync_months("sales", stash["sales"][1]["months"], source))
            if body.get("add_costs", True) and stash.get("cost_dfs") and stash.get("cost_pool"):
                idx = body.get("cost_month_index")
                ym = stash["cost_pool"][idx] if isinstance(idx, int) and 0 <= idx < len(stash["cost_pool"]) else stash["cost_pool"][-1]
                done.append(supa_sync.sync_months("cost", [ym], source))
    except Exception as e:  # noqa: BLE001
        done.append(f"Supabase sync failed ({e}) - the local data is updated; run: python supa_sync.py --full")
    return jsonify({"done": done})


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8173)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    if not os.path.exists(dbm.DB_PATH):
        print("No database yet. Run first:  python db.py --import P_L_tracker_retail_New.xlsx")
        raise SystemExit(1)
    ensure_data()
    print(f"Dashboard on http://{args.host}:{args.port}  (Ctrl+C to stop)")
    from waitress import serve
    serve(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
