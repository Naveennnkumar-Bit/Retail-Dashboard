"""
Package the website for Cloudflare Pages -> dist/ folder.

    python package_site.py

Copies website/ to dist/ WITHOUT the data/ folder. On Cloudflare the dashboard reads
from Supabase behind the sign-in; the data/ JSONs are unauthenticated files and must
never be uploaded to a public host. The script refuses to package if config.js has
no Supabase settings (the site would show an empty error page online).
"""
import os
import re
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(HERE, "website")
DIST = os.path.join(HERE, "dist")

with open(os.path.join(SITE, "config.js"), encoding="utf-8") as fh:
    cfg = fh.read()
url = re.search(r'supabaseUrl:\s*"([^"]*)"', cfg)
key = re.search(r'supabaseAnonKey:\s*"([^"]*)"', cfg)
if not (url and url.group(1).strip() and key and key.group(1).strip()):
    raise SystemExit("website/config.js has no Supabase URL / anon key yet.\n"
                     "Fill them in first (Supabase Dashboard -> Project Settings -> API), or the site\n"
                     "would go online with no data source. Nothing was packaged.")
if "service_role" in cfg.lower() or len(key.group(1)) > 400:
    raise SystemExit("config.js seems to hold a service key. Only the anon/public key may go on the website. Nothing was packaged.")

if os.path.exists(DIST):
    shutil.rmtree(DIST)
shutil.copytree(SITE, DIST, ignore=shutil.ignore_patterns("data"))
n = sum(len(f) for _, _, f in os.walk(DIST))
print(f"dist/ ready: {n} files, no data/ folder.")
print("Upload the dist/ folder to Cloudflare Pages (or: npx wrangler pages deploy dist --project-name retail-pnl).")
