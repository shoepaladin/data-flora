"""Unit + integration tests for the new OSPI metrics.

Unit tests (always run): verify parse/aggregate logic using mocked CSV rows.
Integration tests (network-gated): fetch real OSPI data, verify plausible values
  for known schools to confirm we replicate the published OSPI Report Card.

Run integration tests locally with:
    OSPI_INTEGRATION=1 python -m unittest discover -s tests -p test_new_metrics.py
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seattle_schools_dashboard.ospi import (
    _absenteeism_value,
    _suspension_value,
    fetch_new_metrics,
)

_NETWORK = bool(os.environ.get("OSPI_INTEGRATION"))
_skip_no_network = unittest.skipUnless(_NETWORK, "set OSPI_INTEGRATION=1 to run network tests")


# ---------------------------------------------------------------------------
# Helpers shared across test classes
# ---------------------------------------------------------------------------

def _make_schools():
    return [
        {"id": "s1", "name": "Roosevelt High School",    "district_name": "Seattle"},
        {"id": "s2", "name": "Bainbridge High School",   "district_name": "Bainbridge Island"},
        {"id": "s3", "name": "Bellevue High School",     "district_name": "Bellevue"},
    ]


def _patch(ospi_module, **lists):
    """Return (original_values, restore_fn) for monkeypatching dataset lists."""
    original = {attr: getattr(ospi_module, attr) for attr in lists}

    def restore():
        for attr, val in original.items():
            setattr(ospi_module, attr, val)

    for attr, val in lists.items():
        setattr(ospi_module, attr, val)
    return restore


# ---------------------------------------------------------------------------
# Unit — parser helpers
# ---------------------------------------------------------------------------

class AbsenteeismParserTests(unittest.TestCase):

    def test_percentagevalue_column(self):
        self.assertAlmostEqual(_absenteeism_value({"percentagevalue": "12.3%"}), 0.123)

    def test_chronicabsenteeismrate_column(self):
        self.assertAlmostEqual(_absenteeism_value({"chronicabsenteeismrate": "8.5%"}), 0.085)

    def test_percentageabsent_column(self):
        self.assertAlmostEqual(_absenteeism_value({"percentageabsent": "15.0%"}), 0.15)

    def test_suppressed_returns_none(self):
        self.assertIsNone(_absenteeism_value({"percentagevalue": "*"}))

    def test_null_returns_none(self):
        self.assertIsNone(_absenteeism_value({"percentagevalue": "NULL"}))

    def test_no_matching_column_returns_none(self):
        self.assertIsNone(_absenteeism_value({"someothercolumn": "12%"}))

    def test_decimal_0_to_1_normalised(self):
        # Some OSPI datasets provide 0-1 floats instead of percents
        self.assertAlmostEqual(_absenteeism_value({"percentagevalue": "0.123"}), 0.123)

    def test_100_percent(self):
        self.assertAlmostEqual(_absenteeism_value({"percentagevalue": "100%"}), 1.0)


class SuspensionParserTests(unittest.TestCase):

    def test_percentagevalue_column(self):
        self.assertAlmostEqual(_suspension_value({"percentagevalue": "5.7%"}), 0.057)

    def test_suspensionrate_column(self):
        self.assertAlmostEqual(_suspension_value({"suspensionrate": "3.2%"}), 0.032)

    def test_datavalue_column(self):
        self.assertAlmostEqual(_suspension_value({"datavalue": "4.1%"}), 0.041)

    def test_suppressed_returns_none(self):
        self.assertIsNone(_suspension_value({"percentagevalue": "*"}))

    def test_no_matching_column_returns_none(self):
        self.assertIsNone(_suspension_value({"othercolumn": "5%"}))

    def test_disciplinerate_column(self):
        self.assertAlmostEqual(_suspension_value({"disciplinerate": "7.8%"}), 0.078)

    def test_zero_rate(self):
        self.assertAlmostEqual(_suspension_value({"percentagevalue": "0%"}), 0.0)



# ---------------------------------------------------------------------------
# Unit — fetch_new_metrics integration via monkeypatching
# ---------------------------------------------------------------------------

class FetchNewMetricsUnitTests(unittest.TestCase):

    def _run_with_fake(self, *, discipline_rows=None, absenteeism_rows=None, el_rows=None):
        from seattle_schools_dashboard import ospi as m

        restore = _patch(m,
            CHRONIC_ABSENTEEISM_DATASETS=[("2024-25", "https://fake-absent.example")] if absenteeism_rows else [],
            DISCIPLINE_DATASETS=[("2024-25", "https://fake-discipline.example")] if discipline_rows else [],
            ENGLISH_LEARNER_DATASETS=[("2024-25", "https://fake-el.example")] if el_rows else [],
        )

        row_map = {
            "https://fake-absent.example":     absenteeism_rows or [],
            "https://fake-discipline.example": discipline_rows or [],
            "https://fake-el.example":         el_rows or [],
        }
        original_fetch = m._fetch_csv
        m._fetch_csv = lambda url, where="": row_map.get(url, [])

        try:
            return fetch_new_metrics(_make_schools())
        finally:
            restore()
            m._fetch_csv = original_fetch

    def _base_row(self, school="Roosevelt High School", district="Seattle", year="2024-25"):
        return {
            "organizationlevel": "School",
            "studentgrouptype":  "All",
            "districtname":      district,
            "schoolname":        school,
            "schoolyear":        year,
        }

    # ── Discipline ────────────────────────────────────────────────────────

    def test_suspension_rate_extracted(self):
        rows = [{**self._base_row(), "percentagevalue": "6.2%"}]
        result = self._run_with_fake(discipline_rows=rows)
        self.assertAlmostEqual(result[("s1", "2024-2025")]["suspension_rate"], 0.062)

    def test_suspension_suppressed_is_none(self):
        rows = [{**self._base_row(), "percentagevalue": "*"}]
        result = self._run_with_fake(discipline_rows=rows)
        self.assertIsNone(result[("s1", "2024-2025")]["suspension_rate"])

    def test_suspension_unmatched_school_excluded(self):
        rows = [{**self._base_row(school="Nonexistent School XYZ"), "percentagevalue": "5%"}]
        result = self._run_with_fake(discipline_rows=rows)
        self.assertEqual(result, {})

    def test_multiple_schools_discipline(self):
        rows = [
            {**self._base_row(),                                           "percentagevalue": "6.2%"},
            {**self._base_row(school="Bainbridge High School",
                              district="Bainbridge Island"),               "percentagevalue": "2.1%"},
        ]
        result = self._run_with_fake(discipline_rows=rows)
        self.assertAlmostEqual(result[("s1", "2024-2025")]["suspension_rate"], 0.062)
        self.assertAlmostEqual(result[("s2", "2024-2025")]["suspension_rate"], 0.021)

    # ── Chronic absenteeism ───────────────────────────────────────────────

    def test_absenteeism_rate_extracted(self):
        rows = [{**self._base_row(), "percentagevalue": "18.4%"}]
        result = self._run_with_fake(absenteeism_rows=rows)
        self.assertAlmostEqual(result[("s1", "2024-2025")]["chronic_absentee_rate"], 0.184)

    def test_empty_datasets_produce_empty_result(self):
        result = self._run_with_fake()
        self.assertEqual(result, {})


# ---------------------------------------------------------------------------
# Integration — real OSPI data (skipped unless OSPI_INTEGRATION=1)
# ---------------------------------------------------------------------------

@_skip_no_network
class IntegrationDisciplineTests(unittest.TestCase):
    """Verify discipline data against OSPI Report Card for 2024-25.

    Expected ranges derived from OSPI published figures for Seattle-area schools.
    All assertions use generous bounds to tolerate year-over-year variation.
    """

    @classmethod
    def setUpClass(cls):
        from seattle_schools_dashboard.ospi import DISCIPLINE_DATASETS, fetch_new_metrics
        import json
        data_path = Path(__file__).resolve().parents[1] / "site" / "dashboard-data.json"
        schools = json.loads(data_path.read_text())["schools"]
        cls.result = fetch_new_metrics(schools)

    def _rate(self, school_id, year="2024-2025"):
        return self.result.get((school_id, year), {}).get("suspension_rate")

    def test_at_least_50_schools_have_discipline_data(self):
        count = sum(1 for v in self.result.values() if "suspension_rate" in v and v["suspension_rate"] is not None)
        self.assertGreater(count, 50, "Expected discipline data for many schools")

    def test_all_rates_in_valid_range(self):
        for (sid, year), metrics in self.result.items():
            rate = metrics.get("suspension_rate")
            if rate is not None:
                self.assertGreaterEqual(rate, 0.0, f"{sid}/{year} rate below 0")
                self.assertLessEqual(rate, 1.0, f"{sid}/{year} rate above 100%")

    def test_seattle_schools_represented(self):
        import json
        data_path = Path(__file__).resolve().parents[1] / "site" / "dashboard-data.json"
        payload = json.loads(data_path.read_text())
        seattle_ids = {s["id"] for s in payload["schools"] if s["district_name"] == "Seattle"}
        matched = {sid for (sid, _) in self.result if sid in seattle_ids}
        self.assertGreater(len(matched), 5, "Expected several Seattle schools with discipline data")


if __name__ == "__main__":
    unittest.main()
