"""Refresh OSPI new metrics into an existing site/dashboard-data.json.

Loads the committed NCES payload (schools + historical records), fetches
only the three new OSPI metric datasets (chronic absenteeism, suspension
rate, EL share), merges the results into the records, and writes the
updated file back to site/dashboard-data.json.

Run directly:
    python scripts/refresh_ospi_metrics.py

Or via CI on every push (continue-on-error so a network hiccup never
blocks Pages deployment).
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from seattle_schools_dashboard.nces import METRIC_DEFINITIONS  # noqa: E402
from seattle_schools_dashboard.ospi import fetch_new_metrics  # noqa: E402

data_path = ROOT / "site" / "dashboard-data.json"

payload = json.loads(data_path.read_text(encoding="utf-8"))
schools = payload["schools"]

print(f"Fetching new OSPI metrics for {len(schools)} schools …", flush=True)
new_metrics = fetch_new_metrics(schools)

non_null = sum(
    1 for v in new_metrics.values() for val in v.values() if val is not None
)
print(f"  {len(new_metrics)} school-year pairs, {non_null} non-null values")

for record in payload["records"]:
    key = (record["school_id"], record["year"])
    match = new_metrics.get(key, {})
    record["chronic_absentee_rate"] = match.get("chronic_absentee_rate")
    record["suspension_rate"] = match.get("suspension_rate")
    record["english_learner_share"] = match.get("english_learner_share")

payload["metrics"] = METRIC_DEFINITIONS

data_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
print(f"Updated {data_path}")
