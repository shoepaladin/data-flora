"""Patch site/dashboard-data.json with fresh OSPI metrics and regenerate index.html.

Skips the slow NCES download — reads the existing dashboard-data.json for NCES school
data, fetches only OSPI assessment/graduation CSVs, merges them in, and rewrites both
site/dashboard-data.json and site/index.html.

Usage:
    python scripts/update_ospi_only.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from seattle_schools_dashboard.build import HTML_TEMPLATE
from seattle_schools_dashboard.nces import METRIC_DEFINITIONS
from seattle_schools_dashboard.ospi import fetch_ospi_metrics


def main() -> None:
    data_path = ROOT / "site" / "dashboard-data.json"
    if not data_path.exists():
        print("ERROR: site/dashboard-data.json not found. Run a full build first.", file=sys.stderr)
        sys.exit(1)

    print("Loading existing dashboard-data.json ...", file=sys.stderr)
    payload = json.loads(data_path.read_text(encoding="utf-8"))

    print("Fetching OSPI metrics ...", file=sys.stderr)
    ospi_metrics = fetch_ospi_metrics(payload["schools"], project_root=ROOT)

    print("Merging OSPI metrics into records ...", file=sys.stderr)
    for record in payload["records"]:
        match = ospi_metrics.get((record["school_id"], record["year"]), {})
        record["ela_proficiency_rate"] = match.get("ela_proficiency_rate")
        record["math_proficiency_rate"] = match.get("math_proficiency_rate")
        record["four_year_grad_rate"] = match.get("four_year_grad_rate")
        record["ela_growth_percentile"] = match.get("ela_growth_percentile")
        record["math_growth_percentile"] = match.get("math_growth_percentile")

    payload["metrics"] = METRIC_DEFINITIONS

    site_dir = ROOT / "site"
    site_dir.mkdir(exist_ok=True)

    data_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("Written site/dashboard-data.json", file=sys.stderr)

    (site_dir / "index.html").write_text(
        HTML_TEMPLATE.replace("__DASHBOARD_DATA__", json.dumps(payload)),
        encoding="utf-8",
    )
    print("Written site/index.html", file=sys.stderr)
    print("Done.", file=sys.stderr)


if __name__ == "__main__":
    main()
