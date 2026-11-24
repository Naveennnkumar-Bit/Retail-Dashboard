/* GO DESi | Retail P&L — core: data, state, filtering and P&L maths.
   Sales rows carry qty/revenue/cogs/transport/opex; cost rows carry salaries, travel,
   incentives and DB claims. Net margin = GM - transport - opex - field cost. */
'use strict';

const GD = {
  data: {},          // sales, costs, skus, customers, daily, meta
  months: [],        // sorted "YYYY-MM" with sales
  fys: [],
  latest: null,
  curFY: null,
  state: {
    page: 'overview',
    f: { period: 'ytd', from: null, to: null, cmp: 'ly',
         rsm: [], asm: [], zone: [], state: [], chan: [], l0: [], l1: [], type: [] },
    skuQ: '', custQ: '', drillRsm: null,
    plBy: 'month', plUnit: 'lakh',
    ex: { rows: 'rsm', cols: 'period', meas: 'revenue', unit: 'lakh' },
    up: { report: null, token: null, busy: false, done: null, costIdx: null, split: true, dashToken: '' },
  },
  api: null,
};

/* ---------- months & periods ---------- */
GD.MO = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
GD.pm = {
  add(m, k) { let [y, mo] = m.split('-').map(Number); mo += k; y += Math.floor((mo - 1) / 12); mo = ((mo - 1) % 12 + 12) % 12 + 1; return y + '-' + String(mo).padStart(2, '0'); },
  label(m) { const [y, mo] = m.split('-').map(Number); return GD.MO[mo - 1] + ' ' + String(y % 100).padStart(2, '0'); },
  long(m) { const [y, mo] = m.split('-').map(Number); return GD.MO[mo - 1] + ' ' + y; },
  fy(m) { const [y, mo] = m.split('-').map(Number); const a = mo >= 4 ? y : y - 1; return 'FY ' + String(a % 100).padStart(2, '0') + '-' + String((a + 1) % 100).padStart(2, '0'); },
};

GD.periodLabel = (ms) => !ms.length ? 'No period'
  : ms[0] === ms[ms.length - 1] ? GD.pm.long(ms[0])
  : GD.pm.long(ms[0]) + ' to ' + GD.pm.long(ms[ms.length - 1]);

/* Selected months + comparison months from the filters. */
GD.selection = function () {
  const f = GD.state.f, months = GD.months;
  let sel;
  switch (f.period) {
    case 'ytd': sel = months.filter((m) => GD.pm.fy(m) === GD.curFY); break;
    case 'latest': sel = months.slice(-1); break;
    case 'l3m': sel = months.slice(-3); break;
    case 'l6m': sel = months.slice(-6); break;
    case 'l12m': sel = months.slice(-12); break;
    case 'all': sel = months.slice(); break;
    case 'custom': {
      let a = months.indexOf(f.from), b = months.indexOf(f.to);
      if (a < 0) a = Math.max(0, months.length - 6);
      if (b < 0) b = months.length - 1;
      if (a > b) [a, b] = [b, a];
      sel = months.slice(a, b + 1); break;
    }
    default: sel = months.filter((m) => GD.pm.fy(m) === f.period); // an FY label
  }
  let cmpFull = [], cmpLabel = '';
  if (f.cmp === 'ly') { cmpFull = sel.map((m) => GD.pm.add(m, -12)); cmpLabel = 'vs LY'; }
  else if (f.cmp === 'prev') { cmpFull = sel.map((m, i) => GD.pm.add(sel[0], i - sel.length)); cmpLabel = 'vs prev'; }
  const have = new Set(months);
  const cmp = cmpFull.filter((m) => have.has(m));
  return { sel, cmp, cmpFull, cmpLabel, hasCmp: cmp.length > 0 };
};

GD.commercial = () => {
  const f = GD.state.f;
  return !!(f.zone.length || f.state.length || f.chan.length || f.l0.length || f.l1.length || f.type.length);
};

/* ---------- filtering ---------- */
const FKEYS = [['rsm', 'rsm'], ['asm', 'asm'], ['zone', 'zone'], ['state', 'state'],
               ['chan', 'sub_channel'], ['l0', 'l0'], ['l1', 'l1'], ['type', 'type']];

/* Filter rows for the given months. `dims` lists the row columns that exist in this dataset. */
GD.filt = function (rows, months, dims) {
  const f = GD.state.f, ms = new Set(months);
  const active = FKEYS.filter(([k, col]) => f[k].length && dims.includes(col))
    .map(([k, col]) => [col, new Set(f[k])]);
  return rows.filter((r) => {
    if (!ms.has(r.period)) return false;
    for (const [col, set] of active) if (!set.has(r[col])) return false;
    return true;
  });
};

const SALES_DIMS = ['rsm', 'asm', 'zone', 'state', 'sub_channel', 'l0', 'l1', 'l2', 'pack', 'type'];
const COST_DIMS = ['rsm', 'asm'];
const SKU_DIMS = ['rsm', 'asm', 'l0', 'l1', 'type'];
const CUST_DIMS = ['rsm', 'asm', 'zone', 'state', 'sub_channel'];

GD.sales = (months) => GD.filt(GD.data.sales, months, SALES_DIMS);
GD.costs = (months) => GD.commercial() ? [] : GD.filt(GD.data.costs, months, COST_DIMS);
GD.skus = (months) => GD.filt(GD.data.skus, months, SKU_DIMS);
GD.cust = (months) => GD.filt(GD.data.customers, months, CUST_DIMS);

/* ---------- totals ---------- */
GD.NUMS = ['qty', 'revenue', 'cogs', 'transport', 'opex',
  'so_salary', 'so_travel', 'so_incentive', 'asm_salary', 'asm_travel', 'asm_incentive',
  'rsm_salary', 'rsm_travel', 'rsm_incentive', 'db_claim'];

GD.derive = function (t) {
  t.gm = t.revenue - t.cogs;
  t.so_cost = t.so_salary + t.so_travel + t.so_incentive;
  t.asm_cost = t.asm_salary + t.asm_travel + t.asm_incentive;
  t.rsm_cost = t.rsm_salary + t.rsm_travel + t.rsm_incentive;
  t.field = t.so_cost + t.asm_cost + t.rsm_cost + t.db_claim;
  t.contrib = t.gm - t.transport - t.opex;
  t.nm = t.contrib - t.field;
  t.gm_pct = GD.div(t.gm, t.revenue);
  t.contrib_pct = GD.div(t.contrib, t.revenue);
  t.field_pct = GD.div(t.field, t.revenue);
  t.nm_pct = GD.div(t.nm, t.revenue);
  return t;
};

GD.tot = function (rowSets) {
  const t = {}; GD.NUMS.forEach((c) => { t[c] = 0; });
  for (const rows of rowSets) for (const r of rows) for (const c of GD.NUMS) { const v = +r[c]; if (v) t[c] += v; }
  return GD.derive(t);
};

/* Sales + field costs for the months, respecting all filters (cost rows drop out
   when market/product filters are on, as in the tracker). */
GD.totAll = (months) => GD.tot([GD.sales(months), GD.costs(months)]);

/* Group combined sales+cost rows by a key and derive the P&L for each group. */
GD.groupPL = function (months, keyFn) {
  const g = new Map();
  const push = (rows) => {
    for (const r of rows) {
      const k = keyFn(r);
      let t = g.get(k);
      if (!t) { t = {}; GD.NUMS.forEach((c) => { t[c] = 0; }); g.set(k, t); }
      for (const c of GD.NUMS) { const v = +r[c]; if (v) t[c] += v; }
    }
  };
  push(GD.sales(months)); push(GD.costs(months));
  for (const t of g.values()) GD.derive(t);
  return g;
};

GD.div = (a, b) => (b ? a / b : null);
GD.growth = (c, p) => (p ? (c - p) / Math.abs(p) : null);

/* ---------- formatting ---------- */
GD.inr = function (x, d = 2) {
  if (x == null || !isFinite(x)) return '–';
  const a = Math.abs(x), s = x < 0 ? '-' : '';
  if (a >= 1e7) return s + '₹' + (a / 1e7).toFixed(d) + ' Cr';
  if (a >= 1e5) return s + '₹' + (a / 1e5).toFixed(d) + ' L';
  if (a >= 1e3) return s + '₹' + (a / 1e3).toFixed(1) + ' K';
  return s + '₹' + Math.round(a).toLocaleString('en-IN');
};
GD.pct = (x, d = 1) => (x == null || !isFinite(x) ? '–' : (x * 100).toFixed(d) + '%');
GD.spct = (x, d = 1) => (x == null || !isFinite(x) ? '–' : (x >= 0 ? '+' : '') + (x * 100).toFixed(d) + '%');
GD.lakh = (x) => x / 1e5;
GD.fmtL = (x, d = 1) => (x == null || !isFinite(x) ? '–' : (x / 1e5).toLocaleString('en-IN', { minimumFractionDigits: d, maximumFractionDigits: d }));
GD.num = (x) => (x == null || !isFinite(x) ? '–' : Math.round(x).toLocaleString('en-IN'));
GD.esc = (s) => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

/* ---------- CSV download ---------- */
GD.downloadCSV = function (name, header, rows) {
  const cell = (v) => {
    if (v == null) return '';
    const s = String(v);
    return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  };
  const txt = [header.map(cell).join(',')]
    .concat(rows.map((r) => r.map(cell).join(','))).join('\r\n');
  const blob = new Blob(['﻿' + txt], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
};

/* ---------- multiselect component ---------- */
class MSelect {
  constructor(mount, { placeholder, onChange }) {
    this.el = typeof mount === 'string' ? document.getElementById(mount) : mount;
    this.placeholder = placeholder;
    this.onChange = onChange;
    this.options = [];
    this.values = [];
    this.el.classList.add('ms');
    this.el.innerHTML = '<button type="button" class="ms-btn"><span class="sum"></span><span class="caret">▼</span></button>';
    this.btn = this.el.querySelector('.ms-btn');
    this.pop = null;
    this.btn.addEventListener('click', (e) => { e.stopPropagation(); this.pop ? this.close() : this.open(); });
    document.addEventListener('click', (e) => { if (this.pop && !this.el.contains(e.target)) this.close(); });
    this.renderSum();
  }
  setOptions(options) {
    this.options = options;
    this.values = this.values.filter((v) => options.includes(v));
    this.renderSum();
  }
  set(values) { this.values = values.filter((v) => this.options.includes(v)); this.renderSum(); }
  renderSum() {
    const s = this.btn.querySelector('.sum');
    if (!this.values.length) { s.innerHTML = '<span class="ph">' + GD.esc(this.placeholder) + '</span>'; return; }
    const shown = this.values.slice(0, 2).map((v) => '<span class="ms-tag">' + GD.esc(v) + '</span>').join('');
    const more = this.values.length > 2 ? '<span class="ms-tag">+' + (this.values.length - 2) + '</span>' : '';
    s.innerHTML = '<span class="ms-tagwrap">' + shown + more + '</span>';
  }
  open() {
    this.close();
    const pop = document.createElement('div');
    pop.className = 'ms-pop';
    pop.addEventListener('click', (e) => e.stopPropagation());
    if (this.values.length) {
      const c = document.createElement('button');
      c.type = 'button'; c.className = 'ms-clear'; c.textContent = 'Clear selection';
      c.addEventListener('click', () => { this.values = []; this.renderSum(); this.close(); this.onChange(); });
      pop.appendChild(c);
    }
    for (const o of this.options) {
      const lab = document.createElement('label');
      lab.className = 'ms-opt';
      const cb = document.createElement('input');
      cb.type = 'checkbox'; cb.checked = this.values.includes(o);
      cb.addEventListener('change', () => {
        this.values = cb.checked ? [...this.values, o] : this.values.filter((v) => v !== o);
        this.renderSum(); this.onChange();
      });
      const sp = document.createElement('span'); sp.textContent = o;
      lab.append(cb, sp); pop.appendChild(lab);
    }
    this.el.appendChild(pop);
    this.pop = pop;
  }
  close() { if (this.pop) { this.pop.remove(); this.pop = null; } }
}
