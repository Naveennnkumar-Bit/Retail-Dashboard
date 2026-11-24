"""
GO DESi | Retail P&L - build the website's JSON aggregates from the normalized rows
(the db.py `base` table layout: renamed columns + kind + mnum).
"""
from __future__ import annotations

import json
import os
from datetime import datetime

import numpy as np
import pandas as pd

SALES_NUMS = ["qty", "revenue", "cogs", "transport", "opex"]
COST_NUMS = ["so_salary", "so_travel", "so_incentive", "asm_salary", "asm_travel", "asm_incentive",
             "rsm_salary", "rsm_travel", "rsm_incentive", "db_claim"]


def prep(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in SALES_NUMS + COST_NUMS:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    df["period"] = df["year"].astype(int).astype(str) + "-" + df["mnum"].astype(int).astype(str).str.zfill(2)
    blankish = {"": None, "0": None, "0.0": None, "nan": None, "None": None}
    for c in ["rsm", "asm", "zone", "state", "sub_channel", "l0", "l1", "l2", "pack", "type", "customer", "sku", "city"]:
        df[c] = df[c].astype(str).str.strip().replace(blankish)
    df["rsm"] = df["rsm"].fillna("Unassigned")
    df["asm"] = df["asm"].fillna("Unassigned")
    for c in ["zone", "state", "sub_channel", "l0", "l1", "l2", "pack", "type", "customer", "sku", "city"]:
        df[c] = df[c].fillna("Not set")
    df["is_return"] = (df["is_return"].astype(str).str.strip() == "Yes").astype(int)
    return df


def build(df: pd.DataFrame, out_dir: str, source: str = "", source_modified: str = "", quiet: bool = False):
    """df: normalized rows (db layout). Writes the six JSON files the website reads."""
    os.makedirs(out_dir, exist_ok=True)
    df = prep(df)
    S = df[df.kind == "sales"]
    C = df[df.kind == "cost"]

    def dumpf(frame, name):
        for c in frame.columns:
            if frame[c].dtype == float:
                frame[c] = frame[c].round(2)
        p = os.path.join(out_dir, name)
        frame.to_json(p, orient="records")
        if not quiet:
            print(f"  {name}: {len(frame):,} rows, {os.path.getsize(p)/1024:,.0f} KB")

    sales = (S.groupby(["period", "rsm", "asm", "zone", "state", "sub_channel", "l0", "l1", "l2", "pack",
                        "type", "is_return"], dropna=False)[SALES_NUMS].sum().reset_index())
    dumpf(sales, "sales.json")

    costs = C.groupby(["period", "rsm", "asm"], dropna=False)[COST_NUMS].sum().reset_index()
    dumpf(costs, "costs.json")

    skus = (S.groupby(["period", "sku", "type", "is_return", "rsm", "asm"], dropna=False)
              .agg(l0=("l0", "first"), l1=("l1", "first"), l2=("l2", "first"), pack=("pack", "first"),
                   qty=("qty", "sum"), revenue=("revenue", "sum"), cogs=("cogs", "sum")).reset_index())
    dumpf(skus, "skus.json")

    cust = (S.groupby(["period", "customer", "is_return"], dropna=False)
              .agg(state=("state", "first"), zone=("zone", "first"), rsm=("rsm", "first"), asm=("asm", "first"),
                   sub_channel=("sub_channel", "first"), qty=("qty", "sum"), revenue=("revenue", "sum"),
                   cogs=("cogs", "sum"), invoices=("invoice", "nunique")).reset_index())
    dumpf(cust, "customers.json")

    daily = (S[S["date"].astype(str).str.len() > 0].rename(columns={"date": "day"})
               .groupby(["day", "rsm"], dropna=False).agg(revenue=("revenue", "sum")).reset_index())
    dumpf(daily, "daily.json")

    meta = {
        "source": source, "source_modified": source_modified,
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "base_rows": int(len(df)), "sales_rows": int(len(S)), "cost_rows": int(len(C)),
    }
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f)
    if not quiet:
        print("  meta.json written")
    return meta
