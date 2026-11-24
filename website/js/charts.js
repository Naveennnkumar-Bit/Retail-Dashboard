/* GO DESi | Retail P&L — Plotly styling and shared UI builders. */
'use strict';

/* Green-led palette matched to the reference design. The keys keep their old names
   so every chart picks the new colors without further changes. */
const C = {
  NAVY: '#1A1D1F',      // ink / dark lines
  INDIGO: '#1F9D5B',    // primary green
  SAFFRON: '#D9A441',   // gold accent (GM % line)
  TEAL: '#2FBF8F',      // mint green
  GREEN: '#1F9D5B',
  RED: '#D95749',       // soft red for losses / shortfalls
  VIOLET: '#17623F',    // deep green
  SKY: '#5B8DB8',       // muted blue
  PINK: '#C96A5B',      // muted clay
  INK: '#1A1D1F', MUTED: '#7A828A', LINE: '#E8EBED',
};
const SERIES = ['#1F9D5B', '#A7D7BC', '#17623F', '#D9A441', '#5B8DB8', '#2FBF8F', '#C96A5B', '#8A6FBF', '#6B7280', '#79B4A0'];
const GM_SCALE = [[0, '#F3CBC3'], [0.5, '#F5E7C4'], [1, '#9FDDBB']];
const PLOT_CFG = { displayModeBar: false, responsive: true };

/* style_fig port: shared layout */
function baseLayout(h, legend = true, extra = {}) {
  return Object.assign({
    height: h,
    // wider right margin whenever a second (%) axis sits on the right, so its labels never clip
    margin: { l: 48, r: extra && extra.yaxis2 ? 48 : 14, t: legend ? 44 : 10, b: 34 },
    paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
    font: { family: 'Plus Jakarta Sans, system-ui, sans-serif', color: C.INK, size: 12 },
    colorway: SERIES,
    hoverlabel: { bgcolor: '#FFFFFF', bordercolor: '#DFE3E6',
      font: { size: 13, family: 'Plus Jakarta Sans, sans-serif', color: '#1A1D1F' } },
    legend: legend ? { orientation: 'h', yanchor: 'bottom', y: 1.0, x: 0, bgcolor: 'rgba(0,0,0,0)', title: { text: '' } } : undefined,
    showlegend: legend,
    bargap: 0.32,
    xaxis: { showgrid: false, linecolor: C.LINE, tickfont: { color: C.MUTED } },
    yaxis: { gridcolor: '#EFF1F2', griddash: 'dot', zeroline: false, tickfont: { color: C.MUTED } },
  }, extra);
}

function plot(id, traces, layout) {
  const el = document.getElementById(id);
  if (el) Plotly.newPlot(el, traces, layout, PLOT_CFG);
}

/* sparkline svg */
function spark(values, color = C.INDIGO, w = 220, h = 38) {
  const v = values.map((x) => (isFinite(x) ? +x : 0));
  if (v.length < 2) return '';
  const lo = Math.min(...v), hi = Math.max(...v), rng = (hi - lo) || 1;
  const pts = v.map((x, i) => [i * w / (v.length - 1), h - 4 - (x - lo) / rng * (h - 8)]);
  const line = pts.map((p) => p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' ');
  const gid = 'g' + Math.abs([...JSON.stringify(v) + color].reduce((a, c) => (a * 31 + c.charCodeAt(0)) | 0, 7)) % 1e8;
  const [lx, ly] = pts[pts.length - 1];
  return `<svg width="100%" height="${h}" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true">` +
    `<defs><linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${color}" stop-opacity=".28"/>` +
    `<stop offset="1" stop-color="${color}" stop-opacity="0"/></linearGradient></defs>` +
    `<polygon points="0,${h} ${line} ${w},${h}" fill="url(#${gid})"/>` +
    `<polyline points="${line}" fill="none" stroke="${color}" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>` +
    `<circle cx="${lx.toFixed(1)}" cy="${ly.toFixed(1)}" r="3.2" fill="${color}"/></svg>`;
}

/* KPI card */
function kpi({ label, value, sub = '', delta = null, deltaKind = 'pct', goodUp = true, cmpLabel = 'vs LY', trend = null, color = C.INDIGO, hero = false }) {
  let chip = '';
  if (delta != null && isFinite(delta)) {
    const unit = deltaKind === 'pct' ? '%' : ' pts';
    let txt = (delta >= 0 ? '▲ ' : '▼ ') + Math.abs(delta * 100).toFixed(1) + unit;
    let cls = Math.abs(delta) < 0.0005 ? 'flat' : ((delta > 0) === goodUp ? 'up' : 'down');
    if (cls === 'flat') txt = '● level';
    chip = `<span class="d ${cls}" title="${GD.esc(cmpLabel)}">${txt} <span style="opacity:.7;font-weight:600">${GD.esc(cmpLabel)}</span></span>`;
  }
  const sv = trend ? spark(trend, hero ? '#CBEBD9' : color) : '';
  return `<div class="kpi${hero ? ' hero' : ''}"><div class="row"><div class="l">${GD.esc(label)}</div>${chip}</div>` +
    `<div class="v">${value}</div><div class="s">${sub}</div>${sv}</div>`;
}

function cardHead(title, sub = '') {
  return `<div class="card-h">${GD.esc(title)}</div>` + (sub ? `<div class="card-s">${GD.esc(sub)}</div>` : '');
}

/* ---------- sortable, searchable table ----------
   cols: [{key, label, fmt, align:'l'|'r', bar:maxFn, cls(v,row), html(v,row)}]
   opts: {search, searchKeys, maxRows, height, download:{name, label}} */
const _tables = {};
function renderTable(mountId, cols, rows, opts = {}) {
  const t = { cols, rows, opts, sortKey: opts.sortKey ?? null, sortDir: opts.sortDir ?? -1, q: '' };
  _tables[mountId] = t;
  const el = document.getElementById(mountId);
  if (!el) return;
  let html = '';
  if (opts.search) html += `<input class="tsearch" type="search" placeholder="${GD.esc(opts.search)}" data-tq="${mountId}">`;
  html += `<div class="twrap"${opts.height ? ` style="max-height:${opts.height}px"` : ''}><table class="dt"><thead><tr>`;
  for (const c of cols) html += `<th class="${c.align === 'l' ? 'l' : ''}" data-tsort="${mountId}:${c.key}">${GD.esc(c.label)}<span class="arr"></span></th>`;
  html += '</tr></thead><tbody></tbody></table></div>';
  html += `<div class="tfoot"><span class="cnt"></span>` +
    (opts.download ? `<button class="btn btn-ghost btn-sm" data-tdl="${mountId}" type="button">⬇ ${GD.esc(opts.download.label || 'Download CSV')}</button>` : '') + '</div>';
  el.innerHTML = html;
  const inp = el.querySelector('input[data-tq]');
  if (inp) inp.addEventListener('input', () => { t.q = inp.value.trim().toLowerCase(); fillTable(mountId); });
  el.querySelectorAll('th[data-tsort]').forEach((th) => th.addEventListener('click', () => {
    const key = th.dataset.tsort.split(':')[1];
    if (t.sortKey === key) t.sortDir = -t.sortDir; else { t.sortKey = key; t.sortDir = -1; }
    fillTable(mountId);
  }));
  const dl = el.querySelector('button[data-tdl]');
  if (dl) dl.addEventListener('click', () => {
    const data = tableRows(t);
    GD.downloadCSV(opts.download.name, cols.map((c) => c.label),
      data.map((r) => cols.map((c) => r[c.key] ?? '')));
  });
  fillTable(mountId);
}

function tableRows(t) {
  let data = t.rows;
  if (t.q && t.opts.searchKeys) {
    data = data.filter((r) => t.opts.searchKeys.some((k) => String(r[k] ?? '').toLowerCase().includes(t.q)));
  }
  if (t.sortKey) {
    const k = t.sortKey, d = t.sortDir;
    data = [...data].sort((a, b) => {
      const x = a[k], y = b[k];
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      if (typeof x === 'number' && typeof y === 'number') return (x - y) * d;
      return String(x).localeCompare(String(y)) * d;
    });
  }
  return data;
}

function fillTable(mountId) {
  const t = _tables[mountId];
  const el = document.getElementById(mountId);
  if (!t || !el) return;
  const tbody = el.querySelector('tbody');
  const data = tableRows(t);
  const max = t.opts.maxRows || 400;
  const shown = data.slice(0, max);
  let html = '';
  for (const r of shown) {
    html += '<tr>';
    for (const c of t.cols) {
      const v = r[c.key];
      let inner;
      if (c.html) inner = c.html(v, r);
      else if (c.bar) {
        const mx = c.bar(data) || 1;
        const w = Math.max(0, Math.min(100, (v / mx) * 100));
        inner = `<span class="bar"><i style="width:${w}%"></i><b>${GD.esc(c.fmt ? c.fmt(v, r) : v)}</b></span>`;
      } else inner = GD.esc(c.fmt ? c.fmt(v, r) : (v ?? '–'));
      const cls = [(c.align === 'l' ? 'l' : ''), (c.cls ? c.cls(v, r) || '' : '')].join(' ').trim();
      html += `<td${cls ? ` class="${cls}"` : ''}>${inner}</td>`;
    }
    html += '</tr>';
  }
  tbody.innerHTML = html || `<tr><td class="l" colspan="${t.cols.length}" style="color:var(--muted)">Nothing matches.</td></tr>`;
  const cnt = el.querySelector('.cnt');
  if (cnt) cnt.textContent = data.length > shown.length
    ? `Showing ${shown.length.toLocaleString()} of ${data.length.toLocaleString()} rows — search to narrow, or download the full CSV`
    : `${data.length.toLocaleString()} row${data.length === 1 ? '' : 's'}`;
  el.querySelectorAll('th[data-tsort] .arr').forEach((sp) => { sp.textContent = ''; });
  if (t.sortKey) {
    const th = el.querySelector(`th[data-tsort="${mountId}:${t.sortKey}"] .arr`);
    if (th) th.textContent = t.sortDir === -1 ? ' ▾' : ' ▴';
  }
}
