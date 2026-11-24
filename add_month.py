"""
GO DESi | Retail P&L - add a month from the raw files.

Drop the month's files into the incoming/ folder (any mix of):

    ERP item-wise sales export      (xlsx or csv)
    Primary Customer Mapping        (optional - otherwise RSM/ASM come from the data already in Base)
    Trans % sheet                   (optional - otherwise transport defaults to 4% and a warning is printed)
    Salary / Expenses / Incentive / DB Claim sheets

then run:

    python add_month.py                 # read incoming/, update the tracker, rebuild website data
    python add_month.py --dry-run       # show what would happen, change nothing
    python add_month.py path\to\folder  # read a different folder
    python add_month.py --cost-month "Sep 2026"   # pick the cost month (default: latest in the files)
    python add_month.py --no-split      # don't share Satnam Singh's RSM cost across territories

The script tells which file is which from the column headings (same rules as the old
"Upload files" page). Sales and cost rows already in Base for the same months are replaced.
The old tracker is kept as a timestamped .backup file next to it.
"""
from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

import db as dbm
import dump

HERE = os.path.dirname(os.path.abspath(__file__))
TRACKER = os.path.join(HERE, "P_L_tracker_retail_New.xlsx")
LABELS = {"sales": "ERP sales export", "mapping": "Primary Customer Mapping", "trans": "Trans % sheet",
          "salary": "Salary", "expenses": "Expenses", "incentive": "Incentive", "dbclaim": "DB Claim"}


def get_conn(tracker: str):
    """The database connection; a missing database is bootstrapped from the tracker Excel."""
    fresh = not os.path.exists(dbm.DB_PATH)
    conn = dbm.connect()
    if fresh or dbm.version(conn) == 0:
        if not os.path.exists(tracker):
            raise SystemExit(f"No database and no tracker at {tracker} to bootstrap it from.")
        print(f"First run: importing {os.path.basename(tracker)} into {os.path.basename(dbm.DB_PATH)}…")
        n = dbm.import_excel(conn, tracker)
        print(f"    {n:,} rows imported.")
    return conn


def carry_rate(trans: dict, rsm: str, year: int, mi: int):
    """The RSM's most recent transport rate before (year, mi), matching names like dump.rate_for."""
    k = dump.key(rsm)
    best = None
    for (n, y, m), v in trans.items():
        if not (n == k or (len(n) >= 4 and len(k) >= 4 and (k.startswith(n) or n.startswith(k)))):
            continue
        if (y, m) >= (year, mi):
            continue
        if best is None or (y, m) > best[0]:
            best = ((y, m), v)
    return best


def inr(x):
    a = abs(x)
    s = "-" if x < 0 else ""
    if a >= 1e7:
        return f"{s}₹{a/1e7:.2f} Cr"
    if a >= 1e5:
        return f"{s}₹{a/1e5:.2f} L"
    return f"{s}₹{a:,.0f}"


def main():
    ap = argparse.ArgumentParser(description="Add a month's raw files to the Retail P&L tracker and website.")
    ap.add_argument("folder", nargs="?", default=os.path.join(HERE, "incoming"), help="folder with the month's raw files (default: incoming/)")
    ap.add_argument("--tracker", default=TRACKER, help="tracker xlsx used only to bootstrap a missing database")
    ap.add_argument("--cost-month", default=None, help='cost month to build, e.g. "Sep 2026" (default: latest in the cost files)')
    ap.add_argument("--no-split", action="store_true", help="don't share Satnam Singh's RSM cost across North, Maharashtra and East")
    ap.add_argument("--carry-rates", action="store_true",
                    help="when the Trans %% sheet has no rate for an RSM-month, use that RSM's most recent filled month instead of 4%%")
    ap.add_argument("--dry-run", action="store_true", help="show the report but change nothing")
    args = ap.parse_args()

    if not os.path.isdir(args.folder):
        raise SystemExit(f"Folder not found: {args.folder}\nCreate it and drop the month's files inside.")
    files = [os.path.join(args.folder, f) for f in sorted(os.listdir(args.folder))
             if f.lower().endswith((".xlsx", ".xlsm", ".csv")) and not f.startswith("~$")]
    if not files:
        raise SystemExit(f"No .xlsx, .xlsm or .csv files in {args.folder}.")

    # ---- which file is which ----
    print("Looking at the files:")
    found: dict[str, list] = {}
    for p in files:
        with open(p, "rb") as fh:
            data = fh.read()
        try:
            kinds = dump.detect(data, os.path.basename(p))
        except Exception as e:  # noqa: BLE001
            print(f"  ! {os.path.basename(p)}: could not be opened ({e})")
            continue
        if not kinds:
            print(f"  ? {os.path.basename(p)}: not recognised (none of its sheets has the headings of a sales export, "
                  "Salary, Expenses, Incentive, DB Claim, Customer Mapping or Trans % sheet)")
        for k in kinds:
            found.setdefault(k, []).append((p, data, len(kinds)))
    chosen = {}
    for kind, cands in found.items():
        # a file made for this purpose (fewest kinds) beats a whole tracker; among equals the newest file wins
        best = min(cands, key=lambda c: (c[2], -os.path.getmtime(c[0])))
        chosen[kind] = best
        extra = "" if len(cands) == 1 else " (also in " + ", ".join(os.path.basename(c[0]) for c in cands if c is not best) + ", not used)"
        print(f"  ✓ {LABELS[kind]}: {os.path.basename(best[0])}{extra}")
    for kind in ["sales", "salary", "expenses", "incentive", "dbclaim"]:
        if kind not in chosen:
            print(f"  - {LABELS[kind]}: not in the folder")
    if "sales" not in chosen and not any(k in chosen for k in ["salary", "expenses", "incentive", "dbclaim"]):
        raise SystemExit("Nothing to add: no sales export and no cost sheets found.")

    rd = lambda kind, fn: fn(chosen[kind][1], os.path.basename(chosen[kind][0])) if kind in chosen else None
    sales = rd("sales", dump.read_sales)
    mapping = rd("mapping", dump.read_mapping)
    trans = rd("trans", dump.read_trans)
    costs = {k: rd(k, f) for k, f in [("salary", dump.read_salary), ("expenses", dump.read_expenses),
                                      ("incentive", dump.read_incentive), ("dbclaim", dump.read_dbclaim)] if k in chosen}

    conn = get_conn(args.tracker)
    base_raw = dbm.denormalize(dbm.fetch_df(conn))
    adds = []

    # ---- sales ----
    if sales is not None:
        rate_tab = dump.rate_table(sales, trans)
        if args.carry_rates and trans:
            for i, r in rate_tab.iterrows():
                if r["From sheet"] == "no":
                    hit = carry_rate(trans, r["RSM"], int(r["Year"]), dump.MONTHS.index(r["Month"]))
                    if hit is not None:
                        (fy, fm), v = hit
                        rate_tab.at[i, "Transport %"] = round(v * 100, 2)
                        rate_tab.at[i, "From sheet"] = f"carried from {dump.MONTHS[fm]} {fy}"
        carried = rate_tab[rate_tab["From sheet"].str.startswith("carried")]
        if len(carried):
            print("\nTransport % carried forward (no rate in the Trans % sheet for that month):")
            for _, r in carried.iterrows():
                print(f"    {r['RSM']}  {r['Month']} {r['Year']}: {r['Transport %']:.2f}%  ({r['From sheet']})")
        missing_rate = rate_tab[rate_tab["From sheet"] == "no"]
        if len(missing_rate):
            print("\nTransport % not found in the Trans % sheet for these RSM-months (4% used):")
            for _, r in missing_rate.iterrows():
                print(f"    {r['RSM']}  {r['Month']} {r['Year']}")
        rows, rep = dump.build_sales(sales, mapping, None if mapping is not None else base_raw,
                                     dump.rates_from_table(rate_tab))
        gm = rep["revenue"] - rep["cogs"]
        span = ", ".join(f"{dump.MONTHS[m]} {y}" for y, m in rep["months"])
        print(f"\nSales ready: {rep['rows']:,} invoice lines for {span}")
        print(f"    Revenue {inr(rep['revenue'])} | COGS {inr(rep['cogs'])} | GM {gm/rep['revenue']*100:.1f}%"
              f" | Transport {inr(rep['transport'])} | Opex {inr(rep['revenue'] * dump.OPEX_PCT)}")
        old = dump.replaced_count(base_raw, "sales", rep["months"])
        if old:
            print(f"    Replaces {old:,} sales lines already in Base for {span}.")
        if rep["unmapped"]:
            print(f"    ! {len(rep['unmapped'])} customer(s) not in the mapping, will show under Unassigned: "
                  + ", ".join(rep["unmapped"][:12]) + (" ..." if len(rep["unmapped"]) > 12 else ""))
        if rep["bad_date"]:
            print(f"    ! {rep['bad_date']} row(s) had no readable date and were left out.")
        if rep["missing_optional"]:
            print("    Columns not in the export, left blank: " + ", ".join(rep["missing_optional"]))
        adds.append({"kind": "sales", "keys": rep["months"], "rows": rows})

    # ---- costs ----
    if costs:
        pool = sorted({p for df in costs.values() for p in dump.periods_in(df)})
        if not pool:
            print("\n! No month and year found in the cost files; cost rows skipped.")
        else:
            if args.cost_month:
                try:
                    mon, yr = args.cost_month.split()
                    ym = (int(yr), dump.MONTHS.index(mon[:3].title()))
                except Exception:  # noqa: BLE001
                    raise SystemExit(f'--cost-month must look like "Sep 2026", got: {args.cost_month}')
                if ym not in pool:
                    raise SystemExit(f"--cost-month {args.cost_month} is not in the cost files. "
                                     "Months found: " + ", ".join(f"{dump.MONTHS[m]} {y}" for y, m in pool))
            else:
                ym = pool[-1]
                if len(pool) > 1:
                    print(f"\nCost files hold several months ({', '.join(f'{dump.MONTHS[m]} {y}' for y, m in pool)}); "
                          f"building the latest, {dump.MONTHS[ym[1]]} {ym[0]}. Use --cost-month to pick another.")
            if "salary" not in costs:
                print("    ! Without the Salary sheet, travel and incentive rows keep the RSM/ASM written in their own sheet.")
            rows, rep = dump.build_costs(ym[0], ym[1], costs.get("salary"), costs.get("expenses"),
                                         costs.get("incentive"), costs.get("dbclaim"),
                                         None if args.no_split else dump.SPLIT_DEFAULT)
            t = rep["totals"]
            print(f"\nField costs ready: {rep['rows']:,} cost lines for {dump.MONTHS[ym[1]]} {ym[0]}")
            print(f"    Salary {inr(t['RSM salary'] + t['ASM salary'] + t['SO salary'])}"
                  f" | Travel {inr(t['RSM  Travel'] + t['ASM Travel'] + t['SO Travel'])}"
                  f" | Incentive {inr(t['RSM  Incentive'] + t['ASM Incentive'] + t['SO Incentive'])}"
                  f" | DB claim {inr(t['DB Claim'])}")
            old = dump.replaced_count(base_raw, "cost", [ym])
            if old:
                print(f"    Replaces {old:,} cost lines already in Base for {dump.MONTHS[ym[1]]} {ym[0]}.")
            for (sheet, pos), n in rep["unknown"].items():
                print(f'    ! {sheet}: {n} row(s) have the position "{pos}" (not SO, ASM, ASE or RSM), left out.')
            if rep["salary_rows"] == 0 and "salary" in costs:
                print("    ! The Salary sheet has no rows for this month.")
            adds.append({"kind": "cost", "keys": [ym], "rows": rows})

    if not adds:
        raise SystemExit("\nNothing usable was built; the database was not touched.")
    if args.dry_run:
        print("\nDry run: the database and website data were NOT changed.")
        return

    # ---- write to the database and rebuild the site data ----
    print("\nWriting to the database…")
    source = ", ".join(os.path.basename(p) for p in files)[:200]
    for a in adds:
        added, replaced = dbm.replace_months(conn, a["kind"], a["keys"], a["rows"], source)
        print(f"    {a['kind']}: {added:,} rows added" + (f", {replaced:,} replaced" if replaced else ""))
    conn.close()

    # ---- push the changed months to Supabase, when it is set up ----
    try:
        import supa_sync
        if supa_sync.configured():
            print("Syncing to Supabase…")
            for a in adds:
                print("    " + supa_sync.sync_months(a["kind"], a["keys"], source))
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(f"    ! Supabase sync failed ({e}). The local data is updated; run  python supa_sync.py --full  to retry.")

    print("Rebuilding website data…")
    import subprocess
    r = subprocess.run([sys.executable, os.path.join(HERE, "build_site_data.py"), "--db"],
                       capture_output=True, text=True)
    print("    " + (r.stdout or "").strip().replace("\n", "\n    "))
    if r.returncode != 0:
        raise SystemExit("build_site_data.py failed:\n" + (r.stderr or ""))
    print("\nDone. If you host the site statically, redeploy website/; with server.py the dashboard is already fresh.")


if __name__ == "__main__":
    main()
