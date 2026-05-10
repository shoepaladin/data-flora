"""Generate a CSV showing how OSPI school names map to NCES school names.

Usage:
    python scripts/inspect_ospi_matches.py > ospi_match_review.csv

Reads NCES schools from site/dashboard-data.json (must exist).
Reads OSPI school names live from data.wa.gov (just the most recent assessment year).

Output columns:
    ospi_district, ospi_school, match_type, match_score, nces_school_id, nces_school_name

match_type: exact | fallback | unmatched
match_score: 1.0 for exact, token-overlap score for fallback, 0 for unmatched

To supply manual overrides, create data/ospi_overrides.csv with columns:
    ospi_district,ospi_school,nces_school_id
One row per override. The script will mark those rows as match_type=override.
"""

from __future__ import annotations

import csv
import io
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from seattle_schools_dashboard.config import TARGET_DISTRICT_NAME_MAP
from seattle_schools_dashboard.ospi import (
    _STOP_WORDS,
    _build_name_index,
    _norm_name,
)

SAMPLE_URL = "https://data.wa.gov/resource/x73g-mrqp.csv?$limit=5000000"
OVERRIDES_FILE = ROOT / "data" / "ospi_overrides.csv"

_TARGET_DISTRICTS = set(TARGET_DISTRICT_NAME_MAP.values())


def _norm_district(raw: str) -> str | None:
    return TARGET_DISTRICT_NAME_MAP.get(raw) or (raw if raw in _TARGET_DISTRICTS else None)


def _token_score(name_a: str, name_b: str) -> float:
    ta = frozenset(t for t in name_a.split() if t not in _STOP_WORDS)
    tb = frozenset(t for t in name_b.split() if t not in _STOP_WORDS)
    denom = max(len(ta), len(tb))
    return len(ta & tb) / denom if denom else 0.0


def load_nces_schools() -> list[dict]:
    data_path = ROOT / "site" / "dashboard-data.json"
    payload = json.loads(data_path.read_text(encoding="utf-8"))
    return payload["schools"]


def load_overrides() -> dict[tuple[str, str], str]:
    """Return {(norm_district, norm_school): nces_school_id}."""
    if not OVERRIDES_FILE.exists():
        return {}
    with OVERRIDES_FILE.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {
            (_norm_name(row["ospi_district"]), _norm_name(row["ospi_school"])): row["nces_school_id"]
            for row in reader
        }


def fetch_ospi_school_names() -> list[tuple[str, str]]:
    """Return sorted unique (canonical_district, ospi_school_name) pairs."""
    print("Fetching OSPI assessment data...", file=sys.stderr)
    with urllib.request.urlopen(SAMPLE_URL, timeout=120) as resp:
        data = resp.read().decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(data)))
    seen: set[tuple[str, str]] = set()
    for row in rows:
        if row.get("organizationlevel") != "School":
            continue
        if row.get("studentgrouptype") != "All":
            continue
        if row.get("gradelevel") != "All Grades":
            continue
        canonical = _norm_district(row.get("districtname", ""))
        if not canonical:
            continue
        seen.add((canonical, row["schoolname"]))
    return sorted(seen)


def main() -> None:
    schools = load_nces_schools()
    overrides = load_overrides()
    exact, by_district = _build_name_index(schools)
    nces_by_id = {s["id"]: s["name"] for s in schools}

    ospi_pairs = fetch_ospi_school_names()

    writer = csv.writer(sys.stdout)
    writer.writerow([
        "ospi_district", "ospi_school",
        "match_type", "match_score",
        "nces_school_id", "nces_school_name",
    ])

    for district, school_name in ospi_pairs:
        nd = _norm_name(district)
        ns = _norm_name(school_name)

        # Check override first
        override_id = overrides.get((nd, ns))
        if override_id:
            nces_name = nces_by_id.get(override_id, "")
            writer.writerow([district, school_name, "override", 1.0, override_id, nces_name])
            continue

        # Primary exact join
        sid = exact.get((nd, ns))
        if sid:
            writer.writerow([district, school_name, "exact", 1.0, sid, nces_by_id.get(sid, "")])
            continue

        # Fallback token overlap
        candidates = by_district.get(nd, [])
        best_score = 0.0
        best_sid = None
        for cand_sid, cand_ns, cand_tokens in candidates:
            score = _token_score(ns, cand_ns)
            if score > best_score:
                best_score = score
                best_sid = cand_sid

        if best_sid and best_score >= 0.80:
            writer.writerow([
                district, school_name, "fallback", round(best_score, 3),
                best_sid, nces_by_id.get(best_sid, ""),
            ])
        else:
            # Show the best candidate even if below threshold, for review
            best_name = nces_by_id.get(best_sid, "") if best_sid else ""
            writer.writerow([
                district, school_name, "unmatched", round(best_score, 3),
                best_sid or "", best_name,
            ])


if __name__ == "__main__":
    main()
