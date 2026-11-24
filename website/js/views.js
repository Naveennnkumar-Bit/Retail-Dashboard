/* GO DESi | Retail P&L — page views. Each view gets ctx = {sel, cmp, cmpFull, cmpLabel, hasCmp, T, P, commercial, trail}. */
'use strict';

const quantile = (arr, q) => {
  const a = arr.filter((x) => isFinite(x)).sort((x, y) => x - y);
  if (!a.length) return null;
  const i = (a.length - 1) * q, lo = Math.floor(i);
  return a[lo] + (a[Math.min(lo + 1, a.length - 1)] - a[lo]) * (i - lo);
};
const sumBy = (rows, keyFn, cols) => {
  const g = new Map();
  for (const r of rows) {
    const k = keyFn(r);
    let o = g.get(k);
    if (!o) { o = { _k: k }; for (const c of cols) o[c] = 0; g.set(k, o); }
    for (const c of cols) { const v = +r[c]; if (v) o[c] += v; }
  }
  return g;
};
/* Product-page sales lines: Sales type only unless a type filter is on (as in the tracker app). */
const salesTyped = (rows) => GD.state.f.type.length ? rows : rows.filter((r) => r.type === 'Sales');

/* ============================ OVERVIEW ============================ */
function viewOverview(ctx) {
  const { sel, cmpLabel, hasCmp, T, P, commercial, trail } = ctx;
  const dlt = (k) => hasCmp ? GD.growth(T[k], P[k]) : null;
  const dpt = (k) => hasCmp && T[k] != null && P[k] != null ? T[k] - P[k] : null;
  const tr = (k) => trail.map((t) => t[k] ?? 0);

  let kpis = [
    kpi({ label: 'Revenue', value: GD.inr(T.revenue), sub: GD.num(T.qty) + ' units sold', delta: dlt('revenue'), cmpLabel, trend: tr('revenue'), hero: true }),
    kpi({ label: 'Gross margin', value: GD.inr(T.gm), sub: GD.pct(T.gm_pct) + ' of revenue', delta: dpt('gm_pct'), deltaKind: 'pts', cmpLabel, trend: tr('gm_pct'), color: C.SAFFRON }),
    kpi({ label: 'Contribution', value: GD.inr(T.contrib), sub: GD.pct(T.contrib_pct) + ' after transport and opex', delta: dlt('contrib'), cmpLabel, trend: tr('contrib'), color: C.TEAL }),
  ];
  if (!commercial) {
    kpis.push(
      kpi({ label: 'Field team cost', value: GD.inr(T.field), sub: GD.pct(T.field_pct) + ' of revenue', delta: dpt('field_pct'), deltaKind: 'pts', goodUp: false, cmpLabel, trend: tr('field_pct'), color: C.RED }),
      kpi({ label: 'Net margin', value: GD.inr(T.nm), sub: GD.pct(T.nm_pct) + ' of revenue', delta: dpt('nm_pct'), deltaKind: 'pts', cmpLabel, trend: tr('nm_pct'), color: C.VIOLET }));
  } else {
    const n = new Set(GD.cust(sel).filter((r) => +r.revenue > 0).map((r) => r.customer)).size;
    kpis.push(kpi({ label: 'Active customers', value: n.toLocaleString(), sub: 'billed in period' }));
  }

  return {
    html: `
      <div class="kpis">${kpis.join('')}</div>
      <div class="caption">Sparklines show the last 12 months up to the end of the selected period.</div>
      <div class="grid g21">
        <div class="card">${cardHead('Monthly performance', 'Revenue against the comparison period, with margin lines')}<div id="ch-monthly" class="chart"></div></div>
        <div class="card">${cardHead('Where the money goes', 'From revenue to net margin, ₹ lakh')}<div id="ch-water" class="chart"></div></div>
      </div>
      <div class="grid g231">
        <div class="card">${cardHead('RSM scorecard', 'Sorted by revenue. Growth compares with the comparison period.')}<div id="tb-rsm"></div></div>
        <div class="card">${cardHead('What stands out', 'Generated from the numbers in view')}<div id="ins"></div></div>
      </div>
      <div class="grid g2">
        <div class="card">${cardHead('Product mix', 'Inner ring is category, outer ring is range. Colour shows gross margin %.')}<div id="ch-mix" class="chart"></div></div>
        <div class="card">${cardHead('Geography', 'Inner ring is zone, outer ring is state')}<div id="ch-geo" class="chart"></div></div>
      </div>
      <div class="card">${cardHead('Billing rhythm', 'Daily revenue in the period. Darker means a bigger billing day.')}<div id="ch-rhythm" class="chart"></div></div>`,
    mount() {
      // monthly performance
      const x = sel.map(GD.pm.label);
      const mt = sel.map((m) => GD.totAll([m]));
      const traces = [];
      if (hasCmp) {
        const have = new Set(GD.months);
        const pv = ctx.cmpFull.map((m) => have.has(m) ? GD.totAll([m]).revenue : null);
        if (pv.some((v) => v != null)) traces.push({ type: 'bar', x, y: pv.map((v) => v == null ? null : GD.lakh(v)), name: 'Revenue ' + cmpLabel.replace('vs ', ''), marker: { color: '#E4E7EA' }, hovertemplate: 'Comparison ₹%{y:.1f} L<extra></extra>' });
      }
      traces.push({ type: 'bar', x, y: mt.map((t) => GD.lakh(t.revenue)), name: 'Revenue', marker: { color: mt.map((t) => GD.lakh(t.revenue)), colorscale: [[0, '#BFE3CE'], [1, C.INDIGO]], showscale: false }, hovertemplate: 'Revenue ₹%{y:.1f} L<extra></extra>' });
      traces.push({ type: 'scatter', x, y: mt.map((t) => (t.gm_pct ?? 0) * 100), name: 'GM %', yaxis: 'y2', mode: 'lines+markers', line: { color: C.SAFFRON, width: 3, shape: 'spline' }, marker: { size: 8, line: { width: 2, color: 'white' } }, hovertemplate: 'GM %{y:.1f}%<extra></extra>' });
      if (!commercial) traces.push({ type: 'scatter', x, y: mt.map((t) => (t.nm_pct ?? 0) * 100), name: 'NM %', yaxis: 'y2', mode: 'lines+markers', line: { color: C.GREEN, width: 3, shape: 'spline' }, marker: { size: 8, line: { width: 2, color: 'white' } }, hovertemplate: 'NM %{y:.1f}%<extra></extra>' });
      plot('ch-monthly', traces, baseLayout(370, true, { barmode: 'group', bargroupgap: 0.08, hovermode: 'x unified', yaxis: Object.assign(baseLayout(0).yaxis, { title: { text: '₹ lakh' } }), yaxis2: { overlaying: 'y', side: 'right', showgrid: false, ticksuffix: '%', tickfont: { color: C.MUTED } } }));

      // waterfall
      let steps = [['Revenue', T.revenue, 'absolute'], ['COGS', -T.cogs, 'relative'], ['Gross margin', T.gm, 'total'],
        ['Transport', -T.transport, 'relative'], ['Opex', -T.opex, 'relative'], ['Contribution', T.contrib, 'total']];
      if (!commercial) steps = steps.concat([['SO team', -T.so_cost, 'relative'], ['ASM team', -T.asm_cost, 'relative'],
        ['RSM', -T.rsm_cost, 'relative'], ['DB claim', -T.db_claim, 'relative'], ['Net margin', T.nm, 'total']]);
      plot('ch-water', [{
        type: 'waterfall', x: steps.map((s) => s[0]), y: steps.map((s) => GD.lakh(s[1])), measure: steps.map((s) => s[2]),
        connector: { line: { color: '#D4D9DC', dash: 'dot' } }, increasing: { marker: { color: C.GREEN } },
        decreasing: { marker: { color: '#E8846F' } }, totals: { marker: { color: '#1A1D1F' } },
        text: steps.map((s) => Math.abs(GD.lakh(s[1])) >= 1 ? GD.lakh(s[1]).toFixed(0) : GD.lakh(s[1]).toFixed(1)),
        textposition: 'outside', cliponaxis: false, textfont: { size: 10, color: C.MUTED },
        hovertemplate: '%{x}: ₹%{y:,.1f} L<extra></extra>',
      }], baseLayout(370, false, { xaxis: Object.assign(baseLayout(0).xaxis, { tickangle: -40 }), margin: { l: 48, r: 14, t: 26, b: 74 } }));

      // RSM scorecard
      const g = GD.groupPL(sel, (r) => r.rsm);
      const pg = hasCmp ? GD.groupPL(ctx.cmp, (r) => r.rsm) : new Map();
      const trailRev = new Map(); // rsm -> [rev per trail month]
      ctx.trailMonths.forEach((m, i) => {
        for (const [k, t] of GD.groupPL([m], (r) => r.rsm)) {
          if (!trailRev.has(k)) trailRev.set(k, Array(ctx.trailMonths.length).fill(0));
          trailRev.get(k)[i] = t.revenue;
        }
      });
      const rows = [...g.entries()].filter(([, t]) => Math.abs(t.revenue) + t.field > 0).map(([rsm, t]) => ({
        rsm, revenue: GD.lakh(t.revenue), gm_pct: t.gm_pct, growth: hasCmp && pg.get(rsm)?.revenue ? (t.revenue - pg.get(rsm).revenue) / Math.abs(pg.get(rsm).revenue) : null,
        cost_pct: commercial ? null : t.field_pct, nm: commercial ? null : GD.lakh(t.nm), nm_pct: commercial ? null : t.nm_pct,
        contrib: commercial ? GD.lakh(t.contrib) : null, trend: trailRev.get(rsm) || [],
      })).sort((a, b) => b.revenue - a.revenue);
      const cols = [
        { key: 'rsm', label: 'RSM', align: 'l' },
        { key: 'revenue', label: 'Revenue (₹ L)', fmt: (v) => v.toFixed(1), bar: (d) => Math.max(...d.map((r) => r.revenue), 1) },
        { key: 'gm_pct', label: 'GM %', fmt: GD.pct },
      ];
      if (hasCmp) cols.push({ key: 'growth', label: 'Growth %', fmt: GD.spct, cls: (v) => v == null ? '' : v < 0 ? 'neg' : 'pos' });
      if (commercial) cols.push({ key: 'contrib', label: 'Contribution (₹ L)', fmt: (v) => v.toFixed(1) });
      else cols.push(
        { key: 'cost_pct', label: 'Cost %', fmt: GD.pct },
        { key: 'nm', label: 'NM (₹ L)', fmt: (v) => v.toFixed(1), cls: (v) => v < 0 ? 'neg' : '' },
        { key: 'nm_pct', label: 'NM %', fmt: GD.pct, cls: (v) => v != null && v < 0 ? 'neg' : '' });
      cols.push({ key: 'trend', label: '12-month trend', html: (v) => `<span style="display:inline-block;width:130px">${spark(v, C.INDIGO, 130, 30)}</span>` });
      renderTable('tb-rsm', cols, rows, {});

      document.getElementById('ins').innerHTML = insights(ctx);

      // product mix sunburst (l0 -> l1)
      const S = GD.sales(sel);
      sunburst('ch-mix', S, ['l0', 'l1'], { colorGM: true });
      // geography sunburst (zone -> state)
      sunburst('ch-geo', S, ['zone', 'state'], { colorGM: false });

      // billing rhythm
      rhythm('ch-rhythm', sel);
    },
  };
}

/* Two-level sunburst built child-up: only positive children are kept, and each
   parent is the sum of its kept children, so the ring totals always close. */
function sunburst(id, rows, levels, { colorGM }) {
  const pairs = sumBy(rows, (r) => r[levels[0]] + '\u0001' + r[levels[1]], ['revenue', 'cogs']);
  const kids = [...pairs.entries()]
    .map(([k, o]) => { const [a, b] = k.split('\u0001'); return { a, b, revenue: o.revenue, cogs: o.cogs }; })
    .filter((o) => o.revenue > 0);
  if (!kids.length) { document.getElementById(id).innerHTML = '<div class="caption">Nothing to show in this view.</div>'; return; }
  const byA = new Map();
  for (const o of kids) {
    const t = byA.get(o.a) || { revenue: 0, cogs: 0 };
    t.revenue += o.revenue; t.cogs += o.cogs; byA.set(o.a, t);
  }
  const catColor = new Map([...byA.keys()].sort().map((k, i) => [k, SERIES[i % SERIES.length]]));
  const ids = [], labels = [], parents = [], values = [], colors = [], gmVals = [];
  const push = (id_, label, parent, o, colorKey) => {
    ids.push(id_); labels.push(label); parents.push(parent); values.push(o.revenue);
    const gm = (o.revenue - o.cogs) / o.revenue * 100;
    gmVals.push(gm);
    colors.push(colorGM ? gm : catColor.get(colorKey));
  };
  for (const [k, o] of byA) push('A\u0001' + k, k, '', o, k);
  for (const o of kids) push('B\u0001' + o.a + '\u0001' + o.b, o.b, 'A\u0001' + o.a, o, o.a);
  const trace = {
    type: 'sunburst', ids, labels, parents, values, branchvalues: 'total',
    insidetextorientation: 'radial',
    marker: { colors, line: { color: 'white', width: 2 } },
    hovertemplate: '<b>%{label}</b><br>₹%{value:,.0f}<br>%{percentRoot:.1%} of total<extra></extra>',
  };
  if (colorGM) {
    trace.marker.colorscale = GM_SCALE;
    trace.marker.cmin = Math.max(0, quantile(gmVals, 0.05) ?? 0);
    trace.marker.cmax = Math.max(quantile(gmVals, 0.95) ?? 50, (quantile(gmVals, 0.05) ?? 0) + 1);
    trace.marker.colorbar = { title: { text: 'GM %' }, thickness: 10, len: 0.7 };
    trace.hovertemplate = '<b>%{label}</b><br>₹%{value:,.0f}<br>GM %{color:.1f}%<extra></extra>';
  }
  plot(id, [trace], baseLayout(380, false, { margin: { l: 8, r: 8, t: 10, b: 8 } }));
}

function rhythm(id, sel) {
  const f = GD.state.f;
  const lo = sel[0] + '-01', hi = GD.pm.add(sel[sel.length - 1], 1) + '-01';
  let rows = GD.data.daily.filter((r) => r.day >= lo && r.day < hi);
  if (f.rsm.length) rows = rows.filter((r) => f.rsm.includes(r.rsm));
  const byDay = new Map();
  rows.forEach((r) => byDay.set(r.day, (byDay.get(r.day) || 0) + (+r.revenue || 0)));
  if (!byDay.size) { document.getElementById(id).innerHTML = '<div class="caption">No billing days in this view.</div>'; return; }
  const days = [...byDay.keys()].sort();
  const d0 = new Date(days[0] + 'T00:00:00Z');
  const start = new Date(d0); start.setUTCDate(start.getUTCDate() - ((d0.getUTCDay() + 6) % 7)); // back to Monday
  const dN = new Date(days[days.length - 1] + 'T00:00:00Z');
  const nWeeks = Math.floor((dN - start) / (7 * 864e5)) + 1;
  const z = Array.from({ length: 7 }, () => Array(nWeeks).fill(null));
  const txt = Array.from({ length: 7 }, () => Array(nWeeks).fill(''));
  for (let d = new Date(start); d <= dN; d.setUTCDate(d.getUTCDate() + 1)) {
    const key = d.toISOString().slice(0, 10);
    const w = Math.floor((d - start) / (7 * 864e5)), dow = (d.getUTCDay() + 6) % 7;
    const v = byDay.get(key) || 0;
    z[dow][w] = v / 1e5;
    txt[dow][w] = d.toUTCString().slice(0, 16) + '<br>₹' + (v / 1e5).toFixed(2) + ' L';
  }
  const xs = Array.from({ length: nWeeks }, (_, i) => {
    const d = new Date(start); d.setUTCDate(d.getUTCDate() + i * 7);
    return d.getUTCDate() + ' ' + GD.MO[d.getUTCMonth()];
  });
  const pos = z.flat().filter((v) => v > 0);
  plot(id, [{
    type: 'heatmap', z, x: xs, y: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'], text: txt,
    hovertemplate: '%{text}<extra></extra>',
    colorscale: [[0, '#F2F5F3'], [0.3, '#BFE3CE'], [0.7, '#2FA568'], [1, '#124F35']],
    xgap: 3, ygap: 3, zmin: 0, zmax: pos.length ? quantile(pos, 0.95) : 1,
    colorbar: { title: { text: '₹ L' }, thickness: 10 },
  }], baseLayout(260, false, { yaxis: { autorange: 'reversed', showgrid: false, tickfont: { color: C.MUTED } }, xaxis: { showgrid: false, nticks: 14, tickfont: { color: C.MUTED } } }));
}

function insights(ctx) {
  const { sel, cmp, cmpLabel, hasCmp, T, P, commercial } = ctx;
  const items = [];
  const add = (icon, bg, html) => items.push(`<div class="insight"><div class="ic" style="background:${bg}">${icon}</div><div>${html}</div></div>`);
  if (hasCmp && P.revenue) {
    const gr = GD.growth(T.revenue, P.revenue);
    const word = Math.abs(gr) < 0.005 ? 'flat' : (gr >= 0 ? 'up ' : 'down ') + Math.abs(gr * 100).toFixed(1) + '%';
    add(gr >= 0 ? '\u{1F4C8}' : '\u{1F4C9}', '#E1F3E8', `Revenue is <b>${word}</b> ${cmpLabel} (${GD.inr(T.revenue)} against ${GD.inr(P.revenue)}).`);
  }
  if (!commercial) {
    const g = [...GD.groupPL(sel, (r) => r.rsm).entries()].filter(([, t]) => t.revenue > T.revenue * 0.02);
    if (g.length >= 2) {
      const best = g.reduce((a, b) => (b[1].nm_pct ?? -9) > (a[1].nm_pct ?? -9) ? b : a);
      const worst = g.reduce((a, b) => (b[1].nm_pct ?? 9) < (a[1].nm_pct ?? 9) ? b : a);
      add('\u{1F3C6}', '#E1F3E8', `<b>${GD.esc(best[0])}</b> runs the healthiest territory at <b>${GD.pct(best[1].nm_pct)}</b> net margin.`);
      if ((worst[1].nm_pct ?? 1) < 0.05) add('⚠️', '#FBEAE7', `<b>${GD.esc(worst[0])}</b> is at <b>${GD.pct(worst[1].nm_pct)}</b> net margin, with field cost at ${GD.pct(worst[1].field_pct)} of revenue.`);
    }
  }
  if (hasCmp) {
    const a = sumBy(GD.sales(sel), (r) => r.l1, ['revenue']);
    const b = sumBy(GD.sales(cmp), (r) => r.l1, ['revenue']);
    const ch = [...new Set([...a.keys(), ...b.keys()])].map((k) => [k, (a.get(k)?.revenue || 0) - (b.get(k)?.revenue || 0)]).sort((x, y) => x[1] - y[1]);
    if (ch.length && ch[ch.length - 1][1] > 0) add('\u{1F680}', '#F8EFD8', `<b>${GD.esc(ch[ch.length - 1][0])}</b> added the most revenue: <b>${GD.inr(ch[ch.length - 1][1])}</b> ${cmpLabel}.`);
    if (ch.length && ch[0][1] < 0) add('\u{1F53B}', '#FBEAE7', `<b>${GD.esc(ch[0][0])}</b> lost the most: <b>${GD.inr(ch[0][1])}</b> ${cmpLabel}.`);
  }
  const cr = [...sumBy(GD.cust(sel), (r) => r.customer, ['revenue']).values()].map((o) => o.revenue).filter((v) => v > 0).sort((x, y) => y - x);
  const crTot = cr.reduce((s, v) => s + v, 0);
  if (crTot > 0) add('\u{1F465}', '#E5EFF6', `Top 10 customers bring <b>${GD.pct(cr.slice(0, 10).reduce((s, v) => s + v, 0) / crTot)}</b> of revenue across ${cr.length} billed customers.`);
  const S = GD.sales(sel);
  const ret = -S.filter((r) => +r.is_return && r.type === 'Sales').reduce((s, r) => s + (+r.revenue || 0), 0);
  const gross = S.filter((r) => !+r.is_return && r.type === 'Sales').reduce((s, r) => s + (+r.revenue || 0), 0);
  if (gross) add('↩️', '#F0F2F3', `Returns took back <b>${GD.inr(ret)}</b>, or <b>${GD.pct(ret / gross)}</b> of gross sales.`);
  const samp = S.filter((r) => r.type !== 'Sales').reduce((s, r) => s + (+r.cogs || 0), 0);
  if (samp) add('\u{1F381}', '#F6E9E6', `Sampling and trade marketing cost <b>${GD.inr(samp)}</b> in product, ${GD.pct(samp / T.revenue)} of revenue.`);
  return items.join('') || '<div class="card-s">Not enough data in this view.</div>';
}

/* ============================ P&L STATEMENT ============================ */
const PL_LINES = [
  ['Revenue', 'revenue', 'sub'], ['Cost of goods sold', 'cogs', 'ind'], ['Gross margin', 'gm', 'sub'], ['Gross margin %', 'gm_pct', 'pct'],
  ['Transport', 'transport', 'ind'], ['Operating expenses', 'opex', 'ind'], ['Contribution', 'contrib', 'sub'], ['Contribution %', 'contrib_pct', 'pct'],
  ['SO salary', 'so_salary', 'ind'], ['SO travel', 'so_travel', 'ind'], ['SO incentive', 'so_incentive', 'ind'],
  ['ASM salary', 'asm_salary', 'ind'], ['ASM travel', 'asm_travel', 'ind'], ['ASM incentive', 'asm_incentive', 'ind'],
  ['RSM salary', 'rsm_salary', 'ind'], ['RSM travel', 'rsm_travel', 'ind'], ['RSM incentive', 'rsm_incentive', 'ind'],
  ['DB claim', 'db_claim', 'ind'], ['Total field cost', 'field', 'sub'], ['Field cost %', 'field_pct', 'pct'],
  ['Net margin', 'nm', 'total'], ['Net margin %', 'nm_pct', 'pct'],
];

function viewPL(ctx) {
  const { sel, commercial } = ctx;
  const st = GD.state;
  return {
    html: `
      <div class="controls">
        <span><span class="lbl">Columns</span><span class="seg" id="pl-by">
          ${['month', 'rsm', 'asm', 'fy'].map((k) => `<button type="button" data-v="${k}" class="${st.plBy === k ? 'on' : ''}">${{ month: 'Month', rsm: 'RSM', asm: 'ASM', fy: 'Financial year' }[k]}</button>`).join('')}
        </span></span>
        <span><span class="lbl">Show</span><span class="seg" id="pl-unit">
          ${[['lakh', '₹ lakh'], ['inr', '₹'], ['pct', '% of revenue']].map(([k, l]) => `<button type="button" data-v="${k}" class="${st.plUnit === k ? 'on' : ''}">${l}</button>`).join('')}
        </span></span>
        <button class="btn btn-sm" id="pl-dl" type="button">⬇ Download P&amp;L (CSV)</button>
      </div>
      ${st.plBy === 'fy' ? '<div class="caption">Financial year view ignores the period picker and shows every year in the file.</div>' : ''}
      <div class="card"><div id="pl-table"></div>
      <div class="caption">Field cost lines and net margin match the YTD &amp; L3M Summary pivot in the tracker.</div></div>`,
    mount() {
      document.querySelectorAll('#pl-by button').forEach((b) => b.addEventListener('click', () => { st.plBy = b.dataset.v; App.render(); }));
      document.querySelectorAll('#pl-unit button').forEach((b) => b.addEventListener('click', () => { st.plUnit = b.dataset.v; App.render(); }));

      const months = st.plBy === 'fy' ? GD.months : sel;
      const keyFn = { month: (r) => r.period, rsm: (r) => r.rsm, asm: (r) => r.asm, fy: (r) => GD.pm.fy(r.period) }[st.plBy];
      const g = GD.groupPL(months, keyFn);
      let keys = [...g.keys()];
      if (st.plBy === 'month' || st.plBy === 'fy') keys.sort();
      else keys = keys.filter((k) => Math.abs(g.get(k).revenue) + g.get(k).field > 0).sort((a, b) => g.get(b).revenue - g.get(a).revenue);
      const tot = GD.totAll(months);
      const colLabel = (k) => st.plBy === 'month' ? GD.pm.label(k) : k;
      const lines = commercial ? PL_LINES.filter(([, k]) => ['revenue', 'cogs', 'gm', 'gm_pct', 'transport', 'opex', 'contrib', 'contrib_pct'].includes(k)) : PL_LINES;

      const cell = (t, key, kind) => {
        const v = t[key];
        let txt;
        if (kind === 'pct') txt = GD.pct(v);
        else if (st.plUnit === 'pct') txt = GD.pct(GD.div(v, t.revenue));
        else if (st.plUnit === 'inr') txt = GD.num(v);
        else txt = GD.fmtL(v, 2);
        return txt;
      };
      let html = '<div class="plwrap"><table class="pl"><thead><tr><th>Line item</th>' +
        keys.map((k) => `<th>${GD.esc(colLabel(k))}</th>`).join('') + '<th>Total</th></tr></thead><tbody>';
      for (const [name, key, kind] of lines) {
        html += `<tr class="${kind}"><td>${GD.esc(name)}</td>`;
        for (const k of keys) {
          const t = g.get(k);
          const v = t[key];
          const neg = isFinite(v) && v < 0 && ['gm', 'contrib', 'nm', 'gm_pct', 'contrib_pct', 'nm_pct'].includes(key);
          html += `<td class="${neg ? 'neg' : ''}">${cell(t, key, kind)}</td>`;
        }
        const vT = tot[key];
        const negT = isFinite(vT) && vT < 0 && ['gm', 'contrib', 'nm', 'gm_pct', 'contrib_pct', 'nm_pct'].includes(key);
        html += `<td class="tot ${negT ? 'neg' : ''}">${cell(tot, key, kind)}</td></tr>`;
      }
      html += '</tbody></table></div>';
      document.getElementById('pl-table').innerHTML = html;

      document.getElementById('pl-dl').addEventListener('click', () => {
        const header = ['Line item', ...keys.map(colLabel), 'Total'];
        const rows = lines.map(([name, key, kind]) => [name,
          ...keys.map((k) => kind === 'pct' ? GD.pct(g.get(k)[key]) : Math.round(g.get(k)[key])),
          kind === 'pct' ? GD.pct(tot[key]) : Math.round(tot[key])]);
        GD.downloadCSV(`GO_DESi_PL_${st.plBy}_${GD.periodLabel(months).replace(/ /g, '_')}.csv`, header, rows);
      });
    },
  };
}

/* ============================ SALES TEAM ============================ */
function viewTeam(ctx) {
  const { sel, cmp, cmpLabel, hasCmp, commercial } = ctx;
  const st = GD.state;
  return {
    html: `
      ${commercial ? '<div class="note">Clear the market and product filters to see field costs by RSM and ASM.</div>' : ''}
      <div class="kpis" id="team-kpis"></div>
      <div class="grid g12">
        <div class="card">${cardHead('ASM map: size vs profitability', 'Bubble size is field cost. Top-right is big and profitable.')}<div id="ch-asmmap" class="chart"></div></div>
        <div class="card">${cardHead('Field cost build-up by RSM', 'Salary, travel and incentives at each level')}<div id="ch-fieldcost" class="chart"></div></div>
      </div>
      <div class="card">${cardHead('Heat check: ' + (commercial ? 'gross' : 'net') + ' margin % by RSM and month', 'Green is healthy, red needs attention. Hover for the numbers.')}<div id="ch-heat" class="chart"></div></div>
      <div class="card">${cardHead('ASM / ASE league table', 'Click a column header to sort')}<div id="tb-asm"></div></div>
      <div class="card">${cardHead('Drill into one RSM', 'Monthly revenue and net margin for the RSM and their ASMs')}
        <select id="drill-rsm" class="sel" style="max-width:300px;margin-bottom:10px"></select>
        <div id="ch-drill" class="chart"></div></div>`,
    mount() {
      const g = GD.groupPL(sel, (r) => r.rsm);
      const live = [...g.entries()].filter(([, t]) => t.revenue + t.field > 0).sort((a, b) => b[1].revenue - a[1].revenue);
      const pg = hasCmp ? GD.groupPL(cmp, (r) => r.rsm) : new Map();
      document.getElementById('team-kpis').innerHTML = live.map(([rsm, t]) => {
        const pv = pg.get(rsm)?.revenue;
        return kpi({ label: rsm, value: GD.inr(t.revenue),
          sub: 'GM ' + GD.pct(t.gm_pct) + (commercial ? '' : ' · NM <b>' + GD.pct(t.nm_pct) + '</b>'),
          delta: pv ? GD.growth(t.revenue, pv) : null, cmpLabel });
      }).join('');

      // ASM bubble map
      const ga = GD.groupPL(sel, (r) => r.rsm + '\u0001' + r.asm);
      const pts = [...ga.entries()].map(([k, t]) => { const [rsm, asm] = k.split('\u0001'); return { rsm, asm, ...t }; }).filter((p) => p.revenue > 0);
      const yKey = commercial ? 'gm_pct' : 'nm_pct', yLab = commercial ? 'Gross margin %' : 'Net margin %';
      const yv = pts.map((p) => (p[yKey] ?? 0) * 100);
      const lo = Math.max(Math.min(...yv, 0), -40) - 3;
      const hidden = yv.filter((v) => v < -40).length;
      const rsms = [...new Set(pts.map((p) => p.rsm))].sort();
      const traces = rsms.map((rsm, i) => {
        const sub = pts.filter((p) => p.rsm === rsm);
        const sizes = sub.map((p) => Math.max(commercial ? p.revenue : p.field, 1));
        const smax = Math.max(...pts.map((p) => Math.max(commercial ? p.revenue : p.field, 1)));
        return { type: 'scatter', mode: 'markers', name: rsm,
          x: sub.map((p) => GD.lakh(p.revenue)), y: sub.map((p) => Math.max((p[yKey] ?? 0) * 100, lo + 0.1)),
          marker: { size: sizes, sizemode: 'area', sizeref: 2 * smax / (42 ** 2), sizemin: 5, color: SERIES[i % SERIES.length], line: { width: 1, color: 'white' } },
          customdata: sub.map((p) => [p.asm, p.rsm, (p[yKey] ?? 0) * 100]),
          hovertemplate: '<b>%{customdata[0]}</b><br>%{customdata[1]}<br>Revenue ₹%{x:.1f} L<br>' + yLab + ' %{customdata[2]:.1f}%<extra></extra>' };
      });
      const notes = hidden ? [{ x: 0, xref: 'paper', y: lo, yref: 'y', xanchor: 'left', yanchor: 'bottom', showarrow: false, text: `${hidden} ASM(s) below -40% shown at the floor: cost with little or no revenue`, font: { color: C.RED, size: 11 } }] : [];
      plot('ch-asmmap', traces, baseLayout(420, true, {
        xaxis: Object.assign(baseLayout(0).xaxis, { title: { text: 'Revenue (₹ lakh)' } }),
        yaxis: Object.assign(baseLayout(0).yaxis, { title: { text: yLab }, range: [lo, Math.max(...yv, 0) + 5] }),
        shapes: [{ type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 0, y1: 0, line: { color: '#D4D9DC' } }],
        annotations: notes,
      }));

      // field cost build-up
      if (commercial) {
        document.getElementById('ch-fieldcost').innerHTML = '<div class="caption">Not available with market or product filters on.</div>';
      } else {
        const gg = live.slice().sort((a, b) => a[1].revenue - b[1].revenue);
        const names = gg.map(([r]) => r);
        const parts = [
          ['SO salary', (t) => t.so_salary], ['SO travel + incentive', (t) => t.so_travel + t.so_incentive],
          ['ASM', (t) => t.asm_cost], ['RSM', (t) => t.rsm_cost], ['DB claim', (t) => t.db_claim]];
        const tr = parts.map(([nm, fn], i) => ({ type: 'bar', orientation: 'h', y: names, x: gg.map(([, t]) => GD.lakh(fn(t))), name: nm, marker: { color: SERIES[i] }, hovertemplate: '%{y}<br>' + nm + ' ₹%{x:.1f} L<extra></extra>' }));
        const ann = gg.map(([r, t]) => ({ x: GD.lakh(t.field), y: r, text: '  ' + GD.pct(t.field_pct) + ' of rev', showarrow: false, xanchor: 'left', font: { color: C.MUTED, size: 11 } }));
        plot('ch-fieldcost', tr, baseLayout(420, true, { barmode: 'stack', xaxis: Object.assign(baseLayout(0).xaxis, { title: { text: '₹ lakh' } }), annotations: ann }));
      }

      // heat check
      const hmKey = commercial ? 'gm_pct' : 'nm_pct';
      const hm = GD.groupPL(sel, (r) => r.rsm + '\u0001' + r.period);
      const order = live.map(([r]) => r);
      const z = order.map((rsm) => sel.map((m) => { const t = hm.get(rsm + '\u0001' + m); return t && t.revenue > 0 ? (t[hmKey] ?? 0) * 100 : null; }));
      const rv = order.map((rsm) => sel.map((m) => { const t = hm.get(rsm + '\u0001' + m); return t ? GD.lakh(t.revenue) : null; }));
      const flat = z.flat().filter((v) => v != null && isFinite(v));
      const lim = flat.length ? Math.max(...flat.map(Math.abs)) : 10;
      plot('ch-heat', [{
        type: 'heatmap', z, x: sel.map(GD.pm.label), y: order,
        text: z.map((row) => row.map((v) => v == null ? '' : v.toFixed(1) + '%')), texttemplate: '%{text}',
        customdata: rv, hovertemplate: '%{y} · %{x}<br>%{z:.1f}%<br>Revenue ₹%{customdata:.1f} L<extra></extra>',
        colorscale: [[0, '#D95749'], [0.5, '#F5E7C4'], [1, '#1F9D5B']], zmid: 0, zmin: -lim, zmax: lim,
        xgap: 4, ygap: 4, colorbar: { ticksuffix: '%', thickness: 10 },
      }], baseLayout(70 + 46 * order.length, false, { yaxis: { autorange: 'reversed', showgrid: false, tickfont: { color: C.MUTED } } }));

      // ASM league table
      const rows = [...ga.entries()].map(([k, t]) => { const [rsm, asm] = k.split('\u0001'); return { rsm, asm, ...t }; })
        .filter((r) => r.revenue + r.field > 0)
        .map((r) => ({ asm: r.asm, rsm: r.rsm, revenue: GD.lakh(r.revenue), gm_pct: r.gm_pct, contrib: GD.lakh(r.contrib),
          growth: hasCmp ? (() => { const p = GD.groupPL(cmp, (x) => x.rsm + '\u0001' + x.asm).get(r.rsm + '\u0001' + r.asm); return p?.revenue ? GD.growth(r.revenue, p.revenue) : null; })() : null,
          field: commercial ? null : GD.lakh(r.field), field_pct: commercial ? null : r.field_pct,
          nm: commercial ? null : GD.lakh(r.nm), nm_pct: commercial ? null : r.nm_pct }))
        .sort((a, b) => b.revenue - a.revenue);
      const cols = [
        { key: 'asm', label: 'ASM / ASE', align: 'l' }, { key: 'rsm', label: 'RSM', align: 'l' },
        { key: 'revenue', label: 'Revenue (₹ L)', fmt: (v) => v.toFixed(2), bar: (d) => Math.max(...d.map((r) => r.revenue), 1) },
        { key: 'gm_pct', label: 'GM %', fmt: GD.pct },
        { key: 'contrib', label: 'Contribution (₹ L)', fmt: (v) => v.toFixed(2), cls: (v) => v < 0 ? 'neg' : '' }];
      if (hasCmp) cols.push({ key: 'growth', label: 'Growth %', fmt: GD.spct, cls: (v) => v == null ? '' : v < 0 ? 'neg' : 'pos' });
      if (!commercial) cols.push(
        { key: 'field', label: 'Field cost (₹ L)', fmt: (v) => v.toFixed(2) },
        { key: 'field_pct', label: 'Field cost %', fmt: GD.pct },
        { key: 'nm', label: 'Net margin (₹ L)', fmt: (v) => v.toFixed(2), cls: (v) => v < 0 ? 'neg' : '' },
        { key: 'nm_pct', label: 'NM %', fmt: GD.pct, cls: (v) => v != null && v < 0 ? 'neg' : '' });
      renderTable('tb-asm', cols, rows, { height: 420, download: { name: 'GO_DESi_ASM_league.csv', label: 'Download CSV' } });

      // drill
      const dsel = document.getElementById('drill-rsm');
      const rsmNames = live.map(([r]) => r);
      if (!rsmNames.includes(st.drillRsm)) st.drillRsm = rsmNames[0] || null;
      dsel.innerHTML = rsmNames.map((r) => `<option${r === st.drillRsm ? ' selected' : ''}>${GD.esc(r)}</option>`).join('');
      dsel.addEventListener('change', () => { st.drillRsm = dsel.value; drawDrill(); });
      const drawDrill = () => {
        const rsm = st.drillRsm;
        if (!rsm) { document.getElementById('ch-drill').innerHTML = ''; return; }
        const x = sel.map(GD.pm.label);
        const byAsm = new Map();
        for (const r of GD.sales(sel).filter((r) => r.rsm === rsm)) {
          if (!byAsm.has(r.asm)) byAsm.set(r.asm, new Map());
          const mm = byAsm.get(r.asm);
          mm.set(r.period, (mm.get(r.period) || 0) + (+r.revenue || 0));
        }
        const traces = [...byAsm.entries()]
          .filter(([, mm]) => [...mm.values()].some((v) => v > 0))
          .map(([asm, mm], i) => ({ type: 'bar', name: asm, x, y: sel.map((m) => GD.lakh(mm.get(m) || 0)), marker: { color: SERIES[i % SERIES.length] }, hovertemplate: '₹%{y:.1f} L<extra>' + GD.esc(asm) + '</extra>' }));
        const layoutExtra = { barmode: 'stack', hovermode: 'x unified', yaxis: Object.assign(baseLayout(0).yaxis, { title: { text: '₹ lakh' } }) };
        if (!commercial) {
          const tots = sel.map((m) => { const t = GD.groupPL([m], (r) => r.rsm).get(rsm); return t ? (t.nm_pct ?? 0) * 100 : null; });
          traces.push({ type: 'scatter', x, y: tots, name: 'NM %', yaxis: 'y2', mode: 'lines+markers', line: { color: C.INK, width: 3 }, hovertemplate: 'NM %{y:.1f}%<extra></extra>' });
          layoutExtra.yaxis2 = { overlaying: 'y', side: 'right', ticksuffix: '%', showgrid: false, tickfont: { color: C.MUTED } };
        }
        plot('ch-drill', traces, baseLayout(380, true, layoutExtra));
      };
      drawDrill();
    },
  };
}

/* ============================ PRODUCTS ============================ */
function viewProducts(ctx) {
  const { sel, cmp, hasCmp } = ctx;
  return {
    html: `
      ${GD.state.f.zone.length || GD.state.f.state.length || GD.state.f.chan.length ? '<div class="note">SKU-level tables and the SKU matrix don’t carry zone, state or channel, so those filters apply to the charts built from invoice lines but not to the SKU tables.</div>' : ''}
      <div class="grid g12">
        <div class="card">${cardHead('Portfolio map', 'Box size is revenue, colour is gross margin %. Click a box to zoom in.')}<div id="ch-tree" class="chart"></div></div>
        <div class="card">${cardHead('SKU matrix', 'Each dot is a SKU. Dashed lines are the averages.')}<div id="ch-skumatrix" class="chart"></div></div>
      </div>
      <div class="card">${cardHead('SKU performance', 'Search, sort, and download')}<div id="tb-sku"></div></div>
      <div class="grid g2">
        <div class="card">${cardHead('Range trend', 'Monthly revenue by range')}<div id="ch-range" class="chart"></div></div>
        <div class="card">${cardHead('Pack type mix', 'Share of revenue and margin by pack format')}<div id="ch-pack" class="chart"></div></div>
      </div>`,
    mount() {
      const S = salesTyped(GD.sales(sel));
      // treemap l0 > l1 > l2, built child-up so every branch total closes
      const leaves = [...sumBy(S, (r) => [r.l0, r.l1, r.l2].join('\u0001'), ['revenue', 'cogs']).entries()]
        .map(([k, o]) => { const [a, b, c] = k.split('\u0001'); return { a, b, c, revenue: o.revenue, cogs: o.cogs }; })
        .filter((o) => o.revenue > 0);
      const rollup = (keyFn) => {
        const m = new Map();
        for (const o of leaves) {
          const k = keyFn(o);
          const t = m.get(k) || { revenue: 0, cogs: 0 };
          t.revenue += o.revenue; t.cogs += o.cogs; m.set(k, t);
        }
        return m;
      };
      const lvlA = rollup((o) => o.a), lvlB = rollup((o) => o.a + '\u0001' + o.b);
      const ids = ['root'], labels = ['All products'], parents = [''], values = [0], colors = [0];
      const gmv = [];
      const pushNode = (id, label, parent, o) => {
        ids.push(id); labels.push(label); parents.push(parent); values.push(o.revenue);
        const gm = (o.revenue - o.cogs) / o.revenue * 100;
        colors.push(gm); gmv.push(gm);
      };
      for (const [k, o] of lvlA) pushNode('A\u0001' + k, k, 'root', o);
      for (const [k, o] of lvlB) pushNode('B\u0001' + k, k.split('\u0001')[1], 'A\u0001' + k.split('\u0001')[0], o);
      for (const o of leaves) pushNode('C\u0001' + [o.a, o.b, o.c].join('\u0001'), o.c, 'B\u0001' + o.a + '\u0001' + o.b, o);
      const rootRev = [...lvlA.values()].reduce((s, o) => s + o.revenue, 0);
      const rootCogs = [...lvlA.values()].reduce((s, o) => s + o.cogs, 0);
      values[0] = rootRev;
      colors[0] = rootRev ? (rootRev - rootCogs) / rootRev * 100 : 0;
      if (leaves.length) plot('ch-tree', [{
        type: 'treemap', ids, labels, parents, values, branchvalues: 'total',
        marker: { colors, colorscale: GM_SCALE, cmin: Math.max(0, quantile(gmv, 0.05) ?? 0),
          cmax: Math.max(quantile(gmv, 0.95) ?? 50, (quantile(gmv, 0.05) ?? 0) + 1),
          colorbar: { title: { text: 'GM %' }, thickness: 10 }, line: { width: 1.5, color: 'white' } },
        hovertemplate: '<b>%{label}</b><br>₹%{value:,.0f}<br>GM %{color:.1f}%<extra></extra>',
      }], baseLayout(460, false, { margin: { l: 8, r: 8, t: 10, b: 8 } }));
      else document.getElementById('ch-tree').innerHTML = '<div class="caption">Nothing to show in this view.</div>';

      // SKU matrix + table (skus.json)
      const K = salesTyped(GD.skus(sel));
      const bySku = new Map();
      for (const r of K) {
        let o = bySku.get(r.sku);
        if (!o) { o = { sku: r.sku, l1: r.l1, l2: r.l2, qty: 0, revenue: 0, cogs: 0 }; bySku.set(r.sku, o); }
        o.qty += +r.qty || 0; o.revenue += +r.revenue || 0; o.cogs += +r.cogs || 0;
      }
      const skus = [...bySku.values()].filter((o) => o.revenue > 0);
      const ranges = [...new Set(skus.map((o) => o.l1))].sort();
      const traces = ranges.map((l1, i) => {
        const sub = skus.filter((o) => o.l1 === l1);
        return { type: 'scatter', mode: 'markers', name: l1,
          x: sub.map((o) => GD.lakh(o.revenue)), y: sub.map((o) => (o.revenue - o.cogs) / o.revenue * 100),
          marker: { size: 10, color: SERIES[i % SERIES.length], line: { width: 1, color: 'white' } },
          customdata: sub.map((o) => o.sku),
          hovertemplate: '<b>%{customdata}</b><br>₹%{x:.2f} L<br>GM %{y:.1f}%<extra></extra>' };
      });
      const totR = skus.reduce((s, o) => s + o.revenue, 0), totG = skus.reduce((s, o) => s + o.revenue - o.cogs, 0);
      const med = quantile(skus.map((o) => o.revenue), 0.5) || 1;
      plot('ch-skumatrix', traces, baseLayout(460, true, {
        xaxis: Object.assign(baseLayout(0).xaxis, { title: { text: 'Revenue (₹ lakh, log scale)' }, type: 'log' }),
        yaxis: Object.assign(baseLayout(0).yaxis, { title: { text: 'GM %' } }),
        shapes: [
          { type: 'line', xref: 'paper', x0: 0, x1: 1, y0: totG / totR * 100, y1: totG / totR * 100, line: { dash: 'dash', color: '#A6ADB3' } },
          { type: 'line', yref: 'paper', x0: GD.lakh(med), x1: GD.lakh(med), y0: 0, y1: 1, line: { dash: 'dash', color: '#A6ADB3' } }],
      }));

      // SKU table
      const prevBySku = new Map();
      if (hasCmp) for (const r of salesTyped(GD.skus(cmp))) prevBySku.set(r.sku, (prevBySku.get(r.sku) || 0) + (+r.revenue || 0));
      const allRev = [...bySku.values()].reduce((s, o) => s + o.revenue, 0);
      const rows = [...bySku.values()].filter((o) => o.revenue !== 0).map((o) => ({
        sku: o.sku, l1: o.l1, l2: o.l2, qty: Math.round(o.qty), revenue: GD.lakh(o.revenue),
        price: GD.div(o.revenue, o.qty), gm_pct: GD.div(o.revenue - o.cogs, o.revenue),
        growth: hasCmp && prevBySku.get(o.sku) ? GD.growth(o.revenue, prevBySku.get(o.sku)) : null,
        share: GD.div(o.revenue, allRev),
      })).sort((a, b) => b.revenue - a.revenue);
      const cols = [
        { key: 'sku', label: 'SKU', align: 'l' }, { key: 'l1', label: 'Range', align: 'l' }, { key: 'l2', label: 'Category', align: 'l' },
        { key: 'qty', label: 'Units', fmt: GD.num },
        { key: 'revenue', label: 'Revenue (₹ L)', fmt: (v) => v.toFixed(2), bar: (d) => Math.max(...d.map((r) => r.revenue), 0.01) },
        { key: 'price', label: 'Avg price (₹)', fmt: (v) => v == null ? '–' : v.toFixed(1) },
        { key: 'gm_pct', label: 'GM %', fmt: GD.pct, cls: (v) => v != null && v < 0 ? 'neg' : '' }];
      if (hasCmp) cols.push({ key: 'growth', label: 'Growth %', fmt: GD.spct, cls: (v) => v == null ? '' : v < 0 ? 'neg' : 'pos' });
      cols.push({ key: 'share', label: 'Share %', fmt: (v) => GD.pct(v, 2) });
      renderTable('tb-sku', cols, rows, { search: 'Type part of a SKU name', searchKeys: ['sku', 'l1', 'l2'], height: 430, download: { name: 'GO_DESi_SKU_performance.csv', label: 'Download SKU table' } });

      // range trend (stacked area)
      const byRange = sumBy(S, (r) => r.period + '\u0001' + r.l1, ['revenue']);
      const rngNames = [...new Set([...byRange.keys()].map((k) => k.split('\u0001')[1]))].sort();
      const x = sel.map(GD.pm.label);
      plot('ch-range', rngNames.map((l1, i) => ({
        type: 'scatter', x, name: l1, stackgroup: 'one', mode: 'lines',
        y: sel.map((m) => GD.lakh(byRange.get(m + '\u0001' + l1)?.revenue || 0)),
        line: { width: 0.8, color: SERIES[i % SERIES.length] },
        hovertemplate: '₹%{y:.1f} L<extra>' + GD.esc(l1) + '</extra>',
      })), baseLayout(360, true, { hovermode: 'x unified', yaxis: Object.assign(baseLayout(0).yaxis, { title: { text: '₹ lakh' } }) }));

      // pack mix
      const byPack = [...sumBy(S, (r) => r.pack, ['revenue', 'cogs']).entries()]
        .filter(([, o]) => o.revenue > 0).sort((a, b) => b[1].revenue - a[1].revenue);
      plot('ch-pack', [
        { type: 'bar', x: byPack.map(([k]) => k), y: byPack.map(([, o]) => GD.lakh(o.revenue)), name: 'Revenue (₹ L)', marker: { color: C.INDIGO }, hovertemplate: 'Revenue ₹%{y:.1f} L<extra></extra>' },
        { type: 'scatter', x: byPack.map(([k]) => k), y: byPack.map(([, o]) => (o.revenue - o.cogs) / o.revenue * 100), name: 'GM %', yaxis: 'y2', mode: 'lines+markers', line: { color: C.SAFFRON, width: 3 }, hovertemplate: 'GM %{y:.1f}%<extra></extra>' },
      ], baseLayout(360, true, { hovermode: 'x unified', yaxis: Object.assign(baseLayout(0).yaxis, { title: { text: '₹ lakh' } }), yaxis2: { overlaying: 'y', side: 'right', ticksuffix: '%', showgrid: false, tickfont: { color: C.MUTED } } }));
    },
  };
}

/* ============================ CUSTOMERS & REGIONS ============================ */
function viewCustomers(ctx) {
  const { sel, cmp, cmpLabel, hasCmp } = ctx;
  return {
    html: `
      <div class="kpis" id="cust-kpis"></div>
      <div class="grid g12">
        <div class="card">${cardHead('States', 'Revenue and gross margin by state')}<div id="ch-states" class="chart"></div></div>
        <div class="card">${cardHead('Customer concentration', 'How much revenue the top customers carry')}<div id="ch-pareto" class="chart"></div></div>
      </div>
      <div class="card">${cardHead('Customer list', 'Search any distributor. Growth compares with the comparison period.')}<div id="tb-cust"></div></div>
      <div class="grid g2">
        <div class="card">${cardHead('Active customers each month', 'Distinct customers billed')}<div id="ch-active" class="chart"></div></div>
        <div class="card">${cardHead('Not billed this period', 'Billed in the comparison period, nothing in this one. Worth a call.')}<div id="tb-lapsed"></div></div>
      </div>`,
    mount() {
      const cur = GD.cust(sel);
      const byCust = new Map();
      for (const r of cur) {
        let o = byCust.get(r.customer);
        if (!o) { o = { customer: r.customer, state: r.state, rsm: r.rsm, revenue: 0, cogs: 0, invoices: 0, last: '' }; byCust.set(r.customer, o); }
        o.revenue += +r.revenue || 0; o.cogs += +r.cogs || 0; o.invoices += +r.invoices || 0;
        if (+r.revenue > 0 && r.period > o.last) o.last = r.period;
      }
      const prev = new Map();
      if (hasCmp) for (const r of GD.cust(cmp)) prev.set(r.customer, (prev.get(r.customer) || 0) + (+r.revenue || 0));
      const billed = [...byCust.values()].filter((o) => o.revenue > 0);
      const prevBilled = new Set([...prev.entries()].filter(([, v]) => v > 0).map(([k]) => k));
      const tot = billed.reduce((s, o) => s + o.revenue, 0);
      const sorted = billed.slice().sort((a, b) => b.revenue - a.revenue);
      const top10 = sorted.slice(0, 10).reduce((s, o) => s + o.revenue, 0);
      const fresh = hasCmp ? billed.filter((o) => !prevBilled.has(o.customer)) : [];
      const curSet = new Set(billed.map((o) => o.customer));
      const lost = hasCmp ? [...prev.entries()].filter(([k, v]) => v > 0 && !curSet.has(k)) : [];

      document.getElementById('cust-kpis').innerHTML = [
        kpi({ label: 'Billed customers', value: billed.length.toLocaleString(), sub: 'with revenue in period', delta: hasCmp ? GD.growth(billed.length, prevBilled.size) : null, cmpLabel }),
        kpi({ label: 'Revenue per customer', value: GD.inr(GD.div(tot, billed.length)), sub: 'average in period' }),
        kpi({ label: 'Top 10 share', value: GD.pct(GD.div(top10, tot)), sub: 'of revenue from 10 customers' }),
        kpi({ label: 'New customers', value: hasCmp ? fresh.length.toLocaleString() : '–', sub: hasCmp ? GD.inr(fresh.reduce((s, o) => s + o.revenue, 0)) + ' revenue' : 'needs a comparison' }),
        kpi({ label: 'Not billed again', value: hasCmp ? lost.length.toLocaleString() : '–', sub: hasCmp ? GD.inr(lost.reduce((s, [, v]) => s + v, 0)) + ' in comparison period' : 'needs a comparison' }),
      ].join('');

      // states
      const S = GD.sales(sel);
      const byState = [...sumBy(S, (r) => r.zone + '\u0001' + r.state, ['revenue', 'cogs']).entries()]
        .map(([k, o]) => { const [zone, state] = k.split('\u0001'); return { zone, state, ...o }; })
        .filter((o) => o.revenue > 0).sort((a, b) => b.revenue - a.revenue).slice(0, 15).reverse();
      plot('ch-states', [{
        type: 'bar', orientation: 'h', y: byState.map((o) => o.state), x: byState.map((o) => GD.lakh(o.revenue)),
        marker: { color: byState.map((o) => (o.revenue - o.cogs) / o.revenue * 100), colorscale: GM_SCALE, colorbar: { title: { text: 'GM %' }, thickness: 10 } },
        customdata: byState.map((o) => [o.zone, (o.revenue - o.cogs) / o.revenue * 100]),
        hovertemplate: '%{y} (%{customdata[0]})<br>₹%{x:.1f} L · GM %{customdata[1]:.1f}%<extra></extra>',
      }], baseLayout(470, false, { xaxis: Object.assign(baseLayout(0).xaxis, { title: { text: '₹ lakh' } }) }));

      // pareto
      const r = sorted.map((o) => o.revenue);
      let cum = 0;
      const cumPct = r.map((v) => (cum += v) / tot * 100);
      const n80 = cumPct.filter((v) => v < 80).length + 1;
      plot('ch-pareto', [
        { type: 'bar', x: r.slice(0, 40).map((_, i) => i + 1), y: r.slice(0, 40).map(GD.lakh), name: 'Revenue (₹ L)', marker: { color: C.INDIGO }, customdata: sorted.slice(0, 40).map((o) => o.customer), hovertemplate: '#%{x} %{customdata}<br>₹%{y:.1f} L<extra></extra>' },
        { type: 'scatter', x: cumPct.map((_, i) => i + 1), y: cumPct, name: 'Cumulative %', yaxis: 'y2', line: { color: C.SAFFRON, width: 3 }, hovertemplate: 'Top %{x} customers: %{y:.1f}%<extra></extra>' },
      ], baseLayout(470, true, {
        xaxis: Object.assign(baseLayout(0).xaxis, { title: { text: 'Customer rank' }, range: [0.4, Math.max(10, Math.min(r.length, n80 ? n80 * 1.6 : 40))] }),
        yaxis: Object.assign(baseLayout(0).yaxis, { title: { text: '₹ lakh' } }),
        yaxis2: { overlaying: 'y', side: 'right', range: [0, 102], ticksuffix: '%', showgrid: false, tickfont: { color: C.MUTED } },
        annotations: r.length ? [{ x: n80, y: 80, yref: 'y2', text: `${n80} customers = 80%`, showarrow: true, arrowhead: 2, ax: 40, ay: -30 }] : [],
      }));

      // customer table
      const rows = [...byCust.values()].map((o) => ({
        customer: o.customer, state: o.state, rsm: o.rsm, revenue: GD.lakh(o.revenue),
        gm_pct: GD.div(o.revenue - o.cogs, o.revenue), invoices: o.invoices, last: o.last ? GD.pm.label(o.last) : '–',
        prev: hasCmp ? GD.lakh(prev.get(o.customer) || 0) : null,
        growth: hasCmp && prev.get(o.customer) ? GD.growth(o.revenue, prev.get(o.customer)) : null,
      })).sort((a, b) => b.revenue - a.revenue);
      const cols = [
        { key: 'customer', label: 'Customer', align: 'l' }, { key: 'state', label: 'State', align: 'l' }, { key: 'rsm', label: 'RSM', align: 'l' },
        { key: 'revenue', label: 'Revenue (₹ L)', fmt: (v) => v.toFixed(2), bar: (d) => Math.max(...d.map((x) => x.revenue), 0.01) },
        { key: 'gm_pct', label: 'GM %', fmt: GD.pct, cls: (v) => v != null && v < 0 ? 'neg' : '' },
        { key: 'invoices', label: 'Invoices' }, { key: 'last', label: 'Last billed' }];
      if (hasCmp) cols.push(
        { key: 'prev', label: 'Prev (₹ L)', fmt: (v) => v.toFixed(2) },
        { key: 'growth', label: 'Growth %', fmt: GD.spct, cls: (v) => v == null ? '' : v < 0 ? 'neg' : 'pos' });
      renderTable('tb-cust', cols, rows, { search: 'Type part of a customer name', searchKeys: ['customer', 'state', 'rsm'], height: 420, download: { name: 'GO_DESi_customers.csv', label: 'Download customer table' } });

      // active per month
      const act = sel.map((m) => {
        const per = new Map();
        for (const r of cur) if (r.period === m) per.set(r.customer, (per.get(r.customer) || 0) + (+r.revenue || 0));
        return [...per.values()].filter((v) => v > 0).length;
      });
      plot('ch-active', [{
        type: 'scatter', x: sel.map(GD.pm.label), y: act, mode: 'lines+markers+text', text: act, textposition: 'top center',
        line: { color: C.TEAL, width: 3 }, fill: 'tozeroy', fillcolor: 'rgba(31,157,91,0.12)', cliponaxis: false,
      }], baseLayout(320, false, { yaxis: Object.assign(baseLayout(0).yaxis, { range: [0, Math.max(...act, 1) * 1.2] }) }));

      // lapsed
      if (hasCmp && lost.length) {
        renderTable('tb-lapsed',
          [{ key: 'customer', label: 'Customer', align: 'l' }, { key: 'prev', label: 'Comparison revenue (₹ L)', fmt: (v) => v.toFixed(2) }],
          lost.map(([customer, v]) => ({ customer, prev: GD.lakh(v) })).sort((a, b) => b.prev - a.prev),
          { height: 300 });
      } else {
        document.getElementById('tb-lapsed').innerHTML = '<div class="caption">No lapsed customers, or no comparison period selected.</div>';
      }
    },
  };
}

/* ============================ RETURNS & SAMPLING ============================ */
function viewReturns(ctx) {
  const { sel, T } = ctx;
  return {
    html: `
      <div class="kpis" id="ret-kpis"></div>
      <div class="grid g2">
        <div class="card">${cardHead('Returns trend', 'Return value and return rate by month')}<div id="ch-ret" class="chart"></div></div>
        <div class="card">${cardHead('Sampling and trade marketing by RSM', 'Product cost given away, against revenue')}<div id="ch-samp" class="chart"></div></div>
      </div>
      <div class="grid g2">
        <div class="card">${cardHead('Top returning customers')}<div id="tb-retcust"></div></div>
        <div class="card">${cardHead('Top returned SKUs')}<div id="tb-retsku"></div></div>
      </div>`,
    mount() {
      const S = GD.sales(sel);
      const sales = S.filter((r) => r.type === 'Sales');
      const gross = sales.filter((r) => !+r.is_return).reduce((s, r) => s + (+r.revenue || 0), 0);
      const ret = -sales.filter((r) => +r.is_return).reduce((s, r) => s + (+r.revenue || 0), 0);
      const samp = S.filter((r) => r.type === 'Sampling').reduce((s, r) => s + (+r.cogs || 0), 0);
      const tm = S.filter((r) => r.type === 'Trade Marketing').reduce((s, r) => s + (+r.cogs || 0), 0);
      document.getElementById('ret-kpis').innerHTML = [
        kpi({ label: 'Gross sales', value: GD.inr(gross), sub: 'before returns' }),
        kpi({ label: 'Returns', value: GD.inr(ret), sub: GD.pct(GD.div(ret, gross)) + ' of gross sales' }),
        kpi({ label: 'Sampling cost', value: GD.inr(samp), sub: GD.pct(GD.div(samp, T.revenue)) + ' of revenue' }),
        kpi({ label: 'Trade marketing', value: GD.inr(tm), sub: GD.pct(GD.div(tm, T.revenue)) + ' of revenue' }),
        kpi({ label: 'Transport', value: GD.inr(T.transport), sub: GD.pct(GD.div(T.transport, T.revenue)) + ' of revenue' }),
      ].join('');

      // returns trend
      const x = sel.map(GD.pm.label);
      const perM = sel.map((m) => {
        const mm = sales.filter((r) => r.period === m);
        const g = mm.filter((r) => !+r.is_return).reduce((s, r) => s + (+r.revenue || 0), 0);
        const rr = -mm.filter((r) => +r.is_return).reduce((s, r) => s + (+r.revenue || 0), 0);
        return { ret: rr, rate: g ? rr / g * 100 : null };
      });
      plot('ch-ret', [
        { type: 'bar', x, y: perM.map((o) => GD.lakh(o.ret)), name: 'Returns (₹ L)', marker: { color: '#E8846F' }, hovertemplate: 'Returns ₹%{y:.1f} L<extra></extra>' },
        { type: 'scatter', x, y: perM.map((o) => o.rate), name: 'Return rate %', yaxis: 'y2', line: { color: C.INK, width: 3 }, hovertemplate: 'Rate %{y:.1f}%<extra></extra>' },
      ], baseLayout(340, true, { hovermode: 'x unified', yaxis: Object.assign(baseLayout(0).yaxis, { title: { text: '₹ lakh' } }), yaxis2: { overlaying: 'y', side: 'right', ticksuffix: '%', showgrid: false, tickfont: { color: C.MUTED } } }));

      // sampling by RSM
      const byRsm = new Map();
      for (const r of S) {
        let o = byRsm.get(r.rsm);
        if (!o) { o = { samp: 0, tm: 0, rev: 0 }; byRsm.set(r.rsm, o); }
        if (r.type === 'Sampling') o.samp += +r.cogs || 0;
        if (r.type === 'Trade Marketing') o.tm += +r.cogs || 0;
        o.rev += +r.revenue || 0;
      }
      const sr = [...byRsm.entries()].filter(([, o]) => o.samp + o.tm > 0).sort((a, b) => a[1].rev - b[1].rev);
      plot('ch-samp', [
        { type: 'bar', orientation: 'h', y: sr.map(([k]) => k), x: sr.map(([, o]) => GD.lakh(o.samp)), name: 'Sampling', marker: { color: C.SAFFRON }, hovertemplate: '%{y}<br>Sampling ₹%{x:.1f} L<extra></extra>' },
        { type: 'bar', orientation: 'h', y: sr.map(([k]) => k), x: sr.map(([, o]) => GD.lakh(o.tm)), name: 'Trade marketing', marker: { color: C.VIOLET }, hovertemplate: '%{y}<br>Trade marketing ₹%{x:.1f} L<extra></extra>' },
      ], baseLayout(340, true, {
        barmode: 'stack', xaxis: Object.assign(baseLayout(0).xaxis, { title: { text: '₹ lakh' } }),
        annotations: sr.map(([k, o]) => ({ x: GD.lakh(o.samp + o.tm), y: k, text: '  ' + GD.pct(GD.div(o.samp + o.tm, o.rev)) + ' of rev', showarrow: false, xanchor: 'left', font: { color: C.MUTED, size: 11 } })),
      }));

      // top returning customers
      const rc = new Map();
      for (const r of GD.cust(sel)) {
        let o = rc.get(r.customer);
        if (!o) { o = { gross: 0, ret: 0 }; rc.set(r.customer, o); }
        if (+r.is_return) o.ret -= +r.revenue || 0; else o.gross += +r.revenue || 0;
      }
      renderTable('tb-retcust',
        [{ key: 'customer', label: 'Customer', align: 'l' },
         { key: 'ret', label: 'Returns (₹ L)', fmt: (v) => v.toFixed(2) },
         { key: 'rate', label: 'Return rate %', fmt: GD.pct }],
        [...rc.entries()].filter(([, o]) => o.ret > 0).map(([customer, o]) => ({ customer, ret: GD.lakh(o.ret), rate: GD.div(o.ret, o.gross) }))
          .sort((a, b) => b.ret - a.ret).slice(0, 12), {});

      // top returned SKUs
      const rs = new Map();
      for (const r of GD.skus(sel).filter((r) => r.type === 'Sales' && +r.is_return)) {
        let o = rs.get(r.sku);
        if (!o) { o = { units: 0, ret: 0 }; rs.set(r.sku, o); }
        o.units -= +r.qty || 0; o.ret -= +r.revenue || 0;
      }
      renderTable('tb-retsku',
        [{ key: 'sku', label: 'SKU', align: 'l' }, { key: 'units', label: 'Units', fmt: GD.num },
         { key: 'ret', label: 'Returns (₹ L)', fmt: (v) => v.toFixed(2) }],
        [...rs.entries()].filter(([, o]) => o.ret > 0).map(([sku, o]) => ({ sku, units: o.units, ret: GD.lakh(o.ret) }))
          .sort((a, b) => b.ret - a.ret).slice(0, 12), {});
    },
  };
}

/* ============================ EXPLORER ============================ */
const EX_DIMS = {
  period: 'Month', fy: 'Financial year', rsm: 'RSM', asm: 'ASM', zone: 'Zone', state: 'State',
  sub_channel: 'Sub-channel', customer: 'Customer', l0: 'Category', l1: 'Range', l2: 'Sub-category',
  sku: 'SKU', pack: 'Pack type', type: 'Sales / Sampling',
};
const EX_MEAS = {
  revenue: 'Revenue', gm: 'Gross margin', gm_pct: 'GM %', cogs: 'COGS', qty: 'Units',
  transport: 'Transport', contrib: 'Contribution', field: 'Field cost', nm: 'Net margin', nm_pct: 'NM %',
};
const TEAM_DIMS = new Set(['period', 'fy', 'rsm', 'asm']);
const SALES_JSON_DIMS = new Set(['period', 'fy', 'rsm', 'asm', 'zone', 'state', 'sub_channel', 'l0', 'l1', 'l2', 'pack', 'type']);
const CUST_JSON_DIMS = new Set(['period', 'fy', 'customer', 'rsm', 'asm', 'zone', 'state', 'sub_channel']);
const SKU_JSON_DIMS = new Set(['period', 'fy', 'sku', 'rsm', 'asm', 'l0', 'l1', 'l2', 'pack', 'type']);

function viewExplorer(ctx) {
  const { sel, commercial } = ctx;
  const ex = GD.state.ex;
  const selHtml = (id, opts, cur, none) => `<select id="${id}" class="sel">` +
    (none ? `<option value="">(none)</option>` : '') +
    Object.entries(opts).map(([k, l]) => `<option value="${k}"${k === cur ? ' selected' : ''}>${l}</option>`).join('') + '</select>';
  return {
    html: `
      <div class="card">
        <div class="card-s">Build any cut of the data. Pick rows, an optional column split, and a measure.</div>
        <div class="ex-controls">
          <div><label>Rows</label>${selHtml('ex-rows', EX_DIMS, ex.rows)}</div>
          <div><label>Columns</label>${selHtml('ex-cols', EX_DIMS, ex.cols, true)}</div>
          <div><label>Measure</label>${selHtml('ex-meas', EX_MEAS, ex.meas)}</div>
          <div><label>Units</label>${selHtml('ex-unit', { lakh: '₹ lakh', inr: '₹' }, ex.unit)}</div>
        </div>
        <div id="ex-out"></div>
      </div>`,
    mount() {
      for (const [id, key] of [['ex-rows', 'rows'], ['ex-cols', 'cols'], ['ex-meas', 'meas'], ['ex-unit', 'unit']]) {
        document.getElementById(id).addEventListener('change', (e) => { ex[key] = e.target.value; App.render(); });
      }
      const out = document.getElementById('ex-out');
      const rk = ex.rows, ck = ex.cols || null, mk = ex.meas;
      const keys = [rk, ...(ck ? [ck] : [])];
      const people = ['field', 'nm', 'nm_pct'].includes(mk);
      if (people && (commercial || !keys.every((k) => TEAM_DIMS.has(k)))) {
        out.innerHTML = '<div class="note">Field cost and net margin can only be split by Month, Financial year, RSM or ASM, and only with market and product filters cleared.</div>';
        return;
      }
      // choose dataset
      let rows, dims;
      const need = new Set(keys);
      const within = (set) => [...need].every((k) => set.has(k));
      if (within(SALES_JSON_DIMS)) {
        rows = GD.sales(sel); dims = SALES_JSON_DIMS;
        if (people || keys.every((k) => TEAM_DIMS.has(k))) rows = rows.concat(GD.costs(sel));
      } else if (within(CUST_JSON_DIMS)) {
        rows = GD.cust(sel); dims = CUST_JSON_DIMS;
        if (!['revenue', 'gm', 'gm_pct', 'qty'].includes(mk)) { out.innerHTML = '<div class="note">Customer cuts support Revenue, Gross margin, GM % and Units.</div>'; return; }
      } else if (within(SKU_JSON_DIMS)) {
        rows = GD.skus(sel); dims = SKU_JSON_DIMS;
        if (!['revenue', 'gm', 'gm_pct', 'qty'].includes(mk)) { out.innerHTML = '<div class="note">SKU cuts support Revenue, Gross margin, GM % and Units.</div>'; return; }
      } else {
        out.innerHTML = '<div class="note">That combination mixes customer and product detail, which the aggregated data doesn’t carry. Pick dimensions from one family (market/team, customer, or product).</div>';
        return;
      }
      const keyOf = (r, k) => k === 'fy' ? GD.pm.fy(r.period) : r[k];
      const cells = new Map(); // rkey -> Map(ckey -> {sums})
      const sumCols = ['revenue', 'cogs', 'qty', 'transport', 'opex', 'so_salary', 'so_travel', 'so_incentive', 'asm_salary', 'asm_travel', 'asm_incentive', 'rsm_salary', 'rsm_travel', 'rsm_incentive', 'db_claim'];
      for (const r of rows) {
        const a = keyOf(r, rk), b = ck ? keyOf(r, ck) : '_';
        if (!cells.has(a)) cells.set(a, new Map());
        const m = cells.get(a);
        if (!m.has(b)) { const o = {}; sumCols.forEach((c) => { o[c] = 0; }); m.set(b, o); }
        const o = m.get(b);
        for (const c of sumCols) { const v = +r[c]; if (v) o[c] += v; }
      }
      const val = (o) => {
        if (!o) return null;
        const t = GD.derive({ ...o });
        return t[mk];
      };
      const isPct = ['gm_pct', 'nm_pct'].includes(mk);
      let rKeys = [...cells.keys()];
      const cKeys = ck ? [...new Set([].concat(...[...cells.values()].map((m) => [...m.keys()])))] : ['_'];
      if (rk === 'period' || rk === 'fy') rKeys.sort();
      if (ck === 'period' || ck === 'fy') cKeys.sort();
      const rowTotal = (a) => {
        const o = {}; sumCols.forEach((c) => { o[c] = 0; });
        for (const v of cells.get(a).values()) for (const c of sumCols) o[c] += v[c];
        return val(o);
      };
      if (rk !== 'period' && rk !== 'fy') rKeys.sort((a, b) => (rowTotal(b) ?? -Infinity) - (rowTotal(a) ?? -Infinity));
      const fmtV = (v) => v == null ? '–' : isPct ? GD.pct(v) : mk === 'qty' ? GD.num(v) : ex.unit === 'lakh' ? GD.fmtL(v, 2) : GD.num(v);
      const colLabel = (k) => (ck === 'period' ? GD.pm.label(k) : k);
      const rowLabel = (k) => (rk === 'period' ? GD.pm.label(k) : k);
      let html = `<div class="plwrap" style="max-height:60vh"><table class="pl"><thead><tr><th>${EX_DIMS[rk]}</th>` +
        (ck ? cKeys.map((k) => `<th>${GD.esc(colLabel(k))}</th>`).join('') + (isPct ? '' : '<th>Total</th>') : `<th>${EX_MEAS[mk]}</th>`) +
        '</tr></thead><tbody>';
      const csvRows = [];
      for (const a of rKeys.slice(0, 500)) {
        const m = cells.get(a);
        html += `<tr><td>${GD.esc(rowLabel(a))}</td>`;
        const line = [rowLabel(a)];
        for (const b of cKeys) {
          const v = val(m.get(b));
          html += `<td class="${v != null && v < 0 ? 'neg' : ''}">${fmtV(v)}</td>`;
          line.push(v == null ? '' : isPct ? (v * 100).toFixed(1) : Math.round(v));
        }
        if (ck && !isPct) { const t = rowTotal(a); html += `<td class="tot ${t < 0 ? 'neg' : ''}">${fmtV(t)}</td>`; line.push(Math.round(t)); }
        html += '</tr>';
        csvRows.push(line);
      }
      html += '</tbody></table></div>';
      html += `<div class="tfoot"><span class="cnt">${rKeys.length > 500 ? 'Showing 500 of ' + rKeys.length + ' rows' : rKeys.length + ' rows'}</span><button class="btn btn-ghost btn-sm" id="ex-dl" type="button">⬇ Download this table</button></div>`;
      out.innerHTML = html;
      document.getElementById('ex-dl').addEventListener('click', () => {
        const header = [EX_DIMS[rk], ...(ck ? cKeys.map(colLabel) : [EX_MEAS[mk]])].concat(ck && !isPct ? ['Total'] : []);
        GD.downloadCSV(`GO_DESi_${EX_DIMS[rk]}_by_${ck ? EX_DIMS[ck] : 'none'}_${EX_MEAS[mk]}.csv`.replace(/ /g, '_'), header, csvRows);
      });
    },
  };
}

/* ============================ UPLOAD ============================ */
function viewUpload() {
  const up = GD.state.up;
  if (!GD.api) {
    const supa = GD.mode === 'supabase';
    return {
      html: `<div class="card">${cardHead('Upload files', supa
          ? 'This dashboard reads live from Supabase. Adding a month happens on the machine that holds the raw files.'
          : 'This copy of the dashboard is served as static files, so uploads happen on the machine that holds the database.')}
        <div class="step"><div class="n">1</div><div>Drop the month's raw files (ERP sales export, Salary, Expenses, Incentive, DB Claim, and optionally Customer Mapping and Trans %) into the <code>incoming/</code> folder next to the project.</div></div>
        <div class="step"><div class="n">2</div><div>Run <code>python add_month.py</code> — it works out which file is which, calculates everything with the tracker's rules${supa ? ' and pushes the new months to Supabase automatically' : ', stores it in the database and rebuilds the website data'}.</div></div>
        <div class="step"><div class="n">3</div><div>${supa ? 'Reload this page — the new numbers are live. Nothing to redeploy.'
          : 'Redeploy the <code>website/</code> folder. To upload straight from this page instead, run the dashboard with <code>python server.py</code>.'}</div></div></div>`,
      mount() {},
    };
  }
  const r = up.report;
  let body = '';
  if (up.done) {
    body += `<div class="card" style="margin-bottom:12px">${cardHead('Added to the dashboard')}` +
      up.done.map((d) => `<div class="step"><div class="n">✓</div><div>${GD.esc(d)}</div></div>`).join('') +
      `<div class="caption">The numbers everywhere on this site now include these rows.</div></div>`;
  }
  body += `<div class="card" style="margin-bottom:12px">
    ${cardHead('Drop the month’s files', 'Everything in one go — the dashboard works out which file is which from the column headings: ERP sales export, Salary, Expenses, Incentive, DB Claim, Customer Mapping, Trans %.')}
    ${GD.api.needs_token ? `<div style="margin-bottom:10px"><input type="password" class="tsearch" id="up-token" placeholder="Access token" value="${GD.esc(up.dashToken)}"></div>` : ''}
    <input type="file" id="up-files" multiple accept=".xlsx,.xlsm,.csv" style="margin-bottom:10px">
    <div><button class="btn" id="up-go" type="button"${up.busy ? ' disabled' : ''}>${up.busy ? 'Calculating…' : 'Upload & calculate'}</button></div>
    <div id="up-err" class="note" hidden style="margin-top:10px"></div>
  </div>`;
  if (r) {
    if (r.files && r.files.length) {
      body += `<div class="card" style="margin-bottom:12px">${cardHead('Files recognised')}` +
        r.files.map((f) => `<div class="step"><div class="n">${f.kinds.length ? '✓' : '?'}</div><div><b>${GD.esc(f.name)}</b> — ${f.kinds.length ? GD.esc(f.kinds.join(', ')) : 'not recognised'}</div></div>`).join('') + '</div>';
    }
    if (r.errors && r.errors.length) {
      body += r.errors.map((e) => `<div class="note">${GD.esc(e)}</div>`).join('');
    }
    if (r.sales) {
      const s = r.sales;
      body += `<div class="card" style="margin-bottom:12px">${cardHead('Sales ready', `${s.rows.toLocaleString()} invoice lines for ${GD.esc(s.months.join(', '))}`)}
        <div class="kpis">
          ${kpi({ label: 'Revenue', value: GD.inr(s.revenue) })}
          ${kpi({ label: 'COGS', value: GD.inr(s.cogs) })}
          ${kpi({ label: 'Gross margin', value: GD.pct((s.revenue - s.cogs) / (s.revenue || 1)) })}
          ${kpi({ label: 'Transport', value: GD.inr(s.transport) })}
          ${kpi({ label: 'Operating exp', value: GD.inr(s.opex) })}
        </div>
        ${s.replaced ? `<div class="caption">Replaces ${s.replaced.toLocaleString()} sales lines already in the data for these months.</div>` : ''}
        ${s.unmapped && s.unmapped.length ? `<div class="note"><b>${s.unmapped.length + s.unmapped_more} customer(s) are not in the mapping</b> and will show under Unassigned: ${GD.esc(s.unmapped.join(', '))}${s.unmapped_more ? ' …' : ''}</div>` : ''}
        ${s.rate_misses && s.rate_misses.length ? `<div class="note">No transport % in the Trans % sheet for: ${GD.esc(s.rate_misses.map((x) => x.join(' ')).join('; '))}. They use 4%.</div>` : ''}
        ${s.bad_date ? `<div class="note">${s.bad_date} row(s) had no readable date and were left out.</div>` : ''}
        ${s.missing_optional && s.missing_optional.length ? `<div class="caption">Columns not found in the export, left blank: ${GD.esc(s.missing_optional.join(', '))}</div>` : ''}
      </div>`;
    }
    if (r.costs && r.costs.months.length) {
      const idx = up.costIdx == null ? r.costs.default : up.costIdx;
      const cm = r.costs.months[idx];
      body += `<div class="card" style="margin-bottom:12px">${cardHead('Field costs ready', 'Salary, travel, incentive and DB claim are built for one month at a time.')}
        <div class="controls">
          <span><span class="lbl">Cost month</span><select id="up-cm" class="sel" style="width:auto">${r.costs.months.map((m, i) => `<option value="${i}"${i === idx ? ' selected' : ''}>${GD.esc(m.label)}</option>`).join('')}</select></span>
          <label style="font-weight:600"><input type="checkbox" id="up-split"${up.split ? ' checked' : ''}> Share Satnam Singh’s RSM cost across North, Maharashtra and East</label>
        </div>
        <div class="kpis">
          ${kpi({ label: 'Cost lines', value: cm.rows.toLocaleString() })}
          ${kpi({ label: 'Salary', value: GD.inr(cm.salary) })}
          ${kpi({ label: 'Travel', value: GD.inr(cm.travel) })}
          ${kpi({ label: 'Incentive', value: GD.inr(cm.incentive) })}
          ${kpi({ label: 'DB claim', value: GD.inr(cm.db_claim) })}
        </div>
        ${cm.replaced ? `<div class="caption">Replaces ${cm.replaced.toLocaleString()} cost lines already in the data for ${GD.esc(cm.label)}.</div>` : ''}
        ${cm.unknown && cm.unknown.length ? cm.unknown.map((u) => `<div class="note">${GD.esc(u)} — not SO, ASM, ASE or RSM, left out.</div>`).join('') : ''}
        ${!r.costs.has_salary ? '<div class="note">Without the Salary sheet, travel and incentive rows keep the RSM and ASM written in their own sheet.</div>' : ''}
      </div>`;
    }
    if (r.token && (r.sales || (r.costs && r.costs.months.length))) {
      body += `<div class="card"><button class="btn" id="up-commit" type="button"${up.busy ? ' disabled' : ''}>${up.busy ? 'Adding…' : 'Add to the dashboard'}</button>
        <div class="caption">This writes to the database and replaces any rows already there for the same months. The tracker Excel can be downloaded any time from the Data page.</div></div>`;
    }
  }
  const hist = (GD.api.history || []).slice(0, 8);
  if (hist.length) {
    body += `<div class="card" style="margin-top:12px">${cardHead('Recent changes', 'What was added to the database lately')}` +
      hist.map((h) => `<div class="step"><div class="n">•</div><div><b>${GD.esc(h.what)}</b> ${GD.esc(h.months)} — ${h.added.toLocaleString()} rows added${h.replaced ? ', ' + h.replaced.toLocaleString() + ' replaced' : ''} <span style="color:var(--muted)">(${GD.esc(h.at)})</span></div></div>`).join('') + '</div>';
  }
  return {
    html: body,
    mount() {
      const tok = document.getElementById('up-token');
      if (tok) tok.addEventListener('input', () => { up.dashToken = tok.value; });
      const hdrs = () => up.dashToken ? { 'X-Dash-Token': up.dashToken } : {};
      const showErr = (msg) => { const e = document.getElementById('up-err'); if (e) { e.hidden = false; e.textContent = msg; } };
      const go = document.getElementById('up-go');
      if (go) go.addEventListener('click', async () => {
        const inp = document.getElementById('up-files');
        if (!inp.files.length) { showErr('Pick the month’s files first.'); return; }
        up.busy = true; up.done = null; App.render();
        try {
          const fd = new FormData();
          for (const f of inp.files) fd.append('files', f);
          const resp = await fetch('./api/upload', { method: 'POST', body: fd, headers: hdrs() });
          const j = await resp.json();
          if (!resp.ok) throw new Error(j.error || ('HTTP ' + resp.status));
          up.report = j; up.token = j.token || null; up.costIdx = null;
        } catch (e) {
          up.report = null; up.token = null;
          up.busy = false; App.render(); showErr(e.message); return;
        }
        up.busy = false; App.render();
      });
      const cm = document.getElementById('up-cm');
      if (cm) cm.addEventListener('change', () => { up.costIdx = +cm.value; App.render(); });
      const sp = document.getElementById('up-split');
      if (sp) sp.addEventListener('change', () => { up.split = sp.checked; });
      const commit = document.getElementById('up-commit');
      if (commit) commit.addEventListener('click', async () => {
        up.busy = true; App.render();
        try {
          const resp = await fetch('./api/commit', {
            method: 'POST',
            headers: Object.assign({ 'Content-Type': 'application/json' }, hdrs()),
            body: JSON.stringify({
              token: up.token, split: up.split,
              cost_month_index: up.costIdx == null ? (up.report.costs ? up.report.costs.default : null) : up.costIdx,
            }),
          });
          const j = await resp.json();
          if (!resp.ok) throw new Error(j.error || ('HTTP ' + resp.status));
          up.done = j.done; up.report = null; up.token = null; up.busy = false;
          await App.refreshAfterCommit();
        } catch (e) {
          up.busy = false; App.render(); showErr(e.message);
        }
      });
    },
  };
}

/* ============================ DATA ============================ */
function viewData() {
  const m = GD.data.meta || {};
  return {
    html: `
      <div class="meta-grid">
        ${kpi({ label: 'Source file', value: `<span style="font-size:1.05rem">${GD.esc(m.source || '–')}</span>`, sub: 'Base sheet' })}
        ${kpi({ label: 'Tracker last modified', value: `<span style="font-size:1.05rem">${GD.esc(m.source_modified || '–')}</span>` })}
        ${kpi({ label: 'Site data generated', value: `<span style="font-size:1.05rem">${GD.esc(m.generated || '–')}</span>` })}
        ${kpi({ label: 'Rows in Base sheet', value: GD.num(m.base_rows), sub: `${GD.num(m.sales_rows)} sales lines · ${GD.num(m.cost_rows)} cost lines` })}
      </div>
      <div class="grid g2">
        <div class="card">
          ${cardHead('How the data flows', 'The database (retail_pnl.db) is the source of truth; Excel is an export.')}
          ${GD.api
            ? `<div class="step"><div class="n">1</div><div>Add a month on the <b>Upload files</b> page (or with <code>python add_month.py</code>): drop the raw ERP and cost files, check the calculated numbers, add them. They go straight into the database.</div></div>
               <div class="step"><div class="n">2</div><div>The dashboard rebuilds its numbers from the database automatically — nothing to redeploy.</div></div>
               <div class="step"><div class="n">⬇</div><div><a href="./api/export">Download the tracker as Excel</a> — the whole Base sheet, built from the database, same layout as P_L_tracker_retail_New.xlsx.</div></div>`
            : GD.mode === 'supabase'
            ? `<div class="step"><div class="n">1</div><div>This page reads live from <b>Supabase</b>: every chart queries the database when the page loads, behind the sign-in.</div></div>
               <div class="step"><div class="n">2</div><div>To add a month: drop the raw files in <code>incoming/</code> and run <code>python add_month.py</code> — it calculates everything and pushes the changed months to Supabase. Reload to see them.</div></div>
               <div class="step"><div class="n">3</div><div>Need the Excel tracker back? <code>python db.py --export P_L_tracker_retail_New.xlsx</code> on the machine that holds the data.</div></div>`
            : `<div class="step"><div class="n">1</div><div>Drop the month's raw files in <code>incoming/</code> and run <code>python add_month.py</code> — it calculates everything, stores it in the database and rebuilds <code>website/data/</code>.</div></div>
               <div class="step"><div class="n">2</div><div>Redeploy the <code>website/</code> folder (or just <code>website/data/</code>). Run the dashboard with <code>python server.py</code> instead to upload from the browser and skip redeploys.</div></div>
               <div class="step"><div class="n">3</div><div>Need the Excel tracker back? <code>python db.py --export P_L_tracker_retail_New.xlsx</code>.</div></div>`}
        </div>
        <div class="card">
          ${cardHead('What the dashboard reads', 'Aggregates built from the Base sheet, not the raw invoice lines.')}
          <div class="step"><div class="n">₹</div><div><b>sales.json</b> — invoice lines summed by month, RSM, ASM, zone, state, channel, category, range, sub-category, pack and type.</div></div>
          <div class="step"><div class="n">\u{1F465}</div><div><b>costs.json</b> — field-team cost lines (salary, travel, incentive, DB claim) by month, RSM and ASM.</div></div>
          <div class="step"><div class="n">\u{1F4E6}</div><div><b>skus.json</b> and <b>customers.json</b> — SKU-level and customer-level cuts for the tables.</div></div>
          <div class="step"><div class="n">\u{1F4C5}</div><div><b>daily.json</b> — daily billing for the rhythm heatmap.</div></div>
        </div>
      </div>`,
    mount() {},
  };
}
