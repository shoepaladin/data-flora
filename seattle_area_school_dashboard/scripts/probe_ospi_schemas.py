"""Probe new OSPI datasets to discover column names and sample values.

Run via:  python scripts/probe_ospi_schemas.py
Or via the probe-schemas GitHub Actions workflow (workflow_dispatch).

Prints, for each candidate dataset:
  - The resource URL
  - All column names in the response
  - 2 sample rows (district/school/year + the value columns)
"""

from __future__ import annotations

import csv
import io
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# ---------------------------------------------------------------------------
# Candidate datasets to probe
# ---------------------------------------------------------------------------

# User-provided 2024-25 resource IDs
_PROBE_TARGETS = [
    ("Discipline 2024-25",            "https://data.wa.gov/resource/c9tq-ntbq.csv"),
    ("Languages 2024-25",             "https://data.wa.gov/resource/g4qj-yi5j.csv"),
]

# Socrata catalog search — find chronic absenteeism and EL datasets automatically
_CATALOG_SEARCHES = [
    ("chronic absenteeism report card education", "chronic_absenteeism"),
    ("english learner report card education",     "english_learner"),
]

_SOCRATA_SAMPLE = "?$limit=5"
_CATALOG_URL    = "https://data.wa.gov/api/catalog/v1?q={q}&limit=15"

# Filter used by all existing OSPI report-card fetches
_SCHOOL_FILTER = "organizationlevel='School' AND studentgrouptype='All'"


def _fetch(url: str) -> list[dict[str, str]]:
    with urllib.request.urlopen(url, timeout=30) as r:
        return list(csv.DictReader(io.StringIO(r.read().decode("utf-8"))))


def _catalog_search(query: str) -> list[dict]:
    url = _CATALOG_URL.format(q=urllib.parse.quote(query))
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())["results"]


def probe_target(label: str, base_url: str) -> None:
    print(f"\n{'='*60}")
    print(f"DATASET: {label}")
    print(f"URL:     {base_url}")

    where = "&$where=" + urllib.parse.quote(_SCHOOL_FILTER)
    sample_url = base_url + _SOCRATA_SAMPLE + where
    try:
        rows = _fetch(sample_url)
    except Exception as exc:
        print(f"  ERROR fetching with school filter: {exc}")
        # Try without filter
        try:
            rows = _fetch(base_url + _SOCRATA_SAMPLE)
        except Exception as exc2:
            print(f"  ERROR fetching without filter: {exc2}")
            return

    if not rows:
        print("  (no rows returned)")
        return

    print(f"\nCOLUMNS ({len(rows[0])} total):")
    for col in sorted(rows[0].keys()):
        print(f"  {col}")

    print(f"\nSAMPLE ROWS ({min(2, len(rows))}):")
    for row in rows[:2]:
        # Print key identification + value columns only
        interesting = {k: v for k, v in row.items()
                       if any(t in k.lower() for t in
                              ("district", "school", "year", "percent", "rate", "count",
                               "label", "value", "language", "absent", "suspend",
                               "expul", "english", "student", "subject", "datalabel"))}
        for k, v in interesting.items():
            print(f"    {k}: {v!r}")
        print()


def probe_catalog(query: str, tag: str) -> None:
    print(f"\n{'='*60}")
    print(f"CATALOG SEARCH: {query!r}")
    try:
        results = _catalog_search(query)
    except Exception as exc:
        print(f"  ERROR: {exc}")
        return

    edu_results = [r for r in results
                   if "education" in [c.lower() for c in r.get("classification", {}).get("categories", [])]]
    if not edu_results:
        edu_results = results[:5]

    for r in edu_results[:5]:
        meta = r.get("resource", {})
        rid  = meta.get("id", "?")
        name = meta.get("name", "?")
        upd  = meta.get("updatedAt", "?")[:10]
        print(f"  [{upd}] {name}")
        print(f"         resource id: {rid}")
        print(f"         url: https://data.wa.gov/resource/{rid}.csv")

        # Probe this dataset
        probe_target(f"  {tag} / {name}", f"https://data.wa.gov/resource/{rid}.csv")


def main() -> None:
    print("OSPI Schema Probe")
    print("=" * 60)

    for label, url in _PROBE_TARGETS:
        probe_target(label, url)

    for query, tag in _CATALOG_SEARCHES:
        probe_catalog(query, tag)

    print("\n" + "=" * 60)
    print("Probe complete.")


if __name__ == "__main__":
    main()
