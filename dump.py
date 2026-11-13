"""
GO DESi | Retail P&L: turn the monthly files into Base rows.

The dashboard reads the Base sheet of P_L_tracker_retail_New.xlsx. That sheet holds two kinds of rows:

    sales rows : one per invoice line, pasted from the ERP item-wise sales export
    cost rows  : salary, travel, incentive and DB claim, built from the Salary, Expenses, Incentive and DB Claim sheets

This module rebuilds both kinds from the raw files, using the same rules as the tracker's formulas:

    Revenue            = Amount excluding tax
    COGS Total         = COGS
    Transport cost     = revenue x the month's transport % for that RSM (the "Trans %" sheet)
    Operating expense  = 2% of revenue
    FA RSM / ASM Name  = Primary Customer Mapping (customer -> RSM, ASM)
    Salary             = Salary sheet "Gross + TA", by User Position (SO / ASM+ASE / RSM)
    Travel             = Expenses sheet "Provision Amount", by User Position
    Incentive          = Incentive sheet "Incentive amount", by Designation
    DB claim           = DB Claim sheet "Claim Amount"

Every rule was checked against the tracker, month by month, before it went in.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re

import numpy as np
import pandas as pd

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MNUM = {m: i + 1 for i, m in enumerate(MONTHS)}

# The Base columns the dashboard reads, with the tracker's own spelling.
BASE_COLS = [
    "Date", "Month", "Year", "Customer Name", "Sub-Channel", "Customer Group", "Customer City", "Customer State", "Customer Zone",
    "FA RSM", "ASM Name", "Item Name", "L0 - Parent Category", "L1 - Parent Category", "L2 - Parent Category", "L3 - Sub-Category",
    "Packaging Type", "Type", "Returns", "Qty Sold", "Revenue", "COGS Total", "Transportaion Cost", "Operatinal Exp",
    "RSM salary", "RSM  Travel", "RSM  Incentive", "ASM salary", "ASM Travel", "ASM Incentive", "DB Claim",
    "SO salary", "SO Incentive", "SO Travel", "Invoice Number", "Keka Name", "Part of Scheme SKU List?",
]

TRANSPORT_PCT = 0.04
OPEX_PCT = 0.02

# component column in Base for (who, what)
COMP = {
    ("rsm", "salary"): "RSM salary", ("rsm", "travel"): "RSM  Travel", ("rsm", "incentive"): "RSM  Incentive",
    ("asm", "salary"): "ASM salary", ("asm", "travel"): "ASM Travel", ("asm", "incentive"): "ASM Incentive",
    ("so", "salary"): "SO salary", ("so", "travel"): "SO Travel", ("so", "incentive"): "SO Incentive",
    ("db", "claim"): "DB Claim",
}
COST_COLS = list(COMP.values())
POSITION = {"SO": "so", "ASM": "asm", "ASE": "asm", "RSM": "rsm"}

# An RSM whose cost is shared equally over several territories, as the tracker does today.
# Each entry is (FA RSM, ASM Name) exactly as they appear in Base.
SPLIT_DEFAULT = {
    "Satnam Singh": [
        ("Satnam Singh", "Vacant ASM Mahrashtra"),
        ("Satnam Singh", "Vacant ASM North"),
        ("Vacant RSM - East", "Pawan Kumar"),
    ]
}


# ---------------------------------------------------------------- reading files
def norm(h) -> str:
    return re.sub(r"[^a-z0-9]", "", str(h).lower())


def _rows_from_bytes(data: bytes, name: str, need: set, hints: tuple):
    """Return (rows, sheet_name) for the first sheet (or the csv) whose header row holds every column in `need`."""
    lower = name.lower()
    if lower.endswith(".csv") or lower.endswith(".txt"):
        text = data.decode("utf-8-sig", errors="replace")
        return list(csv.reader(io.StringIO(text))), "csv"
    from python_calamine import CalamineWorkbook
    wb = CalamineWorkbook.from_filelike(io.BytesIO(data))
    names = list(wb.sheet_names)
    order = sorted(names, key=lambda n: (0 if any(norm(h) == norm(n) for h in hints) else 1, names.index(n)))
    for n in order:
        sh = wb.get_sheet_by_name(n)
        try:
            top = sh.to_python(nrows=25)
        except TypeError:
            top = sh.to_python()[:25]
        if _find_header(top, need) is not None:
            return sh.to_python(), n
    return None, None


def _find_header(rows, need: set):
    for i, r in enumerate(rows[:25]):
        if need <= {norm(c) for c in r if str(c).strip()}:
            return i
    return None


def read_table(data: bytes, name: str, need: set, hints: tuple = ()) -> pd.DataFrame:
    """Read a table from an uploaded xlsx or csv. If the file is a whole workbook, pick the sheet that fits."""
    rows, sheet = _rows_from_bytes(data, name, need, hints)
    if rows is None:
        raise ValueError(f"{name}: could not find a sheet with these columns: " + ", ".join(sorted(need)))
    i = _find_header(rows, need)
    if i is None:
        raise ValueError(f"{name}: could not find the header row (needs " + ", ".join(sorted(need)) + ")")
    head = [str(c).strip() for c in rows[i]]
    width = len(head)
    body = [list(r[:width]) + [""] * (width - len(r)) for r in rows[i + 1:]]
    df = pd.DataFrame(body, columns=head, dtype=object)
    return df


def pick(df: pd.DataFrame, want: dict, required: list, label: str) -> pd.DataFrame:
    """Rename columns to the wanted names by normalised header. `want` maps target name -> accepted normalised headers."""
    have = {}
    for c in df.columns:
        have.setdefault(norm(c), c)
    out, missing = {}, []
    for target, alts in want.items():
        src = next((have[a] for a in alts if a in have), None)
        if src is None:
            if target in required:
                missing.append(target)
            continue
        out[target] = df[src]
    if missing:
        raise ValueError(f"{label}: missing column(s): " + ", ".join(missing))
    return pd.DataFrame(out, index=df.index)


def num(s) -> pd.Series:
    return pd.to_numeric(pd.Series(s).replace("", np.nan), errors="coerce")


def parse_dates(s: pd.Series) -> pd.Series:
    """Dates as the ERP gives them: real dates, ISO text, or dd-mm-yyyy text."""
    s = pd.Series(s, dtype=object)
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    is_txt = s.map(lambda v: isinstance(v, str) and v.strip() != "")
    iso = s.map(lambda v: isinstance(v, str) and bool(re.match(r"^\d{4}-\d{2}-\d{2}", v.strip())))
    real = ~is_txt & s.map(lambda v: v not in ("", None) and not (isinstance(v, float) and np.isnan(v)))
    if real.any():
        out[real] = pd.to_datetime(s[real], errors="coerce")
    if (is_txt & iso).any():
        out[is_txt & iso] = pd.to_datetime(s[is_txt & iso].str.strip(), errors="coerce")
    other = is_txt & ~iso
    if other.any():
        out[other] = pd.to_datetime(s[other].str.strip(), errors="coerce", dayfirst=True)
    return out


def sig(df: pd.DataFrame) -> str:
    h = pd.util.hash_pandas_object(df.astype(str), index=False).values
    return hashlib.md5(h.tobytes()).hexdigest()[:12]


# ---------------------------------------------------------------- sales rows
SALES_NEED = {"date", "customername", "itemname", "qtysold", "cogs"}
SALES_WANT = {
    "Date": ["date", "invoicedate", "postingdate"],
    "Customer Name": ["customername", "customer"],
    "Sub-Channel": ["subchannel"],
    "Customer Group": ["customergroup"],
    "Customer City": ["customercity"],
    "Customer State": ["customerstate"],
    "Customer Zone": ["customerzone"],
    "Item Name": ["itemname"],
    "RSM": ["rsm"],
    "L0 - Parent Category": ["l0parentcategory"],
    "L1 - Parent Category": ["l1parentcategory"],
    "L2 - Parent Category": ["l2parentcategory"],
    "L3 - Sub-Category": ["l3subcategory"],
    "Packaging Type": ["packagingtype"],
    "Returns": ["returns"],
    "Is Return": ["isreturncreditnote"],
    "Qty Sold": ["qtysold", "qty"],
    "Amount": ["amountexcludingtax", "amountexcltax", "amountbeforetax", "revenue"],
    "COGS": ["cogs", "cogstotal"],
    "Sampling / Sales": ["samplingsales"],
    "Invoice Number": ["invoicenumber", "invoiceno"],
    "Scheme": ["partofschemeskulist"],
}
SALES_REQUIRED = ["Date", "Customer Name", "Item Name", "Qty Sold", "Amount", "COGS"]


def read_sales(data: bytes, name: str) -> pd.DataFrame:
    df = read_table(data, name, SALES_NEED, hints=("Base", "Sales", "Item Wise Sales"))
    return pick(df, SALES_WANT, SALES_REQUIRED, "Sales export")


def read_mapping(data: bytes, name: str) -> pd.DataFrame:
    df = read_table(data, name, {"customername", "rsmname", "asmname"}, hints=("Primary Customer Mapping",))
    return pick(df, {"Customer Name": ["customername"], "RSM Name": ["rsmname"], "ASM Name": ["asmname"]},
                ["Customer Name", "RSM Name", "ASM Name"], "Customer mapping")


def key(s) -> str:
    return re.sub(r"\s+", " ", str(s)).strip().lower()


def mapping_from_base(raw: pd.DataFrame) -> dict:
    """Customer -> (FA RSM, ASM Name) from the sales rows already in Base, latest row wins."""
    m = raw[raw["Date"].map(lambda v: v not in ("", None))]
    m = m[(m["FA RSM"].astype(str).str.strip() != "") & (m["Customer Name"].astype(str).str.strip() != "")]
    out = {}
    for c, r, a in zip(m["Customer Name"], m["FA RSM"], m["ASM Name"]):
        out[key(c)] = (str(r).strip(), str(a).strip())
    return out



# ---------------------------------------------------------------- transport % (Trans % sheet)
FULL_MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]


def _pct(v):
    if v in ("", None):
        return None
    if isinstance(v, (int, float)):
        return None if isinstance(v, float) and np.isnan(v) else float(v)
    t = str(v).strip().replace(",", ".").replace("%", "")
    try:
        x = float(t)
    except ValueError:
        return None
    return x / 100 if x > 1 else x


def parse_trans_rows(rows) -> dict:
    """The 'Trans %' sheet: blocks headed 'RSM', a years row, then one row per month. -> {(rsm key, year, month index): rate}"""
    res, i = {}, 0
    while i < len(rows):
        r = rows[i]
        if str(r[0]).strip().lower() == "rsm" and i + 1 < len(rows):
            names = [(j, str(v).strip()) for j, v in enumerate(r) if j > 0 and str(v).strip()]
            yr = rows[i + 1]
            ends = [j for j, _ in names][1:] + [len(yr)]
            k = i + 2
            while k < len(rows) and str(rows[k][0]).strip().lower() in FULL_MONTHS + ["full year"]:
                lab = str(rows[k][0]).strip().lower()
                if lab in FULL_MONTHS:
                    mi = FULL_MONTHS.index(lab)
                    for (j, nm), end in zip(names, ends):
                        for c in range(j, end):
                            y = yr[c] if c < len(yr) else ""
                            v = _pct(rows[k][c]) if c < len(rows[k]) else None
                            if v is not None and isinstance(y, (int, float)) and y == y:
                                res[(key(nm), int(y), mi)] = v
                k += 1
            i = k
        else:
            i += 1
    return res


def read_trans(data: bytes, name: str) -> dict:
    from python_calamine import CalamineWorkbook
    wb = CalamineWorkbook.from_filelike(io.BytesIO(data))
    names = list(wb.sheet_names)
    pick_ = next((n for n in names if norm(n) == "trans"), None)
    if pick_ is None:
        pick_ = next((n for n in names if "trans" in norm(n)), names[0])
    res = parse_trans_rows(wb.get_sheet_by_name(pick_).to_python())
    if not res:
        raise ValueError(f"{name}: no 'RSM' blocks with monthly transport % found.")
    return res


def rate_for(trans: dict, rsm: str, year: int, mi: int):
    """The month's transport % for an RSM name from the export. Exact name first, then a name that starts the same."""
    k = key(rsm)
    if (k, year, mi) in trans:
        return trans[(k, year, mi)]
    for (n, y, m), v in trans.items():
        if y == year and m == mi and n and (k.startswith(n) or n.startswith(k)) and len(n) >= 4 and len(k) >= 4:
            return v
    return None


def rate_table(sales: pd.DataFrame, trans: dict | None, default: float = TRANSPORT_PCT) -> pd.DataFrame:
    """One row per RSM and month in the export, with the transport % to apply (in percent), ready to edit."""
    dt = parse_dates(sales["Date"])
    rsm = sales["RSM"].astype(str).str.strip() if "RSM" in sales else pd.Series("", index=sales.index)
    d = pd.DataFrame({"RSM": rsm, "Year": dt.dt.year, "mi": dt.dt.month - 1}).dropna()
    d = d.drop_duplicates().sort_values(["Year", "mi", "RSM"])
    out = []
    for r, y, m in zip(d["RSM"], d["Year"].astype(int), d["mi"].astype(int)):
        v = rate_for(trans, r, y, m) if trans else None
        out.append({"RSM": r, "Year": y, "Month": MONTHS[m], "Transport %": round((v if v is not None else default) * 100, 2),
                    "From sheet": "yes" if v is not None else "no"})
    return pd.DataFrame(out, columns=["RSM", "Year", "Month", "Transport %", "From sheet"])


def rates_from_table(t: pd.DataFrame) -> dict:
    return {(str(r), int(y), MONTHS.index(m)): float(p) / 100 for r, y, m, p in zip(t["RSM"], t["Year"], t["Month"], t["Transport %"])}


def build_sales(sales: pd.DataFrame, mapping: pd.DataFrame | None, base_raw: pd.DataFrame | None, rates: dict | None = None):
    """Sales export -> Base rows. `rates` maps (RSM name in the export, year, month index) to the transport fraction.
    Returns (rows, report)."""
    s = sales.copy()
    s["_dt"] = parse_dates(s["Date"])
    blank = s["Item Name"].astype(str).str.strip().eq("") & s["_dt"].isna()
    s = s[~blank]
    bad_date = int(s["_dt"].isna().sum())
    s = s[s["_dt"].notna()].copy()
    if s.empty:
        raise ValueError("Sales export: no rows with a valid Date.")

    cmap = mapping_from_base(base_raw) if base_raw is not None else {}
    if mapping is not None:
        for c, r, a in zip(mapping["Customer Name"], mapping["RSM Name"], mapping["ASM Name"]):
            if str(c).strip():
                cmap[key(c)] = (str(r).strip(), str(a).strip())
    ck = s["Customer Name"].map(key)
    rsm = ck.map(lambda k: cmap.get(k, ("", ""))[0])
    asm = ck.map(lambda k: cmap.get(k, ("", ""))[1])
    unmapped = sorted(set(s.loc[rsm.eq(""), "Customer Name"].astype(str).str.strip()))

    amt = num(s["Amount"]).fillna(0.0)
    cogs = num(s["COGS"]).fillna(0.0)
    qty = num(s["Qty Sold"]).fillna(0.0)

    def col(name, default=""):
        return s[name].astype(object).where(s[name].astype(str).str.strip() != "", default) if name in s else pd.Series(default, index=s.index)

    if "Returns" in s:
        ret = col("Returns", "No").astype(str).str.strip()
    elif "Is Return" in s:
        ret = np.where(num(s["Is Return"]).fillna(0) > 0, "Yes", "No")
    else:
        ret = "No"
    typ = col("Sampling / Sales", "Sales").astype(str).str.strip() if "Sampling / Sales" in s else pd.Series("Sales", index=s.index)

    rows = pd.DataFrame("", index=s.index, columns=BASE_COLS, dtype=object)
    rows["Date"] = s["_dt"].dt.to_pydatetime()
    rows["Month"] = s["_dt"].dt.month.map(lambda m: MONTHS[m - 1])
    rows["Year"] = s["_dt"].dt.year.astype(int)
    for dst, src in [("Customer Name", "Customer Name"), ("Sub-Channel", "Sub-Channel"), ("Customer Group", "Customer Group"),
                     ("Customer City", "Customer City"), ("Customer State", "Customer State"), ("Customer Zone", "Customer Zone"),
                     ("Item Name", "Item Name"), ("L0 - Parent Category", "L0 - Parent Category"),
                     ("L1 - Parent Category", "L1 - Parent Category"), ("L2 - Parent Category", "L2 - Parent Category"),
                     ("L3 - Sub-Category", "L3 - Sub-Category"), ("Packaging Type", "Packaging Type"),
                     ("Invoice Number", "Invoice Number"), ("Part of Scheme SKU List?", "Scheme")]:
        if src in s:
            rows[dst] = s[src].where(s[src].astype(str).str.strip() != "", "")
    rows["FA RSM"], rows["ASM Name"] = rsm, asm
    rows["Type"], rows["Returns"] = typ, ret
    rows["Qty Sold"], rows["Revenue"], rows["COGS Total"] = qty, amt, cogs
    rsm_raw = s["RSM"].astype(str).str.strip() if "RSM" in s else pd.Series("", index=s.index)
    yrs, mis = s["_dt"].dt.year.astype(int), s["_dt"].dt.month.astype(int) - 1
    rate = pd.Series(TRANSPORT_PCT, index=s.index, dtype=float)
    no_rate = set()
    if rates is not None:
        for (nm, y, m), idx in pd.DataFrame({"n": rsm_raw, "y": yrs, "m": mis}).groupby(["n", "y", "m"]).groups.items():
            v = rates.get((nm, y, m))
            if v is None:
                no_rate.add(nm)
            else:
                rate.loc[idx] = v
    rows["Transportaion Cost"] = amt * rate
    rows["Operatinal Exp"] = amt * OPEX_PCT
    for c in COST_COLS:
        rows[c] = ""
    rows = rows.reset_index(drop=True).astype(object)

    months = sorted({(int(y), MONTHS.index(m)) for y, m in zip(rows["Year"], rows["Month"])})
    rep = {
        "rows": len(rows), "months": months, "revenue": float(amt.sum()), "cogs": float(cogs.sum()),
        "returns_rows": int((pd.Series(ret, index=s.index) == "Yes").sum()) if not isinstance(ret, str) else 0,
        "unmapped": unmapped, "bad_date": bad_date, "no_rate": sorted(no_rate), "transport": float((amt * rate).sum()),
        "missing_optional": [c for c in ["Sub-Channel", "Customer Group", "Customer City", "Customer State", "Customer Zone",
                                         "L0 - Parent Category", "L1 - Parent Category", "L2 - Parent Category", "L3 - Sub-Category",
                                         "Packaging Type", "Invoice Number", "Sampling / Sales", "Returns"] if c not in s],
    }
    return rows, rep


# ---------------------------------------------------------------- cost rows
SAL_NEED = {"month", "year", "kekaid", "userposition"}
SAL_WANT = {
    "Month": ["month"], "Year": ["year"], "Id": ["kekaid"], "Name": ["nameoftheemployee", "employeename", "name"],
    "Position": ["userposition"], "RSM": ["rsmname"], "ASM": ["asmase", "asmname"],
    "GrossTA": ["grossta"], "Earned": ["totalgrossearned"], "TA": ["ta"],
}
EXP_NEED = {"month", "year", "employeeid", "userposition", "provisionamount"}
EXP_WANT = {
    "Month": ["month"], "Year": ["year"], "Id": ["employeeid"], "Name": ["employeename"], "Position": ["userposition"],
    "RSM": ["rsmname"], "ASM": ["asmase"], "Provision": ["provisionamount"],
}
INC_NEED = {"incentivemonth", "year", "employeeid", "designation", "incentiveamount"}
INC_WANT = {
    "Month": ["incentivemonth"], "Year": ["year"], "Id": ["employeeid"], "Name": ["employeename"], "Position": ["designation"],
    "RSM": ["rsmname"], "ASM": ["asmname"], "Amount": ["incentiveamount"],
}
DB_NEED = {"month", "year", "asmid", "dbname", "claimamount"}
DB_WANT = {"Month": ["month"], "Year": ["year"], "RSM": ["rsmname"], "ASM": ["asmname"], "Name": ["dbname"], "Amount": ["claimamount"]}


def read_salary(data, name):
    return pick(read_table(data, name, SAL_NEED, ("Salary",)), SAL_WANT, ["Month", "Year", "Id", "Position", "RSM", "ASM"], "Salary")


def read_expenses(data, name):
    return pick(read_table(data, name, EXP_NEED, ("Expenses",)), EXP_WANT, ["Month", "Year", "Id", "Position", "Provision"], "Expenses")


def read_incentive(data, name):
    return pick(read_table(data, name, INC_NEED, ("Incentive",)), INC_WANT, ["Month", "Year", "Id", "Position", "Amount"], "Incentive")


def read_dbclaim(data, name):
    return pick(read_table(data, name, DB_NEED, ("DB Claim",)), DB_WANT, ["Month", "Year", "RSM", "ASM", "Amount"], "DB Claim")


def _ym(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["_y"] = pd.to_numeric(d["Year"], errors="coerce")
    d["_m"] = d["Month"].astype(str).str.strip().str[:3].str.title()
    return d


def periods_in(df: pd.DataFrame) -> list:
    d = _ym(df)
    d = d[d["_y"].notna() & d["_m"].isin(MONTHS)]
    return sorted({(int(y), MONTHS.index(m)) for y, m in zip(d["_y"], d["_m"])})


def _is_cost_row(raw: pd.DataFrame) -> pd.Series:
    return raw["Date"].map(lambda v: v in ("", None) or (isinstance(v, float) and np.isnan(v)))


def build_costs(year: int, mi: int, salary=None, expenses=None, incentive=None, dbclaim=None, split: dict | None = None):
    """Salary, Expenses, Incentive and DB Claim -> Base cost rows for one month. Returns (rows, report)."""
    mon = MONTHS[mi]
    out, warn = [], []
    sal_m = None
    same, first = {}, {}
    if salary is not None:
        sal = _ym(salary)
        for i, a, b in zip(sal["Id"], sal["RSM"], sal["ASM"]):
            first.setdefault(str(i).strip(), (str(a).strip(), str(b).strip()))
        sal_m = sal[(sal["_y"] == year) & (sal["_m"] == mon)]
        for i, a, b in zip(sal_m["Id"], sal_m["RSM"], sal_m["ASM"]):
            same.setdefault(str(i).strip(), (str(a).strip(), str(b).strip()))

    def who(emp_id, rsm_src="", asm_src=""):
        k = str(emp_id).strip()
        if k in same:
            return same[k]
        if k in first:
            return first[k]
        return (str(rsm_src).strip(), str(asm_src).strip())

    def emit(rsm, asm, name, comp, amount):
        amount = float(amount)
        if amount == 0 or np.isnan(amount):
            return
        if split and comp in ("rsm",) and rsm in split:
            parts = split[rsm]
            for r, a in parts:
                out.append((r, a, name, COMP[(comp, kind_now)], amount / len(parts)))
        else:
            out.append((rsm, asm, name, COMP[(comp, kind_now)], amount))

    unknown = {}
    kind_now = "salary"
    if sal_m is not None:
        for _, r in sal_m.iterrows():
            comp = POSITION.get(str(r["Position"]).strip().upper())
            if comp is None:
                unknown[("Salary", str(r["Position"]))] = unknown.get(("Salary", str(r["Position"])), 0) + 1
                continue
            gta = num([r["GrossTA"]]).iloc[0] if "GrossTA" in r.index else np.nan
            if pd.isna(gta):
                gta = (num([r.get("Earned", "")]).fillna(0).iloc[0] + num([r.get("TA", "")]).fillna(0).iloc[0])
            emit(str(r["RSM"]).strip(), str(r["ASM"]).strip(), r.get("Name", ""), comp, gta)

    if expenses is not None:
        kind_now = "travel"
        e = _ym(expenses)
        e = e[(e["_y"] == year) & (e["_m"] == mon)]
        for _, r in e.iterrows():
            comp = POSITION.get(str(r["Position"]).strip().upper())
            if comp is None:
                unknown[("Expenses", str(r["Position"]))] = unknown.get(("Expenses", str(r["Position"])), 0) + 1
                continue
            rs, am = who(r["Id"], r.get("RSM", ""), r.get("ASM", ""))
            emit(rs, am, r.get("Name", ""), comp, num([r["Provision"]]).fillna(0).iloc[0])

    if incentive is not None:
        kind_now = "incentive"
        i_ = _ym(incentive)
        i_ = i_[(i_["_y"] == year) & (i_["_m"] == mon)]
        for _, r in i_.iterrows():
            amt = num([r["Amount"]]).fillna(0).iloc[0]
            if amt == 0:
                continue
            comp = POSITION.get(str(r["Position"]).strip().upper())
            if comp is None:
                unknown[("Incentive", str(r["Position"]))] = unknown.get(("Incentive", str(r["Position"])), 0) + 1
                continue
            rs, am = who(r["Id"], r.get("RSM", ""), r.get("ASM", ""))
            emit(rs, am, r.get("Name", ""), comp, amt)

    if dbclaim is not None:
        d = _ym(dbclaim)
        d = d[(d["_y"] == year) & (d["_m"] == mon)]
        for _, r in d.iterrows():
            amt = num([r["Amount"]]).fillna(0).iloc[0]
            if amt:
                out.append((str(r["RSM"]).strip(), str(r["ASM"]).strip(), r.get("Name", ""), COMP[("db", "claim")], float(amt)))

    rows = pd.DataFrame("", index=range(len(out)), columns=BASE_COLS, dtype=object)
    if out:
        rows["Month"], rows["Year"] = mon, year
        rows["FA RSM"] = [o[0] for o in out]
        rows["ASM Name"] = [o[1] for o in out]
        rows["Keka Name"] = [str(o[2]) for o in out]
        rows["Type"] = "Expenses"
        for c in COST_COLS:
            rows[c] = pd.Series([o[4] if o[3] == c else "" for o in out], dtype=object)
    rows = rows.astype(object)
    totals = {c: float(num(rows[c]).fillna(0).sum()) for c in COST_COLS}
    return rows, {"rows": len(rows), "totals": totals, "unknown": unknown,
                  "salary_rows": 0 if sal_m is None else len(sal_m)}


# ---------------------------------------------------------------- putting rows into Base
def apply_adds(raw: pd.DataFrame, adds: list) -> pd.DataFrame:
    """Add rows to the Base frame. Rows of the same kind (sales or cost) for the same month are replaced."""
    out = raw
    for a in adds:
        rows, kind, keys = a["rows"], a["kind"], set(a["keys"])
        yr = pd.to_numeric(out["Year"], errors="coerce")
        mo = out["Month"].astype(str).str.strip().str[:3].str.title().map(lambda m: MONTHS.index(m) if m in MONTHS else -1)
        hit = pd.Series([(y == y and (int(y), m) in keys) for y, m in zip(yr, mo)], index=out.index)
        same_kind = _is_cost_row(out) if kind == "cost" else ~_is_cost_row(out)
        out = pd.concat([out[~(hit & same_kind)], rows[BASE_COLS]], ignore_index=True)
    return out


def replaced_count(raw: pd.DataFrame, kind: str, keys) -> int:
    keys = set(keys)
    yr = pd.to_numeric(raw["Year"], errors="coerce")
    mo = raw["Month"].astype(str).str.strip().str[:3].str.title().map(lambda m: MONTHS.index(m) if m in MONTHS else -1)
    hit = pd.Series([(y == y and (int(y), m) in keys) for y, m in zip(yr, mo)], index=raw.index)
    same_kind = _is_cost_row(raw) if kind == "cost" else ~_is_cost_row(raw)
    return int((hit & same_kind).sum())


def to_base_xlsx(raw: pd.DataFrame) -> bytes:
    """The updated Base as a workbook the dashboard reads (sheet 'Base', same headers)."""
    d = raw[BASE_COLS].copy()
    sales = ~_is_cost_row(d)
    dates = parse_dates(d.loc[sales, "Date"])
    clean = [t.to_pydatetime() if pd.notna(t) else orig for t, orig in zip(dates, d.loc[sales, "Date"])]
    d["Date"] = d["Date"].astype(object)
    d.loc[sales, "Date"] = pd.Series(clean, index=d.index[sales], dtype=object)
    buf = io.BytesIO()
    try:
        import xlsxwriter  # noqa: F401
        engine = "xlsxwriter"
    except ImportError:  # slower, but needs nothing beyond openpyxl
        engine = "openpyxl"
    with pd.ExcelWriter(buf, engine=engine, datetime_format="dd-mm-yyyy") as xw:
        d.to_excel(xw, sheet_name="Base", index=False)
    return buf.getvalue()
