/* GO DESi | Retail P&L — boot, filter bar, routing. */
'use strict';

const App = { ms: {} };

App.PAGES = ['overview', 'pl', 'team', 'products', 'customers', 'returns', 'explorer', 'upload', 'data'];
App.sb = null;          // Supabase client when config.js is filled in

App.loadData = async function () {
  const names = ['sales', 'costs', 'skus', 'customers', 'daily', 'meta'];
  let parsed;
  if (App.sb) {
    const rpcs = ['dash_sales', 'dash_costs', 'dash_skus', 'dash_customers', 'dash_daily', 'dash_meta'];
    parsed = await Promise.all(rpcs.map(async (fn) => {
      const { data, error } = await App.sb.rpc(fn);
      if (error) throw new Error(fn + ': ' + error.message);
      return data;
    }));
  } else {
    const res = await Promise.all(names.map((n) => fetch(`./data/${n}.json`, { cache: 'no-cache' })));
    for (const r of res) if (!r.ok) throw new Error(`${r.url.split('/').pop()}: HTTP ${r.status}`);
    parsed = await Promise.all(res.map((r) => r.json()));
  }
  names.forEach((n, i) => { GD.data[n] = parsed[i]; });
  GD.months = [...new Set(GD.data.sales.map((r) => r.period))].sort();
  GD.latest = GD.months[GD.months.length - 1];
  GD.curFY = GD.pm.fy(GD.latest);
  GD.fys = [...new Set(GD.months.map(GD.pm.fy))].sort();
  const meta = GD.data.meta || {};
  document.getElementById('pill').textContent = 'Updated ' + (meta.source_modified || meta.generated || '').split(' ')[0];
};

App.loadStatus = async function () {
  if (App.sb) { GD.api = null; return; }   // live-data mode: updates happen via add_month.py, not this page
  try {
    const r = await fetch('./api/status', { cache: 'no-cache' });
    GD.api = r.ok ? await r.json() : null;
  } catch (e) { GD.api = null; }
};

App.boot = async function () {
  const cfg = window.GD_CONFIG || {};
  if (cfg.supabaseUrl && cfg.supabaseAnonKey && window.supabase) {
    GD.mode = 'supabase';
    App.sb = window.supabase.createClient(cfg.supabaseUrl, cfg.supabaseAnonKey);
    App.initLogin();
    let session = null;
    try { session = (await App.sb.auth.getSession()).data.session; } catch (e) { /* treated as signed out */ }
    if (!session) { App.showLogin(); return; }   // App.start() runs after sign-in
  } else {
    GD.mode = 'static';
  }
  await App.start();
};

App.start = async function () {
  document.getElementById('login').hidden = true;
  document.getElementById('loading').hidden = false;
  try {
    await App.loadData();
  } catch (e) {
    document.getElementById('loading').hidden = true;
    const err = document.getElementById('err');
    err.hidden = false;
    document.getElementById('err-msg').textContent = App.sb
      ? 'The dashboard could not read from Supabase (' + e.message + '). Check that schema.sql was run in the SQL Editor, '
        + 'that this user is confirmed in Authentication, and that data was pushed with: python supa_sync.py --full'
      : 'The dashboard could not fetch its data files (' + e.message + '). '
        + 'Make sure the website/data/ folder was deployed next to index.html, and that you are not opening index.html straight from disk — serve it over HTTP.';
    return;
  }
  await App.loadStatus();

  App.initFilters();
  App.initNav();

  if (App.sb) {
    const out = document.getElementById('btn-logout');
    out.hidden = false;
    out.addEventListener('click', async () => { try { await App.sb.auth.signOut(); } catch (e) {} location.reload(); });
  }

  document.getElementById('loading').hidden = true;
  document.getElementById('app').hidden = false;

  const h = (location.hash || '').replace('#', '');
  if (App.PAGES.includes(h)) GD.state.page = h;
  App.setPage(GD.state.page, false);
};

/* ---------- login (Supabase mode) ---------- */
App.showLogin = function () {
  document.getElementById('loading').hidden = true;
  document.getElementById('login').hidden = false;
};

App.initLogin = function () {
  const form = document.getElementById('login-form');
  if (!form || form.dataset.wired) return;
  form.dataset.wired = '1';
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('login-go');
    const errBox = document.getElementById('login-err');
    errBox.hidden = true;
    btn.disabled = true; btn.textContent = 'Signing in…';
    try {
      const { error } = await App.sb.auth.signInWithPassword({
        email: document.getElementById('login-email').value.trim(),
        password: document.getElementById('login-pass').value,
      });
      if (error) throw new Error(error.message);
      await App.start();
    } catch (err2) {
      errBox.hidden = false;
      errBox.textContent = 'Could not sign in: ' + err2.message;
    }
    btn.disabled = false; btn.textContent = 'Sign in';
  });
};

/* After a commit on the Upload page: pull fresh data and rebuild the period options. */
App.refreshAfterCommit = async function () {
  await App.loadData();
  await App.loadStatus();
  const f = GD.state.f;
  const per = document.getElementById('f-period');
  const opts = [
    ['ytd', GD.curFY + ' YTD'], ['latest', 'Latest month'], ['l3m', 'Last 3 months'],
    ['l6m', 'Last 6 months'], ['l12m', 'Last 12 months'],
    ...GD.fys.slice().reverse().filter((fy) => fy !== GD.curFY).map((fy) => [fy, fy]),
    ['all', 'All months'], ['custom', 'Custom range'],
  ];
  const keep = f.period;
  per.innerHTML = opts.map(([v, l]) => `<option value="${v}">${l}</option>`).join('');
  per.value = opts.some(([v]) => v === keep) ? keep : 'ytd';
  f.period = per.value;
  const mopts = GD.months.map((m) => `<option value="${m}">${GD.pm.label(m)}</option>`).join('');
  const from = document.getElementById('f-from'), to = document.getElementById('f-to');
  from.innerHTML = mopts; to.innerHTML = mopts;
  from.value = GD.months.includes(f.from) ? f.from : GD.months[Math.max(0, GD.months.length - 6)];
  to.value = GD.months.includes(f.to) ? f.to : GD.latest;
  f.from = from.value; f.to = to.value;
  App.render();
};

/* ---------- filters ---------- */
App.initFilters = function () {
  const f = GD.state.f;

  // period select
  const per = document.getElementById('f-period');
  const opts = [
    ['ytd', GD.curFY + ' YTD'], ['latest', 'Latest month'], ['l3m', 'Last 3 months'],
    ['l6m', 'Last 6 months'], ['l12m', 'Last 12 months'],
    ...GD.fys.slice().reverse().filter((fy) => fy !== GD.curFY).map((fy) => [fy, fy]),
    ['all', 'All months'], ['custom', 'Custom range'],
  ];
  per.innerHTML = opts.map(([v, l]) => `<option value="${v}">${l}</option>`).join('');
  per.value = f.period;
  per.addEventListener('change', () => { f.period = per.value; App.syncCustom(); App.render(); });

  // custom range
  const from = document.getElementById('f-from'), to = document.getElementById('f-to');
  const mopts = GD.months.map((m) => `<option value="${m}">${GD.pm.label(m)}</option>`).join('');
  from.innerHTML = mopts; to.innerHTML = mopts;
  from.value = GD.months[Math.max(0, GD.months.length - 6)];
  to.value = GD.latest;
  f.from = from.value; f.to = to.value;
  from.addEventListener('change', () => { f.from = from.value; App.render(); });
  to.addEventListener('change', () => { f.to = to.value; App.render(); });

  // compare
  const cmp = document.getElementById('f-cmp');
  cmp.value = f.cmp;
  cmp.addEventListener('change', () => { f.cmp = cmp.value; App.render(); });

  // multiselects
  const mk = (id, key, placeholder) => {
    App.ms[key] = new MSelect(id, { placeholder, onChange: () => { f[key] = App.ms[key].values; App.render(); } });
  };
  mk('ms-rsm', 'rsm', 'All RSMs');
  mk('ms-asm', 'asm', 'All ASMs');
  mk('ms-zone', 'zone', 'All zones');
  mk('ms-state', 'state', 'All states');
  mk('ms-chan', 'chan', 'All channels');
  mk('ms-type', 'type', 'All types');
  mk('ms-l0', 'l0', 'All categories');
  mk('ms-l1', 'l1', 'All ranges');
  App.syncOptions();

  // more-filters popover
  const pop = document.getElementById('more-pop');
  const moreBtn = document.getElementById('btn-more');
  moreBtn.addEventListener('click', (e) => { e.stopPropagation(); pop.hidden = !pop.hidden; });
  pop.addEventListener('click', (e) => e.stopPropagation());
  document.addEventListener('click', () => { pop.hidden = true; });

  // reset
  document.getElementById('btn-reset').addEventListener('click', () => {
    Object.assign(f, { period: 'ytd', cmp: 'ly', rsm: [], asm: [], zone: [], state: [], chan: [], l0: [], l1: [], type: [] });
    per.value = 'ytd'; cmp.value = 'ly';
    for (const k of Object.keys(App.ms)) App.ms[k].set([]);
    App.syncCustom(); App.render();
  });

  App.syncCustom();
};

App.syncCustom = function () {
  document.getElementById('f-custom-wrap').hidden = GD.state.f.period !== 'custom';
};

App.syncOptions = function () {
  const f = GD.state.f;
  const S = GD.data.sales;
  const uniq = (rows, k) => [...new Set(rows.map((r) => r[k]))].sort();
  App.ms.rsm.setOptions(uniq(S.concat(GD.data.costs), 'rsm'));
  App.ms.asm.setOptions(uniq(f.rsm.length ? S.concat(GD.data.costs).filter((r) => f.rsm.includes(r.rsm)) : S.concat(GD.data.costs), 'asm'));
  App.ms.zone.setOptions(uniq(S, 'zone'));
  App.ms.state.setOptions(uniq(f.zone.length ? S.filter((r) => f.zone.includes(r.zone)) : S, 'state'));
  App.ms.chan.setOptions(uniq(S, 'sub_channel'));
  App.ms.type.setOptions(uniq(S, 'type'));
  App.ms.l0.setOptions(uniq(S, 'l0'));
  App.ms.l1.setOptions(uniq(f.l0.length ? S.filter((r) => f.l0.includes(r.l0)) : S, 'l1'));
  // selections may have been trimmed by setOptions
  for (const k of Object.keys(App.ms)) f[k] = App.ms[k].values;
};

/* ---------- nav ---------- */
App.initNav = function () {
  document.querySelectorAll('#nav button').forEach((b) =>
    b.addEventListener('click', () => App.setPage(b.dataset.page, true)));
  window.addEventListener('hashchange', () => {
    const h = (location.hash || '').replace('#', '');
    if (h && h !== GD.state.page && App.PAGES.includes(h)) App.setPage(h, false);
  });
};

App.setPage = function (page, pushHash) {
  GD.state.page = page;
  document.querySelectorAll('#nav button').forEach((b) => b.classList.toggle('on', b.dataset.page === page));
  if (pushHash) { try { history.replaceState(null, '', '#' + page); } catch (e) { /* file:// */ } }
  App.render();
};

/* ---------- render ---------- */
App.render = function () {
  App.syncOptions();
  const M = GD.selection();
  const T = GD.totAll(M.sel);
  const P = GD.totAll(M.cmp);
  const commercial = GD.commercial();
  const trailMonths = GD.months.filter((m) => m <= M.sel[M.sel.length - 1]).slice(-12);
  const trail = trailMonths.map((m) => GD.totAll([m]));
  const ctx = { ...M, T, P, commercial, trail, trailMonths };

  // chips
  const f = GD.state.f;
  const chips = [`Showing <b>${GD.esc(GD.periodLabel(M.sel))}</b>`];
  if (M.hasCmp) chips.push(`Compared with <b>${GD.esc(GD.periodLabel(M.cmp))}</b>`);
  for (const [lab, v] of [['RSM', f.rsm], ['ASM', f.asm], ['Zone', f.zone], ['State', f.state], ['Channel', f.chan], ['Category', f.l0], ['Range', f.l1], ['Type', f.type]]) {
    if (v.length) chips.push(`${lab}: <b>${GD.esc(v.slice(0, 2).join(', '))}${v.length > 2 ? ' +' + (v.length - 2) : ''}</b>`);
  }
  document.getElementById('chips').innerHTML = chips.map((c) => `<span class="fchip">${c}</span>`).join('');

  // notes
  const n = [];
  if (commercial) n.push('Field team costs (salaries, travel, incentives, DB claims) are booked by RSM and ASM, not by region, product or channel. With market or product filters on, margins show up to <b>contribution</b>. Clear them to see net margin.');
  document.getElementById('notes').innerHTML = n.map((x) => `<div class="note">${x}</div>`).join('');

  // more-filters count
  const more = [f.zone, f.state, f.chan, f.l0, f.l1, f.type].filter((v) => v.length).length;
  document.getElementById('btn-more').textContent = more ? `Filters · ${more}` : 'Filters';

  const views = { overview: viewOverview, pl: viewPL, team: viewTeam, products: viewProducts,
    customers: viewCustomers, returns: viewReturns, explorer: viewExplorer, upload: viewUpload, data: viewData };
  const v = views[GD.state.page](ctx);
  const pageEl = document.getElementById('page');
  pageEl.innerHTML = v.html;
  v.mount();
};

document.addEventListener('DOMContentLoaded', App.boot);
