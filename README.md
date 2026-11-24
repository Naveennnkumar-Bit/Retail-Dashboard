# GO DESi | Retail P&L — website

A web version of the Retail P&L dashboard. The data lives in a **SQLite database**
(`retail_pnl.db`); the dashboard is plain HTML + JavaScript, served either by the
built-in Python server (with browser uploads) or as static files. Either way it can
sit under a sub-path such as `https://kioskdash.godesi.in/sales`.

## What's in here

| Path | What it is |
|---|---|
| `retail_pnl.db` | **The data.** One SQLite file, the source of truth (back it up by copying it) |
| `db.py` | Database layer: `--import` a tracker xlsx, `--export` one back, `--stats` |
| `server.py` | Web server: serves the dashboard + browser upload of raw monthly files |
| `add_month.py` | Same upload flow from the command line (`incoming/` folder) |
| `build_site_data.py` | Rebuilds `website/data/*.json` (for static hosting) |
| `aggregates.py`, `dump.py` | Shared calculation logic (dump.py is the tracker's rules) |
| `website/` | The dashboard front end |
| `P_L_tracker_retail_New.xlsx` | The old tracker — now an import/export format |
| `app (8).py` | The old Streamlit app (kept for reference) |

Views: Overview, P&L statement, Sales team, Products, Customers & regions,
Returns & sampling, Explorer (pivot any cut), Upload files, Data. Filters: period
presets + custom range, compare vs last year / previous period, RSM, ASM, zone,
state, channel, type, category, range. As in the tracker, field costs are booked by
RSM/ASM, so market/product filters show margins up to contribution.

## First-time setup

```bash
pip install pandas python-calamine flask waitress xlsxwriter openpyxl
python db.py --import P_L_tracker_retail_New.xlsx   # already done on this machine
python server.py                                    # http://localhost:8173
```

## Adding a month

**From the browser** (server mode): open the dashboard → **Upload files** → drop the
month's raw files (ERP sales export, Salary, Expenses, Incentive, DB Claim, and
optionally Customer Mapping and Trans %) → check the calculated preview → **Add to
the dashboard**. Rows for the same months are replaced, the dashboard refreshes
itself. The rules are the tracker's own: transport % per RSM from the Trans % sheet
(4% when missing, flagged), opex 2% of revenue, RSM/ASM from the mapping (or from
what's already in the data), salary/travel/incentive by position, DB claims, and the
Satnam Singh three-way split.

**From the command line**: drop the files in `incoming/` and run
`python add_month.py` (`--dry-run` to preview, `--cost-month "Sep 2026"`,
`--no-split` as needed).

**Excel out**: Data page → "Download the tracker as Excel", or
`python db.py --export out.xlsx`. The workbook has the same Base sheet layout, so
the old tracker/Streamlit workflow still works on it.

## Going live: Supabase + Cloudflare Pages + GoDaddy DNS

The production setup (same pattern as the Kiosk dashboard): data in **Supabase**
behind a **sign-in**, site served as static files by **Cloudflare Pages**, your
subdomain pointed at it with a **GoDaddy CNAME**.

### 1. Supabase (once)

1. [supabase.com](https://supabase.com) → New project (pick Mumbai / `ap-south-1`).
2. SQL Editor → paste **`supabase/schema.sql`** → Run. This creates the `base`
   table and the `dash_*` read functions the website calls.
3. **Authentication → Sign In / Providers → turn OFF "Allow new users to sign up".**
   Anyone who can sign up can read the numbers, so sign-ups must be closed.
4. Authentication → Users → **Add user** → email + password, tick auto-confirm.
   One per person who should see the dashboard.
5. Project Settings → API:
   - **Project URL** and **anon public key** → paste into `website/config.js`.
   - **service_role key** → put into `supabase_creds.json` next to this README:
     ```json
     {"url": "https://xxxx.supabase.co", "service_key": "eyJ..."}
     ```
     The service key can read and write everything — it stays on your machine
     only: never in `config.js`, never in the `website/` folder, never in Git.

### 2. Push the data

```bash
python supa_sync.py --full     # wipe Supabase and push all of retail_pnl.db
python supa_sync.py --check    # confirm the counts match
```

From now on `python add_month.py` pushes changed months to Supabase
automatically after every monthly update — the live site refreshes itself,
nothing to redeploy.

### 3. Cloudflare Pages

```bash
python package_site.py         # builds dist/ = website/ minus the data/ folder
```

(`data/` holds the unauthenticated JSON files for local use; they must never go
to a public host — online, the site reads from Supabase behind the login.)

Then either drag-and-drop **dist/** at dash.cloudflare.com → Workers & Pages →
Create → Pages → *Upload assets*, or:

```bash
npx wrangler pages deploy dist --project-name retail-pnl
```

You get `retail-pnl.pages.dev` — open it, sign in, check the numbers.

### 4. GoDaddy DNS

1. Cloudflare Pages → your project → **Custom domains** → Add
   `kioskdash.godesi.in` (or `pnl.godesi.in` — any subdomain). Cloudflare shows
   the CNAME to create.
2. GoDaddy → godesi.in → DNS → **Add record**:
   `Type CNAME · Name kioskdash · Value retail-pnl.pages.dev`.
3. Back in Cloudflare, the domain validates within minutes and HTTPS is issued
   automatically. Done: https://kioskdash.godesi.in, with sign-in.

Notes: a Pages custom domain is a whole subdomain, so the address is
`kioskdash.godesi.in`, not a `/sales` path. The anon key in `config.js` is
public by design; the row-level security in `schema.sql` means it can read
nothing without a signed-in user.

## Local / LAN deployment (alternative)

### Option A — server mode (browser uploads work)

Run the app on the server and proxy the sub-path to it:

```bash
# on the server (Linux: use a systemd unit; Windows: NSSM or a scheduled task)
DASH_TOKEN=pick-a-secret waitress-serve --listen=127.0.0.1:8173 server:app
```

```nginx
server {
    server_name kioskdash.godesi.in;
    # ... listen / ssl ...
    location /sales/ {
        proxy_pass http://127.0.0.1:8173/;
        proxy_set_header Host $host;
        client_max_body_size 200m;    # uploads
    }
    location = /sales { return 301 /sales/; }
}
```

`DASH_TOKEN` guards the upload/commit endpoints — the Upload page asks for it.
Viewing stays open, so if the numbers themselves are confidential (they are:
margins and aggregate salaries), put the whole `location` behind `auth_basic`,
Cloudflare Access or your VPN.

### Option B — static mode (no server process)

`python build_site_data.py` then copy `website/` to the server and serve it as
files (nginx `alias`, Netlify, GitHub Pages, S3…). Everything works except the
browser Upload page, which then shows the CLI instructions instead. Redeploy
`website/data/` after each `add_month.py` run.

```nginx
location /sales/ {
    alias /var/www/kioskdash/sales/;
    index index.html;
    gzip on; gzip_types application/json text/css application/javascript;
}
```

## Notes

- Net margin = gross margin − transport − opex − field team cost (SO + ASM + RSM
  salaries/travel/incentives + DB claims), matching the tracker's "YTD & L3M
  Summary" pivot. Verified against pandas on the full Base sheet to the rupee.
- Back up `retail_pnl.db` before big changes (it's a single file). Every upload is
  logged in it (see `python db.py --stats`), and `db.py --export` can reproduce the
  tracker at any time.
- Charts use Plotly from its CDN and fonts from Google Fonts; for a fully offline
  intranet, download `plotly-2.35.2.min.js` next to `index.html` and change the
  script tag.
