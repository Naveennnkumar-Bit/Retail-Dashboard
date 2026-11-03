"""
GO DESi | Retail P&L Command Centre

Reads the "Base" sheet of P_L_tracker_retail_New.xlsx.
The Base sheet holds two kinds of rows:
    sales rows : one per invoice line (Date filled) with revenue, COGS, transport and opex
    cost rows  : one per employee per month (Date blank) with salary, travel, incentive and DB claim
Net margin = Gross margin - Transport - Operating exp - Field team cost - DB claim
which is exactly how the "YTD & L3M Summary" pivot computes NM.
"""
import hashlib
import io
import os
from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="GO DESi | Retail P&L", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

# ---------------------------------------------------------------- theme
NAVY, INDIGO, SAFFRON, TEAL, GREEN, RED, AMBER = "#0B1F4B", "#3B4BDB", "#F28C28", "#0E9F9A", "#16A34A", "#DC2626", "#D97706"
INK, MUTED, LINE, PAGE, CARD = "#0F172A", "#64748B", "#E3E8F2", "#F5F7FB", "#FFFFFF"
SERIES = [INDIGO, SAFFRON, TEAL, "#8B5CF6", "#EC4899", "#0EA5E9", "#84CC16", "#F59E0B", "#64748B", "#14B8A6"]

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, .stApp, p, li, label, input, button, [data-testid="stMarkdownContainer"] {{ font-family: 'Inter', system-ui, sans-serif !important; }}
.stApp {{ background: {PAGE}; }}
#MainMenu, footer {{ visibility: hidden; }}
[data-testid="stHeader"] {{ background: transparent; height: 0; }}
[data-testid="stMainBlockContainer"], [data-testid="block-container"] {{ padding-top: 1.2rem !important; max-width: 1440px; }}
[data-testid="stSidebar"] {{ background: {NAVY}; }}
[data-testid="stSidebar"] * {{ color: #E6EBF7 !important; }}
[data-testid="stSidebar"] [data-baseweb="select"] > div {{ background: #FFFFFF !important; border-color: transparent !important; border-radius: 10px !important; }}
[data-testid="stSidebar"] [data-baseweb="select"] *, [data-testid="stSidebar"] [data-baseweb="input"] * {{ color: {INK} !important; }}
[data-testid="stSidebar"] [data-baseweb="tag"] span {{ color: {INK} !important; }}
[data-testid="stSidebar"] input {{ color: {INK} !important; -webkit-text-fill-color: {INK} !important; opacity: 1 !important; }}
[data-testid="stSidebar"] [data-baseweb="tag"] {{ background: #FDE3C8 !important; }}
[data-testid="stSidebar"] .side-h {{ font-size: .72rem; letter-spacing: .12em; text-transform: uppercase; color: #9FB0D6 !important; margin: 18px 0 4px; font-weight: 700; }}
[data-testid="stSidebar"] [data-testid="stFileUploader"] section {{ background: rgba(255,255,255,0.05) !important; }}
[data-testid="stSidebar"] [data-testid="stFileUploader"] button {{ color: {INK} !important; }}
[data-testid="stSidebar"] [data-testid="stFileUploader"] button * {{ color: {INK} !important; }}
.top {{ display: flex; align-items: center; gap: 16px; background: linear-gradient(120deg, {NAVY} 0%, #1C2F73 60%, #2A3FA8 100%);
        border-radius: 20px; padding: 22px 28px; color: white; margin-bottom: 14px; position: relative; overflow: hidden; }}
.top::after {{ content: ""; position: absolute; right: -60px; top: -80px; width: 260px; height: 260px; border-radius: 50%;
        background: radial-gradient(circle, rgba(242,140,40,0.45), transparent 65%); }}
.top .logo {{ width: 52px; height: 52px; border-radius: 14px; background: {SAFFRON}; display: grid; place-items: center; font-weight: 800; color: {NAVY}; font-size: 1.1rem; flex: none; }}
.top h1 {{ color: white !important; font-size: 1.6rem !important; font-weight: 800 !important; margin: 0 !important; padding: 0 !important; letter-spacing: -.3px; }}
.top .sub {{ color: #C9D3F0; font-size: .92rem; margin-top: 2px; }}
.top .pill {{ margin-left: auto; z-index: 1; background: rgba(255,255,255,0.12); border: 1px solid rgba(255,255,255,0.2); border-radius: 999px;
        padding: 8px 16px; font-size: .86rem; font-weight: 600; color: white; white-space: nowrap; }}
.kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin: 4px 0 6px; }}
.kpi {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 16px; padding: 15px 17px 13px; box-shadow: 0 1px 2px rgba(15,23,42,.04); }}
.kpi .l {{ color: {MUTED}; font-size: .78rem; font-weight: 600; text-transform: uppercase; letter-spacing: .06em; }}
.kpi .v {{ color: {INK}; font-size: 1.65rem; font-weight: 800; letter-spacing: -.5px; margin-top: 4px; line-height: 1.1; }}
.kpi .s {{ color: {MUTED}; font-size: .82rem; margin-top: 3px; }}
.kpi .d {{ display: inline-block; font-size: .78rem; font-weight: 700; padding: 2px 8px; border-radius: 999px; margin-top: 7px; }}
.d.up {{ background: #DCFCE7; color: #166534; }} .d.down {{ background: #FEE2E2; color: #991B1B; }} .d.flat {{ background: #EEF2F7; color: {MUTED}; }}
.card-h {{ font-weight: 700; font-size: 1.02rem; color: {INK}; margin: 0 0 2px; }}
.card-s {{ color: {MUTED}; font-size: .84rem; margin: 0 0 6px; }}
[data-testid="stVerticalBlockBorderWrapper"] {{ background: {CARD}; border-radius: 16px !important; border-color: {LINE} !important; }}
.insight {{ display: flex; gap: 10px; align-items: flex-start; padding: 9px 0; border-bottom: 1px dashed {LINE}; font-size: .92rem; color: {INK}; }}
.insight:last-child {{ border-bottom: none; }}
.insight .ic {{ width: 26px; height: 26px; border-radius: 8px; display: grid; place-items: center; flex: none; font-size: .85rem; }}
.note {{ background: #FFF7ED; border: 1px solid #FED7AA; color: #9A3412; border-radius: 12px; padding: 9px 14px; font-size: .86rem; margin: 4px 0 10px; }}
table.pl {{ border-collapse: separate; border-spacing: 0; width: 100%; font-size: .86rem; }}
table.pl th {{ position: sticky; top: 0; background: {NAVY}; color: white; padding: 9px 12px; text-align: right; font-weight: 600; white-space: nowrap; }}
table.pl th:first-child {{ text-align: left; left: 0; z-index: 2; border-top-left-radius: 10px; }}
table.pl th:last-child {{ border-top-right-radius: 10px; }}
table.pl td {{ padding: 7px 12px; text-align: right; border-bottom: 1px solid {LINE}; white-space: nowrap; color: {INK}; background: white; }}
table.pl td:first-child {{ text-align: left; position: sticky; left: 0; background: white; z-index: 1; }}
table.pl tr.sub td {{ background: #F1F4FB; font-weight: 700; }}
table.pl tr.total td {{ background: #E7ECFB; font-weight: 800; border-top: 2px solid {INDIGO}; }}
table.pl tr.pct td {{ color: {MUTED}; font-style: italic; font-size: .8rem; }}
table.pl tr.ind td:first-child {{ padding-left: 26px; color: #334155; }}
table.pl td.neg {{ color: {RED}; }}
table.pl td.tot {{ background: #F8FAFF; font-weight: 700; }}
.plwrap {{ overflow: auto; border: 1px solid {LINE}; border-radius: 12px; }}
div[data-testid="stSegmentedControl"] button p {{ font-weight: 600; }}
</style>
""", unsafe_allow_html=True)

PLOT_CFG = {"displayModeBar": False}


def style_fig(fig, h=360, legend=True):
    fig.update_layout(height=h, margin=dict(l=8, r=8, t=44 if legend else 10, b=8), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="Inter, system-ui, sans-serif", color=INK, size=12), colorway=SERIES,
                      hoverlabel=dict(bgcolor="white", font_size=12, bordercolor=LINE),
                      legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, bgcolor="rgba(0,0,0,0)", title_text="") if legend else None, showlegend=legend)
    fig.update_xaxes(showgrid=False, linecolor=LINE, tickfont=dict(color=MUTED))
    fig.update_yaxes(gridcolor="#EDF1F7", zeroline=False, tickfont=dict(color=MUTED))
    if "yaxis2" in fig.layout and fig.layout.yaxis2.overlaying:
        fig.update_layout(yaxis2=dict(tickformat=".0f", ticksuffix="%", tickfont=dict(color=MUTED)))
    return fig


# ---------------------------------------------------------------- formatting
def inr(x, dec=2):
    """Indian short form: Cr / L / K."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "–"
    a, s = abs(x), "-" if x < 0 else ""
    if a >= 1e7:
        return f"{s}₹{a/1e7:.{dec}f} Cr"
    if a >= 1e5:
        return f"{s}₹{a/1e5:.{dec}f} L"
    if a >= 1e3:
        return f"{s}₹{a/1e3:.1f} K"
    return f"{s}₹{a:,.0f}"


def pct(x, dec=1):
    return "–" if x is None or not np.isfinite(x) else f"{x*100:.{dec}f}%"


def lakhs(x):
    return x / 1e5


def div(a, b):
    return a / b if b else np.nan


# ---------------------------------------------------------------- data
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MNUM = {m: i + 1 for i, m in enumerate(MONTHS)}
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
NUMS = ["qty", "revenue", "cogs", "transport", "opex", "rsm_salary", "rsm_travel", "rsm_incentive", "asm_salary", "asm_travel",
        "asm_incentive", "db_claim", "so_salary", "so_incentive", "so_travel"]
TEXTS = ["customer", "sub_channel", "cust_group", "city", "state", "zone", "rsm", "asm", "sku", "l0", "l1", "l2", "l3", "pack",
         "type", "is_return", "invoice", "employee", "scheme"]
DEFAULT_FILES = ["P_L_tracker_retail_New.xlsx", "data/P_L_tracker_retail_New.xlsx"]


@st.cache_data(show_spinner="Reading the Base sheet…", max_entries=3)
def load_base(raw: bytes, digest: str) -> pd.DataFrame:
    from python_calamine import CalamineWorkbook
    wb = CalamineWorkbook.from_filelike(io.BytesIO(raw))
    rows = wb.get_sheet_by_name("Base").to_python()
    head = [str(c).strip() for c in rows[0]]
    df = pd.DataFrame(rows[1:], columns=head)
    df.columns = [c.strip() for c in df.columns]
    missing = [k for k in RENAME if k.strip() not in df.columns]
    if missing:
        raise ValueError("Base sheet is missing columns: " + ", ".join(missing))
    df = df[[k.strip() for k in RENAME]].rename(columns={k.strip(): v for k, v in RENAME.items()})
    df = df[df["month"].astype(str).str[:3].isin(MONTHS)].copy()
    for c in NUMS:
        df[c] = pd.to_numeric(df[c].replace("", np.nan), errors="coerce").fillna(0.0)
    for c in TEXTS:
        df[c] = df[c].astype(str).str.strip().replace({"": None, "0": None, "0.0": None, "nan": None})
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype(int)
    df["mnum"] = df["month"].astype(str).str[:3].map(MNUM)
    df["period"] = pd.to_datetime(dict(year=df["year"], month=df["mnum"], day=1))
    df["kind"] = np.where(df["date"].astype(str).str.len() > 0, "sales", "cost")
    df["date"] = pd.to_datetime(df["date"].where(df["kind"] == "sales"), errors="coerce")
    fy0 = np.where(df["mnum"] >= 4, df["year"], df["year"] - 1)
    df["fy"] = [f"FY {a % 100:02d}-{(a + 1) % 100:02d}" for a in fy0]
    df["rsm"] = df["rsm"].fillna("Unassigned")
    df["asm"] = df["asm"].fillna("Unassigned")
    for c in ["zone", "state", "sub_channel", "cust_group", "l0", "l1", "l2", "pack", "type", "customer", "sku", "city"]:
        df[c] = df[c].fillna("Not set")
    df["is_return"] = df["is_return"].eq("Yes")
    df["gm"] = df["revenue"] - df["cogs"]
    df["so_cost"] = df["so_salary"] + df["so_travel"] + df["so_incentive"]
    df["asm_cost"] = df["asm_salary"] + df["asm_travel"] + df["asm_incentive"]
    df["rsm_cost"] = df["rsm_salary"] + df["rsm_travel"] + df["rsm_incentive"]
    df["field"] = df["so_cost"] + df["asm_cost"] + df["rsm_cost"] + df["db_claim"]
    df["contrib"] = df["gm"] - df["transport"] - df["opex"]
    df["nm"] = df["contrib"] - df["field"]
    for c in ["zone", "state", "sub_channel", "cust_group", "l0", "l1", "l2", "pack", "type", "rsm", "asm", "fy"]:
        df[c] = df[c].astype("category")
    return df.drop(columns=["mnum"])


def get_source():
    up = st.sidebar.file_uploader("P&L tracker (.xlsx)", type=["xlsx"], help="Upload the latest P_L_tracker_retail file. Only the Base sheet is read.")
    if up is not None:
        raw = up.getvalue()
        return raw, up.name
    for f in DEFAULT_FILES:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), f)
        if os.path.exists(p):
            with open(p, "rb") as fh:
                return fh.read(), os.path.basename(p)
    return None, None


# ---------------------------------------------------------------- P&L maths
SUM_COLS = ["revenue", "cogs", "gm", "transport", "opex", "contrib", "so_salary", "so_travel", "so_incentive", "asm_salary",
            "asm_travel", "asm_incentive", "rsm_salary", "rsm_travel", "rsm_incentive", "db_claim", "so_cost", "asm_cost",
            "rsm_cost", "field", "nm", "qty"]


def totals(d: pd.DataFrame) -> pd.Series:
    s = d[SUM_COLS].sum()
    s["gm_pct"] = div(s.gm, s.revenue)
    s["contrib_pct"] = div(s.contrib, s.revenue)
    s["field_pct"] = div(s.field, s.revenue)
    s["nm_pct"] = div(s.nm, s.revenue)
    return s


def group_pl(d: pd.DataFrame, by) -> pd.DataFrame:
    g = d.groupby(by, observed=True)[SUM_COLS].sum()
    g["gm_pct"] = g.gm / g.revenue.replace(0, np.nan)
    g["contrib_pct"] = g.contrib / g.revenue.replace(0, np.nan)
    g["field_pct"] = g.field / g.revenue.replace(0, np.nan)
    g["nm_pct"] = g.nm / g.revenue.replace(0, np.nan)
    return g


def growth(cur, prev):
    return (cur - prev) / abs(prev) if prev else np.nan


# ---------------------------------------------------------------- UI helpers
def kpi(label, value, sub="", delta=None, delta_kind="pct", good_up=True, cmp_label="vs LY"):
    chip = ""
    if delta is not None and np.isfinite(delta):
        if delta_kind == "pct":
            txt, mag = f"{'▲' if delta >= 0 else '▼'} {abs(delta)*100:.1f}% {cmp_label}", delta
        else:
            txt, mag = f"{'▲' if delta >= 0 else '▼'} {abs(delta)*100:.1f} pts {cmp_label}", delta
        cls = "flat" if abs(mag) < 0.0005 else ("up" if (mag > 0) == good_up else "down")
        if cls == "flat":
            txt = f"● level {cmp_label}"
        chip = f'<div class="d {cls}">{txt}</div>'
    return f'<div class="kpi"><div class="l">{label}</div><div class="v">{value}</div><div class="s">{sub}</div>{chip}</div>'


def card_head(title, sub=""):
    st.markdown(f'<div class="card-h">{title}</div>' + (f'<div class="card-s">{sub}</div>' if sub else ""), unsafe_allow_html=True)


def period_label(months):
    if not months:
        return "No period"
    a, b = months[0], months[-1]
    return a.strftime("%b %Y") if a == b else f"{a.strftime('%b %Y')} to {b.strftime('%b %Y')}"


def to_excel(sheets: dict) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for name, frame in sheets.items():
            frame.to_excel(xw, sheet_name=name[:31])
    return buf.getvalue()


# ---------------------------------------------------------------- app
raw, src_name = get_source()
if raw is None:
    st.markdown('<div class="top"><div class="logo">GD</div><div><h1>Retail P&L Command Centre</h1>'
                '<div class="sub">Upload the P&L tracker in the sidebar to begin</div></div></div>', unsafe_allow_html=True)
    st.info("Upload **P_L_tracker_retail_New.xlsx** in the sidebar. The dashboard reads the Base sheet and builds every view from it.")
    st.stop()

try:
    DF = load_base(raw, hashlib.md5(raw).hexdigest())
except Exception as e:  # noqa: BLE001
    st.error(f"Couldn't read this file: {e}")
    st.stop()

ALL_MONTHS = sorted(DF["period"].unique())
ALL_MONTHS = [pd.Timestamp(m) for m in ALL_MONTHS]
SALES_MONTHS = sorted(pd.Timestamp(m) for m in DF.loc[DF.kind == "sales", "period"].unique())
LATEST = SALES_MONTHS[-1]
FYS = sorted(DF["fy"].cat.categories.tolist() if hasattr(DF["fy"], "cat") else DF["fy"].unique())
CUR_FY = DF.loc[DF.period == LATEST, "fy"].iloc[0]

# ---- sidebar: period
sb = st.sidebar
sb.markdown('<div class="side-h">Period</div>', unsafe_allow_html=True)
presets = [f"{CUR_FY} YTD", "Last 3 months", "Latest month"] + [f for f in reversed(FYS) if f != CUR_FY] + ["Custom range"]
preset = sb.selectbox("Period", presets, index=0, label_visibility="collapsed")
if preset.endswith("YTD"):
    sel = [m for m in SALES_MONTHS if DF.loc[DF.period == m, "fy"].iloc[0] == CUR_FY]
elif preset == "Last 3 months":
    sel = SALES_MONTHS[-3:]
elif preset == "Latest month":
    sel = [LATEST]
elif preset == "Custom range":
    lab = [m.strftime("%b %Y") for m in SALES_MONTHS]
    a, b = sb.select_slider("Months", options=lab, value=(lab[max(0, len(lab) - 6)], lab[-1]))
    sel = SALES_MONTHS[lab.index(a): lab.index(b) + 1]
else:
    sel = [m for m in SALES_MONTHS if DF.loc[DF.period == m, "fy"].iloc[0] == preset]

cmp_mode = sb.radio("Compare with", ["Same period last year", "Previous period", "No comparison"], index=0)
if cmp_mode == "Same period last year":
    cmp = [m - pd.DateOffset(years=1) for m in sel]
    CMP_LABEL = "vs LY"
elif cmp_mode == "Previous period":
    n = len(sel)
    cmp = [sel[0] - pd.DateOffset(months=n - i) for i in range(n)]
    CMP_LABEL = "vs prev"
else:
    cmp, CMP_LABEL = [], ""
cmp = [m for m in cmp if m in set(SALES_MONTHS)]

# ---- sidebar: team filters (apply to sales and cost rows)
sb.markdown('<div class="side-h">Sales team</div>', unsafe_allow_html=True)
rsm_opts = sorted(DF["rsm"].cat.categories)
f_rsm = sb.multiselect("RSM", rsm_opts, placeholder="All RSMs")
asm_pool = DF if not f_rsm else DF[DF.rsm.isin(f_rsm)]
asm_opts = sorted(asm_pool["asm"].dropna().unique())
f_asm = sb.multiselect("ASM / ASE", asm_opts, placeholder="All ASMs")

# ---- sidebar: commercial filters (sales rows only)
sb.markdown('<div class="side-h">Market and product</div>', unsafe_allow_html=True)
S = DF[DF.kind == "sales"]
f_zone = sb.multiselect("Zone", sorted(S.zone.unique()), placeholder="All zones")
f_state = sb.multiselect("State", sorted(S[S.zone.isin(f_zone)].state.unique() if f_zone else S.state.unique()), placeholder="All states")
f_chan = sb.multiselect("Sub-channel", sorted(S.sub_channel.unique()), placeholder="All channels")
f_l0 = sb.multiselect("Category", sorted(S.l0.unique()), placeholder="All categories")
f_l1 = sb.multiselect("Brand / range", sorted(S[S.l0.isin(f_l0)].l1.unique() if f_l0 else S.l1.unique()), placeholder="All ranges")
f_type = sb.multiselect("Sales / Sampling", sorted(S.type.unique()), placeholder="All types")
commercial = any([f_zone, f_state, f_chan, f_l0, f_l1, f_type])

sb.markdown('<div class="side-h">Data</div>', unsafe_allow_html=True)
sb.caption(f"Source: **{src_name}**  \nCovers {period_label(SALES_MONTHS)}")


def apply_filters(months, base=DF):
    d = base[base.period.isin(months)]
    if f_rsm:
        d = d[d.rsm.isin(f_rsm)]
    if f_asm:
        d = d[d.asm.isin(f_asm)]
    if commercial:
        d = d[d.kind == "sales"]
        for col, vals in [("zone", f_zone), ("state", f_state), ("sub_channel", f_chan), ("l0", f_l0), ("l1", f_l1), ("type", f_type)]:
            if vals:
                d = d[d[col].isin(vals)]
    return d


CUR = apply_filters(sel)
PRV = apply_filters(cmp) if cmp else CUR.iloc[0:0]
CUR_S, PRV_S = CUR[CUR.kind == "sales"], PRV[PRV.kind == "sales"]
T, P = totals(CUR), totals(PRV)
HAS_CMP = len(PRV) > 0

# ---- header
filters_txt = []
for lab, v in [("RSM", f_rsm), ("ASM", f_asm), ("Zone", f_zone), ("State", f_state), ("Channel", f_chan), ("Category", f_l0), ("Range", f_l1), ("Type", f_type)]:
    if v:
        filters_txt.append(f"{lab}: {', '.join(map(str, v[:2]))}{'…' if len(v) > 2 else ''}")
st.markdown(f"""<div class="top"><div class="logo">GD</div>
<div><h1>Retail P&L Command Centre</h1><div class="sub">{' · '.join(filters_txt) if filters_txt else 'All RSMs, regions and categories'}</div></div>
<div class="pill">📅 {period_label(sel)}{'  ·  ' + CMP_LABEL.replace('vs ', 'vs ') + ' ' + period_label(cmp) if HAS_CMP else ''}</div></div>""",
            unsafe_allow_html=True)

if commercial:
    st.markdown('<div class="note">Field team costs (salaries, travel, incentives, DB claims) are booked by RSM and ASM, not by region, '
                'product or channel. With these filters on, the dashboard shows margins up to <b>contribution</b>. '
                'Clear the market and product filters to see net margin.</div>', unsafe_allow_html=True)

PAGES = ["Overview", "P&L statement", "Sales team", "Products", "Customers & regions", "Returns & sampling", "Explorer"]
page = st.segmented_control("View", PAGES, default="Overview", label_visibility="collapsed", key="page") or "Overview"


def dlt(key, kind="pct"):
    if not HAS_CMP:
        return None
    if kind == "pct":
        return growth(T[key], P[key])
    return T[key] - P[key]


# ================================================================ OVERVIEW
def page_overview():
    k = [
        kpi("Revenue", inr(T.revenue), f"{T.qty:,.0f} units", dlt("revenue"), cmp_label=CMP_LABEL),
        kpi("Gross margin", inr(T.gm), f"{pct(T.gm_pct)} of revenue", dlt("gm_pct", "pts"), "pts", cmp_label=CMP_LABEL),
        kpi("Contribution", inr(T.contrib), f"{pct(T.contrib_pct)} after transport and opex", dlt("contrib"), cmp_label=CMP_LABEL),
    ]
    if not commercial:
        k += [
            kpi("Field team cost", inr(T.field), f"{pct(T.field_pct)} of revenue", dlt("field_pct", "pts"), "pts", good_up=False, cmp_label=CMP_LABEL),
            kpi("Net margin", inr(T.nm), f"{pct(T.nm_pct)} of revenue", dlt("nm_pct", "pts"), "pts", cmp_label=CMP_LABEL),
        ]
    else:
        k += [kpi("Active customers", f"{CUR_S[CUR_S.revenue > 0].customer.nunique():,}", "billed in period")]
    st.markdown('<div class="kpis">' + "".join(k) + "</div>", unsafe_allow_html=True)

    c1, c2 = st.columns([1.65, 1])
    with c1, st.container(border=True):
        card_head("Monthly performance", "Revenue bars with margin lines. Dotted line is the comparison period.")
        m = group_pl(CUR, "period").reindex(sel).fillna(0)
        m["gm_pct"] = m.gm / m.revenue.replace(0, np.nan)
        m["nm_pct"] = m.nm / m.revenue.replace(0, np.nan)
        x = [d.strftime("%b %y") for d in sel]
        fig = go.Figure()
        fig.add_bar(x=x, y=lakhs(m.revenue), name="Revenue (₹ L)", marker_color=INDIGO, marker_cornerradius=6,
                    hovertemplate="%{x}<br>Revenue ₹%{y:.1f} L<extra></extra>")
        if HAS_CMP:
            pm = group_pl(PRV, "period").reindex(cmp)
            if len(pm) == len(sel):
                fig.add_scatter(x=x, y=lakhs(pm.revenue.values), name=f"Revenue {CMP_LABEL.replace('vs ', '')}", mode="lines+markers",
                                line=dict(color="#94A3B8", dash="dot", width=2), hovertemplate="%{x}<br>Comparison ₹%{y:.1f} L<extra></extra>")
        fig.add_scatter(x=x, y=m.gm_pct * 100, name="GM %", yaxis="y2", mode="lines+markers", line=dict(color=SAFFRON, width=3),
                        hovertemplate="%{x}<br>GM %{y:.1f}%<extra></extra>")
        if not commercial:
            fig.add_scatter(x=x, y=m.nm_pct * 100, name="NM %", yaxis="y2", mode="lines+markers", line=dict(color=TEAL, width=3),
                            hovertemplate="%{x}<br>NM %{y:.1f}%<extra></extra>")
        fig.update_layout(yaxis=dict(title="₹ lakh"), yaxis2=dict(title="%", overlaying="y", side="right", showgrid=False, ticksuffix="%"), bargap=0.35)
        st.plotly_chart(style_fig(fig, 360), width="stretch", config=PLOT_CFG)

    with c2, st.container(border=True):
        card_head("Where the money goes", "From revenue to net margin")
        steps = [("Revenue", T.revenue, "absolute"), ("COGS", -T.cogs, "relative"), ("Gross margin", T.gm, "total"),
                 ("Transport", -T.transport, "relative"), ("Opex", -T.opex, "relative"), ("Contribution", T.contrib, "total")]
        if not commercial:
            steps += [("SO team", -T.so_cost, "relative"), ("ASM team", -T.asm_cost, "relative"), ("RSM", -T.rsm_cost, "relative"),
                      ("DB claim", -T.db_claim, "relative"), ("Net margin", T.nm, "total")]
        fig = go.Figure(go.Waterfall(x=[s[0] for s in steps], y=[lakhs(s[1]) for s in steps], measure=[s[2] for s in steps],
                                     connector=dict(line=dict(color=LINE)), increasing=dict(marker_color=GREEN),
                                     decreasing=dict(marker_color="#F87171"), totals=dict(marker_color=INDIGO),
                                     text=[f"{lakhs(s[1]):,.1f}" for s in steps], textposition="outside",
                                     hovertemplate="%{x}: ₹%{y:,.1f} L<extra></extra>"))
        fig.update_yaxes(title="₹ lakh")
        fig.update_traces(cliponaxis=False, textfont=dict(size=10))
        fig.update_xaxes(tickangle=-40)
        st.plotly_chart(style_fig(fig, 360, legend=False), width="stretch", config=PLOT_CFG)

    c3, c4 = st.columns([2.3, 1])
    with c3, st.container(border=True):
        card_head("RSM scorecard", "Sorted by revenue. Growth compares with the comparison period.")
        g = group_pl(CUR, "rsm")
        g = g[g.revenue.abs() + g.field > 0]
        out = pd.DataFrame({"RSM": g.index.astype(str), "Revenue (₹ L)": lakhs(g.revenue).round(1), "GM %": (g.gm_pct * 100).round(1)})
        if HAS_CMP:
            pg = group_pl(PRV, "rsm").reindex(g.index)
            out["Growth %"] = ((g.revenue - pg.revenue) / pg.revenue.abs() * 100).round(1).values
        if commercial:
            out["Contribution (₹ L)"] = lakhs(g.contrib).round(1).values
        if not commercial:
            out["Cost %"] = (g.field_pct * 100).round(1).values
            out["NM (₹ L)"] = lakhs(g.nm).round(1).values
            out["NM %"] = (g.nm_pct * 100).round(1).values
        out = out.sort_values("Revenue (₹ L)", ascending=False)
        mx = float(out["Revenue (₹ L)"].max() or 1)
        st.dataframe(out, hide_index=True, width="stretch", column_config={
            "Revenue (₹ L)": st.column_config.ProgressColumn(format="%.1f", min_value=0, max_value=mx, width="medium"),
            "GM %": st.column_config.NumberColumn(format="%.1f%%", width="small"), "Growth %": st.column_config.NumberColumn(format="%+.1f%%", width="small"),
            "Cost %": st.column_config.NumberColumn(format="%.1f%%", width="small", help="Field team cost as % of revenue"), "NM %": st.column_config.NumberColumn(format="%.1f%%", width="small"),
            "NM (₹ L)": st.column_config.NumberColumn(format="%.1f", width="small"),
        })

    with c4, st.container(border=True):
        card_head("What stands out", "Generated from the numbers in view")
        st.markdown(insights(), unsafe_allow_html=True)

    c5, c6 = st.columns(2)
    with c5, st.container(border=True):
        card_head("Revenue by category")
        g = CUR_S.groupby("l1", observed=True).agg(revenue=("revenue", "sum"), gm=("gm", "sum")).query("revenue > 0").sort_values("revenue")
        fig = go.Figure(go.Bar(y=g.index.astype(str), x=lakhs(g.revenue), orientation="h", marker_color=INDIGO, marker_cornerradius=5,
                               customdata=(g.gm / g.revenue * 100), text=[f"{v:,.1f} L" for v in lakhs(g.revenue)], textposition="outside",
                               hovertemplate="%{y}<br>₹%{x:.1f} L · GM %{customdata:.1f}%<extra></extra>"))
        fig.update_traces(cliponaxis=False)
        fig.update_xaxes(title="₹ lakh", range=[0, float(lakhs(g.revenue).max() or 1) * 1.18])
        st.plotly_chart(style_fig(fig, 340, legend=False), width="stretch", config=PLOT_CFG)
    with c6, st.container(border=True):
        card_head("Revenue by zone")
        g = CUR_S.groupby("zone", observed=True)["revenue"].sum().loc[lambda s: s > 0].sort_values(ascending=False)
        fig = go.Figure(go.Pie(labels=g.index.astype(str), values=g.values, hole=0.62, marker=dict(colors=SERIES),
                               textinfo="label+percent", hovertemplate="%{label}: ₹%{value:,.0f}<extra></extra>"))
        fig.add_annotation(text=f"<b>{inr(g.sum(), 1)}</b><br><span style='color:{MUTED}'>total</span>", showarrow=False, font=dict(size=15))
        st.plotly_chart(style_fig(fig, 340, legend=False), width="stretch", config=PLOT_CFG)


def insights():
    items = []

    def add(icon, bg, html):
        items.append(f'<div class="insight"><div class="ic" style="background:{bg}">{icon}</div><div>{html}</div></div>')

    if HAS_CMP and P.revenue:
        gr = growth(T.revenue, P.revenue)
        word = "flat" if abs(gr) < 0.005 else f"{'up' if gr >= 0 else 'down'} {abs(gr)*100:.1f}%"
        add("📈" if gr >= 0 else "📉", "#E0E7FF", f"Revenue is <b>{word}</b> {CMP_LABEL} "
            f"({inr(T.revenue)} against {inr(P.revenue)}).")
    if not commercial:
        g = group_pl(CUR, "rsm")
        g = g[g.revenue > T.revenue * 0.02]
        if len(g) >= 2:
            b, w = g.nm_pct.idxmax(), g.nm_pct.idxmin()
            add("🏆", "#DCFCE7", f"<b>{b}</b> runs the healthiest territory at <b>{pct(g.nm_pct[b])}</b> net margin.")
            if g.nm_pct[w] < 0.05:
                add("⚠️", "#FEE2E2", f"<b>{w}</b> is at <b>{pct(g.nm_pct[w])}</b> net margin, with field cost at {pct(g.field_pct[w])} of revenue.")
    if HAS_CMP:
        a = CUR_S.groupby("l1", observed=True)["revenue"].sum()
        b = PRV_S.groupby("l1", observed=True)["revenue"].sum()
        ch = a.sub(b, fill_value=0).sort_values()
        if len(ch) and ch.iloc[-1] > 0:
            add("🚀", "#FEF3C7", f"<b>{ch.index[-1]}</b> added the most revenue: <b>{inr(ch.iloc[-1])}</b> {CMP_LABEL}.")
        if len(ch) and ch.iloc[0] < 0:
            add("🔻", "#FEE2E2", f"<b>{ch.index[0]}</b> lost the most: <b>{inr(ch.iloc[0])}</b> {CMP_LABEL}.")
    cr = CUR_S.groupby("customer")["revenue"].sum().sort_values(ascending=False)
    if cr.sum() > 0:
        add("👥", "#E0F2FE", f"Top 10 customers bring <b>{pct(cr.head(10).sum()/cr.sum())}</b> of revenue across {int((cr > 0).sum())} billed customers.")
    ret = -CUR_S.loc[CUR_S.is_return, "revenue"].sum()
    gross = CUR_S.loc[~CUR_S.is_return & (CUR_S.type == "Sales"), "revenue"].sum()
    if gross:
        add("↩️", "#F1F5F9", f"Returns took back <b>{inr(ret)}</b>, or <b>{pct(ret/gross)}</b> of gross sales.")
    samp = CUR_S.loc[CUR_S.type != "Sales", "cogs"].sum()
    if samp:
        add("🎁", "#FCE7F3", f"Sampling and trade marketing cost <b>{inr(samp)}</b> in product, {pct(samp/T.revenue)} of revenue.")
    return "".join(items) or "<div class='card-s'>Not enough data in this view.</div>"


# ================================================================ P&L STATEMENT
PL_LINES = [
    ("Revenue", "revenue", "sub"), ("Cost of goods sold", "cogs", "ind"), ("Gross margin", "gm", "sub"), ("Gross margin %", "gm_pct", "pct"),
    ("Transport", "transport", "ind"), ("Operating expenses", "opex", "ind"), ("Contribution", "contrib", "sub"), ("Contribution %", "contrib_pct", "pct"),
    ("SO salary", "so_salary", "ind"), ("SO travel", "so_travel", "ind"), ("SO incentive", "so_incentive", "ind"),
    ("ASM salary", "asm_salary", "ind"), ("ASM travel", "asm_travel", "ind"), ("ASM incentive", "asm_incentive", "ind"),
    ("RSM salary", "rsm_salary", "ind"), ("RSM travel", "rsm_travel", "ind"), ("RSM incentive", "rsm_incentive", "ind"),
    ("DB claim", "db_claim", "ind"), ("Total field cost", "field", "sub"), ("Field cost %", "field_pct", "pct"),
    ("Net margin", "nm", "total"), ("Net margin %", "nm_pct", "pct"),
]


def pl_matrix(d, by):
    g = group_pl(d, by)
    if by == "period":
        g = g.reindex([m for m in sel if m in g.index])
        g.index = [m.strftime("%b %y") for m in g.index]
    else:
        g = g[(g.revenue.abs() + g.field) > 0].sort_values("revenue", ascending=False)
        g.index = g.index.astype(str)
    tot = totals(d)
    g.loc["Total"] = tot[g.columns]
    return g


def page_pl():
    c1, c2, c3 = st.columns([1.3, 1, 1])
    by_lab = c1.segmented_control("Columns", ["Month", "RSM", "ASM", "Financial year"], default="Month", key="pl_by") or "Month"
    unit = c2.segmented_control("Show", ["₹ lakh", "₹", "% of revenue"], default="₹ lakh", key="pl_unit") or "₹ lakh"
    by = {"Month": "period", "RSM": "rsm", "ASM": "asm", "Financial year": "fy"}[by_lab]
    d = CUR if by != "fy" else apply_filters([m for m in SALES_MONTHS])
    if by == "fy":
        st.caption("Financial year view ignores the period picker and shows every year in the file.")
    lines = PL_LINES if not commercial else [l for l in PL_LINES if l[1] in ("revenue", "cogs", "gm", "gm_pct", "transport", "opex", "contrib", "contrib_pct")]
    g = pl_matrix(d, by)
    cols = list(g.index)
    html = ['<div class="plwrap"><table class="pl"><thead><tr><th>Line item</th>' + "".join(f"<th>{c}</th>" for c in cols) + "</tr></thead><tbody>"]
    for name, key, kind in lines:
        tds = []
        for c in cols:
            v = g.at[c, key]
            if kind == "pct":
                txt = pct(v)
            elif unit == "% of revenue":
                txt = pct(div(v, g.at[c, "revenue"]))
            elif unit == "₹":
                txt = f"{v:,.0f}"
            else:
                txt = f"{v/1e5:,.2f}"
            cls = (" neg" if (np.isfinite(v) and v < 0 and key in ("gm", "contrib", "nm", "gm_pct", "contrib_pct", "nm_pct")) else "") + (" tot" if c == "Total" else "")
            tds.append(f'<td class="{cls.strip()}">{txt}</td>')
        html.append(f'<tr class="{kind}"><td>{name}</td>{"".join(tds)}</tr>')
    html.append("</tbody></table></div>")
    st.markdown("".join(html), unsafe_allow_html=True)

    out = pd.DataFrame({name: g[key] for name, key, _ in lines}).T
    c3.download_button("⬇ Download P&L (Excel)", to_excel({"P&L": out}), file_name=f"GO_DESi_PL_{by_lab}_{period_label(sel).replace(' ', '_')}.xlsx",
                       width="stretch")
    st.caption("Field cost lines and net margin match the YTD & L3M Summary pivot in the tracker.")


# ================================================================ SALES TEAM
def page_team():
    if commercial:
        st.markdown('<div class="note">Clear the market and product filters to see field costs by RSM and ASM.</div>', unsafe_allow_html=True)
    g = group_pl(CUR, "rsm")
    g = g[(g.revenue + g.field) > 0]
    cards = []
    for r, row in g.sort_values("revenue", ascending=False).iterrows():
        gr = None
        if HAS_CMP:
            pv = PRV[PRV.rsm == r].revenue.sum()
            gr = growth(row.revenue, pv) if pv else None
        cards.append(kpi(str(r), inr(row.revenue), f"GM {pct(row.gm_pct)}" + ("" if commercial else f" · NM <b>{pct(row.nm_pct)}</b>"), gr, cmp_label=CMP_LABEL))
    st.markdown('<div class="kpis">' + "".join(cards) + "</div>", unsafe_allow_html=True)

    c1, c2 = st.columns([1.2, 1])
    with c1, st.container(border=True):
        card_head("ASM map: size vs profitability", "Bubble size is field cost. Top-right is big and profitable.")
        a = group_pl(CUR, ["rsm", "asm"]).reset_index()
        a = a[a.revenue > 0]
        ycol, ylab = ("nm_pct", "Net margin %") if not commercial else ("gm_pct", "Gross margin %")
        fig = px.scatter(a, x=lakhs(a.revenue), y=a[ycol] * 100, size=a.field.clip(lower=1) if not commercial else a.revenue.clip(lower=1),
                         color="rsm", hover_name="asm", size_max=42, color_discrete_sequence=SERIES,
                         custom_data=["asm", "rsm"])
        fig.update_traces(hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<br>Revenue ₹%{x:.1f} L<br>" + ylab + " %{y:.1f}%<extra></extra>")
        fig.add_hline(y=0, line_color="#CBD5E1")
        yv = a[ycol] * 100
        lo = max(float(yv.min()), -40.0) - 3
        hidden = int((yv < -40).sum())
        fig.update_yaxes(range=[lo, float(yv.max()) + 5])
        if hidden:
            fig.add_annotation(x=0, xref="paper", y=lo, yref="y", xanchor="left", yanchor="bottom", showarrow=False,
                               text=f"{hidden} ASM(s) below -40% not shown: cost with little or no revenue", font=dict(color=RED, size=11))
        fig.update_layout(xaxis_title="Revenue (₹ lakh)", yaxis_title=ylab, legend_title_text="")
        st.plotly_chart(style_fig(fig, 420), width="stretch", config=PLOT_CFG)
    with c2, st.container(border=True):
        card_head("Field cost build-up by RSM", "Salary, travel and incentives at each level")
        if commercial:
            st.caption("Not available with market or product filters on.")
        else:
            parts = [("SO salary", "so_salary"), ("SO travel + incentive", None), ("ASM", "asm_cost"), ("RSM", "rsm_cost"), ("DB claim", "db_claim")]
            gg = g.sort_values("revenue")
            fig = go.Figure()
            vals = {"SO salary": gg.so_salary, "SO travel + incentive": gg.so_travel + gg.so_incentive, "ASM": gg.asm_cost, "RSM": gg.rsm_cost, "DB claim": gg.db_claim}
            for i, (nm_, _) in enumerate(parts):
                fig.add_bar(y=gg.index.astype(str), x=lakhs(vals[nm_]), name=nm_, orientation="h", marker_color=SERIES[i],
                            hovertemplate="%{y}<br>" + nm_ + " ₹%{x:.1f} L<extra></extra>")
            fig.update_layout(barmode="stack", xaxis_title="₹ lakh")
            for y, r in zip(gg.index.astype(str), gg.itertuples()):
                fig.add_annotation(x=lakhs(r.field), y=y, text=f"  {pct(r.field_pct)} of rev", showarrow=False, xanchor="left", font=dict(color=MUTED, size=11))
            st.plotly_chart(style_fig(fig, 420), width="stretch", config=PLOT_CFG)

    with st.container(border=True):
        card_head("ASM / ASE league table", "Click a column header to sort")
        a = group_pl(CUR, ["rsm", "asm"]).reset_index()
        a = a[(a.revenue + a.field) > 0]
        out = pd.DataFrame({"ASM / ASE": a.asm.astype(str), "RSM": a.rsm.astype(str), "Revenue (₹ L)": lakhs(a.revenue).round(2),
                            "GM %": (a.gm_pct * 100).round(1), "Contribution (₹ L)": lakhs(a.contrib).round(2)})
        if HAS_CMP:
            pa = PRV.groupby(["rsm", "asm"], observed=True).revenue.sum()
            prev = [pa.get((r, s), 0) for r, s in zip(a.rsm, a.asm)]
            out["Growth %"] = [round(growth(c, p) * 100, 1) if p else None for c, p in zip(a.revenue, prev)]
        if not commercial:
            out["Field cost (₹ L)"] = lakhs(a.field).round(2).values
            out["Field cost %"] = (a.field_pct * 100).round(1).values
            out["Net margin (₹ L)"] = lakhs(a.nm).round(2).values
            out["NM %"] = (a.nm_pct * 100).round(1).values
        out = out.sort_values("Revenue (₹ L)", ascending=False)
        st.dataframe(out, hide_index=True, width="stretch", height=420, column_config={
            "Revenue (₹ L)": st.column_config.ProgressColumn(format="%.2f", min_value=0, max_value=float(out["Revenue (₹ L)"].max() or 1)),
            "GM %": st.column_config.NumberColumn(format="%.1f%%"), "Growth %": st.column_config.NumberColumn(format="%+.1f%%"),
            "Field cost %": st.column_config.NumberColumn(format="%.1f%%"), "NM %": st.column_config.NumberColumn(format="%.1f%%")})

    with st.container(border=True):
        card_head("Drill into one RSM", "Monthly revenue and net margin for the RSM and their ASMs")
        rs = st.selectbox("RSM", [str(x) for x in g.sort_values("revenue", ascending=False).index], key="drill_rsm")
        d = CUR[CUR.rsm == rs]
        m = group_pl(d, ["period", "asm"]).reset_index()
        m = m[m.revenue > 0]
        m["Month"] = m.period.dt.strftime("%b %y")
        fig = px.bar(m, x="Month", y=lakhs(m.revenue), color="asm", color_discrete_sequence=SERIES,
                     category_orders={"Month": [p.strftime("%b %y") for p in sel]})
        fig.update_traces(marker_cornerradius=3, hovertemplate="%{x}<br>₹%{y:.1f} L<extra>%{fullData.name}</extra>")
        tot = group_pl(d, "period").reindex(sel)
        if not commercial:
            fig.add_scatter(x=[p.strftime("%b %y") for p in sel], y=tot.nm_pct * 100, name="NM %", yaxis="y2", mode="lines+markers",
                            line=dict(color=INK, width=3), hovertemplate="%{x}<br>NM %{y:.1f}%<extra></extra>")
            fig.update_layout(yaxis2=dict(overlaying="y", side="right", ticksuffix="%", showgrid=False))
        fig.update_layout(barmode="stack", yaxis_title="₹ lakh", legend_title_text="")
        st.plotly_chart(style_fig(fig, 380), width="stretch", config=PLOT_CFG)


# ================================================================ PRODUCTS
def page_products():
    S_ = CUR_S[CUR_S.type == "Sales"] if not f_type else CUR_S
    c1, c2 = st.columns([1.3, 1])
    with c1, st.container(border=True):
        card_head("Portfolio map", "Box size is revenue, colour is gross margin %. Click a box to zoom in.")
        t = S_.groupby(["l0", "l1", "l2"], observed=True).agg(revenue=("revenue", "sum"), gm=("gm", "sum")).reset_index()
        t = t[t.revenue > 0]
        t["gm_pct"] = t.gm / t.revenue * 100
        fig = px.treemap(t, path=[px.Constant("All products"), "l0", "l1", "l2"], values="revenue", color="gm_pct",
                         color_continuous_scale=[[0, "#FCA5A5"], [0.5, "#FDE68A"], [1, "#4ADE80"]],
                         range_color=[max(0, t.gm_pct.quantile(0.05)), t.gm_pct.quantile(0.95)])
        fig.update_traces(hovertemplate="<b>%{label}</b><br>₹%{value:,.0f}<br>GM %{color:.1f}%<extra></extra>", marker_cornerradius=4)
        fig.update_layout(coloraxis_colorbar=dict(title="GM %", thickness=10))
        st.plotly_chart(style_fig(fig, 460, legend=False), width="stretch", config=PLOT_CFG)
    with c2, st.container(border=True):
        card_head("SKU matrix", "Each dot is a SKU. Dashed lines are the averages.")
        s = S_.groupby("sku").agg(revenue=("revenue", "sum"), gm=("gm", "sum"), l1=("l1", "first")).query("revenue > 0").reset_index()
        s["gm_pct"] = s.gm / s.revenue * 100
        fig = px.scatter(s, x=lakhs(s.revenue), y="gm_pct", color="l1", hover_name="sku", log_x=True, color_discrete_sequence=SERIES)
        fig.update_traces(marker=dict(size=10, line=dict(width=1, color="white")),
                          hovertemplate="<b>%{hovertext}</b><br>₹%{x:.2f} L<br>GM %{y:.1f}%<extra></extra>")
        if len(s):
            fig.add_hline(y=div(s.gm.sum(), s.revenue.sum()) * 100, line_dash="dash", line_color="#94A3B8")
            fig.add_vline(x=lakhs(s.revenue.median()), line_dash="dash", line_color="#94A3B8")
        fig.update_layout(xaxis_title="Revenue (₹ lakh, log scale)", yaxis_title="GM %", legend_title_text="")
        st.plotly_chart(style_fig(fig, 460), width="stretch", config=PLOT_CFG)

    with st.container(border=True):
        card_head("SKU performance", "Search, sort, and download")
        s = S_.groupby(["l1", "l2", "sku"], observed=True).agg(revenue=("revenue", "sum"), gm=("gm", "sum"), qty=("qty", "sum")).reset_index()
        s = s[s.revenue != 0]
        if HAS_CMP:
            ps = (PRV_S[PRV_S.type == "Sales"] if not f_type else PRV_S).groupby("sku").revenue.sum()
            s["prev"] = s.sku.map(ps).fillna(0)
        out = pd.DataFrame({"SKU": s.sku, "Range": s.l1.astype(str), "Category": s.l2.astype(str), "Units": s.qty.round(0),
                            "Revenue (₹ L)": lakhs(s.revenue).round(2), "Avg price (₹)": (s.revenue / s.qty.replace(0, np.nan)).round(1),
                            "GM %": (s.gm / s.revenue * 100).round(1)})
        if HAS_CMP:
            out["Growth %"] = [round(growth(c, p) * 100, 1) if p else None for c, p in zip(s.revenue, s.prev)]
        out["Share %"] = (s.revenue / s.revenue.sum() * 100).round(2)
        out = out.sort_values("Revenue (₹ L)", ascending=False)
        q = st.text_input("Search SKU", placeholder="Type part of a SKU name", key="sku_q", label_visibility="collapsed")
        if q:
            out = out[out.SKU.str.contains(q, case=False, na=False)]
        st.dataframe(out, hide_index=True, width="stretch", height=430, column_config={
            "Revenue (₹ L)": st.column_config.ProgressColumn(format="%.2f", min_value=0, max_value=float(out["Revenue (₹ L)"].max() if len(out) else 1)),
            "GM %": st.column_config.NumberColumn(format="%.1f%%"), "Growth %": st.column_config.NumberColumn(format="%+.1f%%"),
            "Share %": st.column_config.NumberColumn(format="%.2f%%"), "Units": st.column_config.NumberColumn(format="%d")})
        st.download_button("⬇ Download SKU table", to_excel({"SKUs": out.set_index("SKU")}), file_name="GO_DESi_SKU_performance.xlsx")

    c3, c4 = st.columns(2)
    with c3, st.container(border=True):
        card_head("Range trend", "Monthly revenue by range")
        m = S_.groupby(["period", "l1"], observed=True).revenue.sum().reset_index()
        m = m[m.revenue > 0]
        m["Month"] = m.period.dt.strftime("%b %y")
        fig = px.area(m, x="Month", y=lakhs(m.revenue), color="l1", color_discrete_sequence=SERIES,
                      category_orders={"Month": [p.strftime("%b %y") for p in sel]})
        fig.update_traces(hovertemplate="%{x}<br>₹%{y:.1f} L<extra>%{fullData.name}</extra>")
        fig.update_layout(yaxis_title="₹ lakh", legend_title_text="")
        st.plotly_chart(style_fig(fig, 360), width="stretch", config=PLOT_CFG)
    with c4, st.container(border=True):
        card_head("Pack type mix", "Share of revenue and margin by pack format")
        p = S_.groupby("pack", observed=True).agg(revenue=("revenue", "sum"), gm=("gm", "sum")).query("revenue > 0").sort_values("revenue", ascending=False)
        p.index = p.index.astype(str).str.replace("^0(\\.0)?$", "Not set", regex=True)
        fig = go.Figure()
        fig.add_bar(x=p.index, y=lakhs(p.revenue), name="Revenue (₹ L)", marker_color=INDIGO, marker_cornerradius=5)
        fig.add_scatter(x=p.index, y=p.gm / p.revenue * 100, name="GM %", yaxis="y2", mode="markers+lines", line=dict(color=SAFFRON, width=3))
        fig.update_layout(yaxis_title="₹ lakh", yaxis2=dict(overlaying="y", side="right", ticksuffix="%", showgrid=False))
        st.plotly_chart(style_fig(fig, 360), width="stretch", config=PLOT_CFG)


# ================================================================ CUSTOMERS & REGIONS
def page_customers():
    c = CUR_S.groupby("customer").agg(revenue=("revenue", "sum"), gm=("gm", "sum"), state=("state", "first"), rsm=("rsm", "first"),
                                      last=("date", "max"), invoices=("invoice", "nunique")).reset_index()
    billed = c[c.revenue > 0]
    prev_c = PRV_S.groupby("customer").revenue.sum() if HAS_CMP else pd.Series(dtype=float)
    new = billed[~billed.customer.isin(prev_c[prev_c > 0].index)] if HAS_CMP else billed.iloc[0:0]
    lost = prev_c[(prev_c > 0) & ~prev_c.index.isin(billed.customer)] if HAS_CMP else prev_c
    top10 = billed.revenue.nlargest(10).sum() / billed.revenue.sum() if len(billed) else np.nan
    st.markdown('<div class="kpis">' + "".join([
        kpi("Billed customers", f"{len(billed):,}", "with revenue in period",
            growth(len(billed), int((prev_c > 0).sum())) if HAS_CMP else None, cmp_label=CMP_LABEL),
        kpi("Revenue per customer", inr(div(billed.revenue.sum(), len(billed))), "average in period"),
        kpi("Top 10 share", pct(top10), "of revenue from 10 customers"),
        kpi("New customers", f"{len(new):,}", f"{inr(new.revenue.sum())} revenue" if HAS_CMP else "needs a comparison"),
        kpi("Not billed again", f"{len(lost):,}", f"{inr(lost.sum())} in comparison period" if HAS_CMP else "needs a comparison"),
    ]) + "</div>", unsafe_allow_html=True)

    c1, c2 = st.columns([1, 1.25])
    with c1, st.container(border=True):
        card_head("States", "Revenue and gross margin by state")
        s = CUR_S.groupby(["zone", "state"], observed=True).agg(revenue=("revenue", "sum"), gm=("gm", "sum")).reset_index()
        s = s[s.revenue > 0].sort_values("revenue", ascending=False).head(15).sort_values("revenue")
        fig = go.Figure(go.Bar(y=s.state.astype(str), x=lakhs(s.revenue), orientation="h", marker_cornerradius=5,
                               marker=dict(color=s.gm / s.revenue * 100, colorscale=[[0, "#FCA5A5"], [0.5, "#FDE68A"], [1, "#4ADE80"]],
                                           colorbar=dict(title="GM %", thickness=10)),
                               customdata=np.c_[s.zone.astype(str), s.gm / s.revenue * 100],
                               hovertemplate="%{y} (%{customdata[0]})<br>₹%{x:.1f} L · GM %{customdata[1]:.1f}%<extra></extra>"))
        fig.update_xaxes(title="₹ lakh")
        st.plotly_chart(style_fig(fig, 470, legend=False), width="stretch", config=PLOT_CFG)
    with c2, st.container(border=True):
        card_head("Customer concentration", "How much revenue the top customers carry")
        r = billed.revenue.sort_values(ascending=False).reset_index(drop=True)
        cum = r.cumsum() / r.sum() * 100
        fig = go.Figure()
        fig.add_bar(x=list(range(1, min(len(r), 40) + 1)), y=lakhs(r.head(40)), name="Revenue (₹ L)", marker_color=INDIGO, marker_cornerradius=3,
                    customdata=billed.sort_values("revenue", ascending=False).customer.head(40),
                    hovertemplate="#%{x} %{customdata}<br>₹%{y:.1f} L<extra></extra>")
        fig.add_scatter(x=list(range(1, len(r) + 1)), y=cum, name="Cumulative %", yaxis="y2", line=dict(color=SAFFRON, width=3),
                        hovertemplate="Top %{x} customers: %{y:.1f}%<extra></extra>")
        n80 = int((cum < 80).sum()) + 1 if len(cum) else 0
        fig.add_annotation(x=n80, y=80, yref="y2", text=f"{n80} customers = 80%", showarrow=True, arrowhead=2, ax=40, ay=-30)
        fig.update_xaxes(range=[0.4, max(10, min(len(r), n80 * 1.6 if n80 else 40))])
        fig.update_layout(xaxis_title="Customer rank", yaxis_title="₹ lakh", yaxis2=dict(overlaying="y", side="right", range=[0, 102], ticksuffix="%", showgrid=False))
        st.plotly_chart(style_fig(fig, 470), width="stretch", config=PLOT_CFG)

    with st.container(border=True):
        card_head("Customer list", "Search any distributor. Growth compares with the comparison period.")
        out = pd.DataFrame({"Customer": c.customer, "State": c.state.astype(str), "RSM": c.rsm.astype(str), "Revenue (₹ L)": lakhs(c.revenue).round(2),
                            "GM %": (c.gm / c.revenue.replace(0, np.nan) * 100).round(1), "Invoices": c.invoices, "Last billed": c["last"].dt.date})
        if HAS_CMP:
            out["Prev (₹ L)"] = lakhs(c.customer.map(prev_c).fillna(0)).round(2).values
            out["Growth %"] = [round(growth(a, b) * 100, 1) if b else None for a, b in zip(c.revenue, c.customer.map(prev_c).fillna(0))]
        out = out.sort_values("Revenue (₹ L)", ascending=False)
        q = st.text_input("Search customer", placeholder="Type part of a customer name", key="cust_q", label_visibility="collapsed")
        if q:
            out = out[out.Customer.str.contains(q, case=False, na=False)]
        st.dataframe(out, hide_index=True, width="stretch", height=420, column_config={
            "Revenue (₹ L)": st.column_config.ProgressColumn(format="%.2f", min_value=0, max_value=float(out["Revenue (₹ L)"].max() if len(out) else 1)),
            "GM %": st.column_config.NumberColumn(format="%.1f%%"), "Growth %": st.column_config.NumberColumn(format="%+.1f%%")})
        st.download_button("⬇ Download customer table", to_excel({"Customers": out.set_index("Customer")}), file_name="GO_DESi_customers.xlsx")

    c3, c4 = st.columns(2)
    with c3, st.container(border=True):
        card_head("Active customers each month", "Distinct customers billed")
        a = CUR_S[CUR_S.revenue > 0].groupby("period").customer.nunique().reindex(sel).fillna(0)
        fig = go.Figure(go.Scatter(x=[p.strftime("%b %y") for p in sel], y=a.values, mode="lines+markers+text", text=a.astype(int).values,
                                   textposition="top center", line=dict(color=TEAL, width=3), fill="tozeroy", fillcolor="rgba(14,159,154,0.10)", cliponaxis=False))
        fig.update_yaxes(range=[0, float(a.max() or 1) * 1.2])
        st.plotly_chart(style_fig(fig, 320, legend=False), width="stretch", config=PLOT_CFG)
    with c4, st.container(border=True):
        card_head("Not billed this period", "Billed in the comparison period, nothing in this one. Worth a call.")
        if HAS_CMP and len(lost):
            lt = pd.DataFrame({"Customer": lost.index, "Comparison revenue (₹ L)": lakhs(lost.values).round(2)}).sort_values("Comparison revenue (₹ L)", ascending=False)
            st.dataframe(lt, hide_index=True, width="stretch", height=300)
        else:
            st.caption("No lapsed customers, or no comparison period selected.")


# ================================================================ RETURNS & SAMPLING
def page_returns():
    sales = CUR_S[CUR_S.type == "Sales"]
    gross = sales.loc[~sales.is_return, "revenue"].sum()
    ret = -sales.loc[sales.is_return, "revenue"].sum()
    samp = CUR_S.loc[CUR_S.type == "Sampling", "cogs"].sum()
    tm = CUR_S.loc[CUR_S.type == "Trade Marketing", "cogs"].sum()
    st.markdown('<div class="kpis">' + "".join([
        kpi("Gross sales", inr(gross), "before returns"),
        kpi("Returns", inr(ret), f"{pct(div(ret, gross))} of gross sales"),
        kpi("Sampling cost", inr(samp), f"{pct(div(samp, T.revenue))} of revenue"),
        kpi("Trade marketing", inr(tm), f"{pct(div(tm, T.revenue))} of revenue"),
        kpi("Transport", inr(T.transport), f"{pct(div(T.transport, T.revenue))} of revenue"),
    ]) + "</div>", unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1, st.container(border=True):
        card_head("Returns trend", "Return value and return rate by month")
        g = sales.groupby(["period", "is_return"]).revenue.sum().unstack(fill_value=0).reindex(sel).fillna(0)
        gr_ = g.get(False, pd.Series(0, index=g.index))
        rt = -g.get(True, pd.Series(0, index=g.index))
        x = [p.strftime("%b %y") for p in sel]
        fig = go.Figure()
        fig.add_bar(x=x, y=lakhs(rt), name="Returns (₹ L)", marker_color="#F87171", marker_cornerradius=5)
        fig.add_scatter(x=x, y=rt / gr_.replace(0, np.nan) * 100, name="Return rate %", yaxis="y2", line=dict(color=INK, width=3))
        fig.update_layout(yaxis_title="₹ lakh", yaxis2=dict(overlaying="y", side="right", ticksuffix="%", showgrid=False))
        st.plotly_chart(style_fig(fig, 340), width="stretch", config=PLOT_CFG)
    with c2, st.container(border=True):
        card_head("Sampling and trade marketing by RSM", "Product cost given away, against revenue")
        g = CUR_S.groupby("rsm", observed=True).apply(lambda d: pd.Series({
            "Sampling": d.loc[d.type == "Sampling", "cogs"].sum(), "Trade Marketing": d.loc[d.type == "Trade Marketing", "cogs"].sum(),
            "rev": d.revenue.sum()}), include_groups=False)
        g = g[(g.Sampling + g["Trade Marketing"]) > 0].sort_values("rev")
        fig = go.Figure()
        fig.add_bar(y=g.index.astype(str), x=lakhs(g.Sampling), name="Sampling", orientation="h", marker_color=SAFFRON)
        fig.add_bar(y=g.index.astype(str), x=lakhs(g["Trade Marketing"]), name="Trade marketing", orientation="h", marker_color="#8B5CF6")
        for y, r in zip(g.index.astype(str), g.itertuples()):
            fig.add_annotation(x=lakhs(r.Sampling + r[2]), y=y, text=f"  {pct(div(r.Sampling + r[2], r.rev))} of rev", showarrow=False, xanchor="left",
                               font=dict(color=MUTED, size=11))
        fig.update_layout(barmode="stack", xaxis_title="₹ lakh")
        st.plotly_chart(style_fig(fig, 340), width="stretch", config=PLOT_CFG)

    c3, c4 = st.columns(2)
    with c3, st.container(border=True):
        card_head("Top returning customers")
        r = sales[sales.is_return].groupby("customer").revenue.sum().mul(-1).nlargest(12)
        gs = sales[~sales.is_return].groupby("customer").revenue.sum()
        st.dataframe(pd.DataFrame({"Customer": r.index, "Returns (₹ L)": lakhs(r.values).round(2),
                                   "Return rate %": (r / r.index.map(gs).fillna(np.nan) * 100).round(1).values}),
                     hide_index=True, width="stretch", column_config={"Return rate %": st.column_config.NumberColumn(format="%.1f%%")})
    with c4, st.container(border=True):
        card_head("Top returned SKUs")
        r = sales[sales.is_return].groupby("sku").agg(v=("revenue", "sum"), q=("qty", "sum"))
        r = r.assign(v=-r.v, q=-r.q).nlargest(12, "v")
        st.dataframe(pd.DataFrame({"SKU": r.index, "Units": r.q.round(0).values, "Returns (₹ L)": lakhs(r.v).round(2).values}), hide_index=True, width="stretch")


# ================================================================ EXPLORER
DIMS = {"Month": "period", "Financial year": "fy", "RSM": "rsm", "ASM": "asm", "Zone": "zone", "State": "state", "City": "city",
        "Sub-channel": "sub_channel", "Customer group": "cust_group", "Customer": "customer", "Category": "l0", "Range": "l1",
        "Sub-category": "l2", "SKU": "sku", "Pack type": "pack", "Sales / Sampling": "type"}
MEASURES = {"Revenue": "revenue", "Gross margin": "gm", "GM %": "gm_pct", "COGS": "cogs", "Units": "qty", "Transport": "transport",
            "Contribution": "contrib", "Field cost": "field", "Net margin": "nm", "NM %": "nm_pct"}
TEAM_DIMS = {"period", "fy", "rsm", "asm"}


def page_explorer():
    st.markdown('<div class="card-s">Build any cut of the data. Pick rows, an optional column split, and a measure.</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    rlab = c1.selectbox("Rows", list(DIMS), index=2)
    clab = c2.selectbox("Columns", ["(none)"] + list(DIMS), index=1)
    mlab = c3.selectbox("Measure", list(MEASURES), index=0)
    unit = c4.selectbox("Units", ["₹ lakh", "₹"], index=0)
    rk, ck, mk = DIMS[rlab], (DIMS[clab] if clab != "(none)" else None), MEASURES[mlab]
    keys = [rk] + ([ck] if ck else [])
    people = mk in ("field", "nm", "nm_pct")
    if people and (commercial or not set(keys) <= TEAM_DIMS):
        st.markdown('<div class="note">Field cost and net margin can only be split by Month, Financial year, RSM or ASM, '
                    'and only with market and product filters cleared.</div>', unsafe_allow_html=True)
        return
    d = CUR if (people or set(keys) <= TEAM_DIMS) else CUR_S
    g = group_pl(d, keys)
    v = g[mk]
    if mk not in ("gm_pct", "nm_pct", "qty") and unit == "₹ lakh":
        v = v / 1e5
    if ck:
        tab = v.unstack(ck)
    else:
        tab = v.to_frame(mlab)
    if rk == "period":
        tab.index = [p.strftime("%b %y") for p in tab.index]
    if ck == "period":
        tab.columns = [p.strftime("%b %y") for p in tab.columns]
    tab = tab.loc[:, tab.notna().any()]
    if mk in ("gm_pct", "nm_pct"):
        tab = (tab * 100).round(1)
    else:
        if ck:
            tab["Total"] = tab.sum(axis=1)
        tab = tab.round(2)
        if rk != "period":
            tab = tab.sort_values(tab.columns[-1], ascending=False)
    tab.index.name = rlab
    st.dataframe(tab, width="stretch", height=min(560, 36 * (len(tab) + 1) + 4))
    st.download_button("⬇ Download this table", to_excel({"Explorer": tab}), file_name=f"GO_DESi_{rlab}_by_{clab}_{mlab}.xlsx".replace(" ", "_"))


{"Overview": page_overview, "P&L statement": page_pl, "Sales team": page_team, "Products": page_products,
 "Customers & regions": page_customers, "Returns & sampling": page_returns, "Explorer": page_explorer}[page]()
