"""Regenerate index-offline-test.html by baking dashboard-data.json inline."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

data = json.loads((ROOT / "site" / "dashboard-data.json").read_text(encoding="utf-8"))
html = (ROOT / "site" / "index.html").read_text(encoding="utf-8")

inline_json = json.dumps(data, ensure_ascii=False, separators=(",", ":"))

old = (
    "fetch('./dashboard-data.json')\n"
    "      .then(r => { if (!r.ok) throw new Error(r.statusText); return r.json(); })\n"
    "      .then(initDashboard)\n"
    "      .catch(() => {\n"
    "        document.getElementById('loading').textContent = 'Failed to load dashboard data. Please refresh the page.';\n"
    "      });"
)
new = f"Promise.resolve({inline_json})\n    .then(initDashboard);"

if old not in html:
    print("ERROR: fetch pattern not found in index.html", file=sys.stderr)
    sys.exit(1)

result = html.replace(old, new, 1)
out = ROOT / "site" / "index-offline-test.html"
out.write_text(result, encoding="utf-8")
print(f"Written {out} ({len(result):,} bytes)")
