from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seattle_schools_dashboard.ospi import (
    _norm_name,
    _parse_pct_string,
    _parse_sgp,
    _proficiency_value,
    _expand_year,
    _build_name_index,
    _lookup_school_id,
    fetch_ospi_metrics,
)


class ParseSgpTests(unittest.TestCase):
    def test_integer_value(self):
        self.assertEqual(_parse_sgp("62"), 62)

    def test_float_rounds(self):
        self.assertEqual(_parse_sgp("45.5"), 46)

    def test_empty_returns_none(self):
        self.assertIsNone(_parse_sgp(""))

    def test_null_string_returns_none(self):
        self.assertIsNone(_parse_sgp("NULL"))

    def test_star_returns_none(self):
        self.assertIsNone(_parse_sgp("*"))

    def test_datreason_suppresses(self):
        self.assertIsNone(_parse_sgp("55", datreason="N<10"))

    def test_null_datreason_allowed(self):
        self.assertEqual(_parse_sgp("55", datreason="NULL"), 55)

    def test_empty_datreason_allowed(self):
        self.assertEqual(_parse_sgp("55", datreason=""), 55)


class ExpandYearTests(unittest.TestCase):
    def test_short_year_expands(self):
        self.assertEqual(_expand_year("2023-24"), "2023-2024")

    def test_century_boundary(self):
        self.assertEqual(_expand_year("1999-00"), "1999-2000")

    def test_already_full_year_unchanged(self):
        self.assertEqual(_expand_year("2023-2024"), "2023-2024")

    def test_empty_unchanged(self):
        self.assertEqual(_expand_year(""), "")


class NormNameTests(unittest.TestCase):
    def test_lowercases(self):
        self.assertEqual(_norm_name("Lincoln High School"), "lincoln high school")

    def test_strips_punctuation(self):
        self.assertEqual(_norm_name("St. Mary's"), "st mary s")

    def test_collapses_whitespace(self):
        self.assertEqual(_norm_name("  Maple   Elementary  "), "maple elementary")

    def test_removes_hyphens(self):
        self.assertEqual(_norm_name("K-8 School"), "k 8 school")


class ParsePctStringTests(unittest.TestCase):
    def test_star_suppressed(self):
        self.assertIsNone(_parse_pct_string("*"))

    def test_empty_suppressed(self):
        self.assertIsNone(_parse_pct_string(""))

    def test_none_suppressed(self):
        self.assertIsNone(_parse_pct_string(None))

    def test_null_string_suppressed(self):
        self.assertIsNone(_parse_pct_string("NULL"))

    def test_n_less_than_10_suppressed(self):
        self.assertIsNone(_parse_pct_string("Suppressed: N<10"))

    def test_less_than_percent_suppressed(self):
        self.assertIsNone(_parse_pct_string("<10%"))

    def test_percent_string_normalises(self):
        self.assertAlmostEqual(_parse_pct_string("73.5%"), 0.735)

    def test_percent_string_with_spaces(self):
        self.assertAlmostEqual(_parse_pct_string("  35.10%  "), 0.3510)

    def test_already_decimal(self):
        self.assertAlmostEqual(_parse_pct_string("0.854"), 0.854)

    def test_zero_percent(self):
        self.assertAlmostEqual(_parse_pct_string("0%"), 0.0)

    def test_100_percent(self):
        self.assertAlmostEqual(_parse_pct_string("100%"), 1.0)


class SchemaVersionDetectionTests(unittest.TestCase):
    def test_old_schema_uses_percentmetstandard(self):
        row = {"percentmetstandard": "45.0%"}
        self.assertAlmostEqual(_proficiency_value(row), 0.45)

    def test_new_schema_uses_percent_consistent(self):
        row = {"percent_consistent_grade_level_knowledge_and_above": "62.3%"}
        self.assertAlmostEqual(_proficiency_value(row), 0.623)

    def test_new_schema_takes_precedence(self):
        row = {
            "percent_consistent_grade_level_knowledge_and_above": "62.3%",
            "percentmetstandard": "45.0%",
        }
        self.assertAlmostEqual(_proficiency_value(row), 0.623)

    def test_2024_25_schema_uses_percent_consistent_grade(self):
        row = {"percent_consistent_grade": "58.7%"}
        self.assertAlmostEqual(_proficiency_value(row), 0.587)

    def test_new_schema_takes_precedence_over_2024_25(self):
        row = {
            "percent_consistent_grade_level_knowledge_and_above": "62.3%",
            "percent_consistent_grade": "58.7%",
        }
        self.assertAlmostEqual(_proficiency_value(row), 0.623)

    def test_suppressed_old_schema(self):
        row = {"percentmetstandard": "*"}
        self.assertIsNone(_proficiency_value(row))

    def test_empty_string_column_falls_through_to_2024_25(self):
        # Column exists in schema but is empty (Socrata backward-compat export).
        # Must fall through to percent_consistent_grade, not return None.
        row = {
            "percent_consistent_grade_level_knowledge_and_above": "",
            "percent_consistent_grade": "58.7%",
        }
        self.assertAlmostEqual(_proficiency_value(row), 0.587)

    def test_empty_string_column_falls_through_to_old_schema(self):
        row = {
            "percent_consistent_grade_level_knowledge_and_above": "",
            "percent_consistent_grade": "",
            "percentmetstandard": "45.0%",
        }
        self.assertAlmostEqual(_proficiency_value(row), 0.45)


class JoinTests(unittest.TestCase):
    def _make_schools(self):
        return [
            {"id": "s1", "name": "Lincoln High School", "district_name": "Seattle"},
            {"id": "s2", "name": "Maple Elementary", "district_name": "Bellevue"},
            # 5-token name; OSPI may add "of" making it 6 tokens → 5/6 ≈ 0.833 ≥ 0.80
            {"id": "s3", "name": "Maple Valley Middle School Arts", "district_name": "Bellevue"},
        ]

    def test_primary_exact_match(self):
        schools = self._make_schools()
        exact, by_district = _build_name_index(schools)
        sid = _lookup_school_id("Seattle", "Lincoln High School", exact, by_district)
        self.assertEqual(sid, "s1")

    def test_primary_case_insensitive(self):
        schools = self._make_schools()
        exact, by_district = _build_name_index(schools)
        sid = _lookup_school_id("seattle", "lincoln high school", exact, by_district)
        self.assertEqual(sid, "s1")

    def test_fallback_token_overlap(self):
        schools = self._make_schools()
        exact, by_district = _build_name_index(schools)
        # OSPI adds "of" and "middle school" stop words differ from NCES name.
        # After stop-word removal both sides share {"maple", "valley", "arts"} → 3/3 = 1.0 → match
        sid = _lookup_school_id(
            "Bellevue", "Maple Valley Middle School of Arts", exact, by_district
        )
        self.assertEqual(sid, "s3")

    def test_no_match_returns_none(self):
        schools = self._make_schools()
        exact, by_district = _build_name_index(schools)
        sid = _lookup_school_id("Bellevue", "Completely Different Academy", exact, by_district)
        self.assertIsNone(sid)

    def test_wrong_district_no_match(self):
        schools = self._make_schools()
        exact, by_district = _build_name_index(schools)
        sid = _lookup_school_id("Renton", "Lincoln High School", exact, by_district)
        self.assertIsNone(sid)

    def test_low_overlap_not_matched(self):
        schools = self._make_schools()
        exact, by_district = _build_name_index(schools)
        # "Maple Oak" shares only 1/2 content tokens with "Maple Valley Middle School Arts"
        # (content tokens: {"maple", "valley", "arts"}) → 1/max(2,3) ≈ 0.33, below threshold
        sid = _lookup_school_id("Bellevue", "Maple Oak School", exact, by_district)
        self.assertIsNone(sid)


class FetchOspiMetricsUnitTests(unittest.TestCase):
    """Tests for fetch_ospi_metrics using monkeypatching to avoid network calls."""

    def _make_schools(self):
        return [
            {"id": "s1", "name": "Roosevelt High School", "district_name": "Seattle"},
        ]

    def test_assessment_ela_and_math_merged(self):
        from seattle_schools_dashboard import ospi as ospi_module

        fake_assessment_rows = [
            {
                "organizationlevel": "School",
                "studentgrouptype": "All",
                "gradelevel": "All Grades",
                "districtname": "Seattle",
                "schoolname": "Roosevelt High School",
                "schoolyear": "2023-2024",
                "testsubject": "ELA",
                "percent_consistent_grade_level_knowledge_and_above": "71.0%",
                "percentmetstandard": "",
            },
            {
                "organizationlevel": "School",
                "studentgrouptype": "All",
                "gradelevel": "All Grades",
                "districtname": "Seattle",
                "schoolname": "Roosevelt High School",
                "schoolyear": "2023-2024",
                "testsubject": "Math",
                "percent_consistent_grade_level_knowledge_and_above": "55.2%",
                "percentmetstandard": "",
            },
        ]

        original_assessment = ospi_module.ASSESSMENT_DATASETS
        original_graduation = ospi_module.GRADUATION_DATASETS
        original_sgp = ospi_module.SGP_DATASETS
        original_fetch = ospi_module._fetch_csv

        ospi_module.ASSESSMENT_DATASETS = [("2023-24", "https://fake-assessment.example")]
        ospi_module.GRADUATION_DATASETS = []
        ospi_module.SGP_DATASETS = []
        ospi_module._fetch_csv = lambda url, where="": fake_assessment_rows

        try:
            result = ospi_module.fetch_ospi_metrics(self._make_schools())
        finally:
            ospi_module.ASSESSMENT_DATASETS = original_assessment
            ospi_module.GRADUATION_DATASETS = original_graduation
            ospi_module.SGP_DATASETS = original_sgp
            ospi_module._fetch_csv = original_fetch

        key = ("s1", "2023-2024")
        self.assertIn(key, result)
        self.assertAlmostEqual(result[key]["ela_proficiency_rate"], 0.71)
        self.assertAlmostEqual(result[key]["math_proficiency_rate"], 0.552)

    def test_unmatched_school_not_in_result(self):
        from seattle_schools_dashboard import ospi as ospi_module

        fake_rows = [
            {
                "organizationlevel": "School",
                "studentgrouptype": "All",
                "gradelevel": "All Grades",
                "districtname": "Seattle",
                "schoolname": "Nonexistent Academy XYZ",
                "schoolyear": "2023-2024",
                "testsubject": "ELA",
                "percent_consistent_grade_level_knowledge_and_above": "60%",
            },
        ]

        original_assessment = ospi_module.ASSESSMENT_DATASETS
        original_graduation = ospi_module.GRADUATION_DATASETS
        original_sgp = ospi_module.SGP_DATASETS
        original_fetch = ospi_module._fetch_csv

        ospi_module.ASSESSMENT_DATASETS = [("2023-24", "https://fake.example")]
        ospi_module.GRADUATION_DATASETS = []
        ospi_module.SGP_DATASETS = []
        ospi_module._fetch_csv = lambda url, where="": fake_rows

        try:
            result = ospi_module.fetch_ospi_metrics(self._make_schools())
        finally:
            ospi_module.ASSESSMENT_DATASETS = original_assessment
            ospi_module.GRADUATION_DATASETS = original_graduation
            ospi_module.SGP_DATASETS = original_sgp
            ospi_module._fetch_csv = original_fetch

        self.assertEqual(result, {})

    def test_graduation_rate_merged(self):
        from seattle_schools_dashboard import ospi as ospi_module

        fake_grad_rows = [
            {
                "organizationlevel": "School",
                "studentgrouptype": "All",
                "cohort": "Four Year",
                "districtname": "Seattle",
                "schoolname": "Roosevelt High School",
                "schoolyear": "2023-2024",
                "graduationrate": "0.913",
            },
        ]

        original_assessment = ospi_module.ASSESSMENT_DATASETS
        original_graduation = ospi_module.GRADUATION_DATASETS
        original_sgp = ospi_module.SGP_DATASETS
        original_fetch = ospi_module._fetch_csv

        ospi_module.ASSESSMENT_DATASETS = []
        ospi_module.GRADUATION_DATASETS = [("2023-24", "https://fake-grad.example")]
        ospi_module.SGP_DATASETS = []
        ospi_module._fetch_csv = lambda url, where="": fake_grad_rows

        try:
            result = ospi_module.fetch_ospi_metrics(self._make_schools())
        finally:
            ospi_module.ASSESSMENT_DATASETS = original_assessment
            ospi_module.GRADUATION_DATASETS = original_graduation
            ospi_module.SGP_DATASETS = original_sgp
            ospi_module._fetch_csv = original_fetch

        key = ("s1", "2023-2024")
        self.assertIn(key, result)
        self.assertAlmostEqual(result[key]["four_year_grad_rate"], 0.913)

    def test_sgp_ela_and_math_merged(self):
        from seattle_schools_dashboard import ospi as ospi_module

        fake_sgp_rows = [
            {
                "organizationlevel": "School",
                "studentgrouptype": "AllStudents",
                "gradelevel": "All Grades",
                "districtname": "Seattle",
                "schoolname": "Roosevelt High School",
                "schoolyear": "2023-2024",
                "subject": "English Language Arts",
                "mediansgp": "62",
                "datreason": "NULL",
            },
            {
                "organizationlevel": "School",
                "studentgrouptype": "AllStudents",
                "gradelevel": "All Grades",
                "districtname": "Seattle",
                "schoolname": "Roosevelt High School",
                "schoolyear": "2023-2024",
                "subject": "Math",
                "mediansgp": "57.5",
                "datreason": "NULL",
            },
        ]

        original_assessment = ospi_module.ASSESSMENT_DATASETS
        original_graduation = ospi_module.GRADUATION_DATASETS
        original_sgp = ospi_module.SGP_DATASETS
        original_fetch = ospi_module._fetch_csv

        ospi_module.ASSESSMENT_DATASETS = []
        ospi_module.GRADUATION_DATASETS = []
        ospi_module.SGP_DATASETS = [("2023-24", "https://fake-sgp.example")]
        ospi_module._fetch_csv = lambda url, where="": fake_sgp_rows

        try:
            result = ospi_module.fetch_ospi_metrics(self._make_schools())
        finally:
            ospi_module.ASSESSMENT_DATASETS = original_assessment
            ospi_module.GRADUATION_DATASETS = original_graduation
            ospi_module.SGP_DATASETS = original_sgp
            ospi_module._fetch_csv = original_fetch

        key = ("s1", "2023-2024")
        self.assertIn(key, result)
        self.assertEqual(result[key]["ela_growth_percentile"], 62)
        self.assertEqual(result[key]["math_growth_percentile"], 58)  # rounds 57.5

    def test_sgp_suppressed_datreason(self):
        from seattle_schools_dashboard import ospi as ospi_module

        fake_sgp_rows = [
            {
                "organizationlevel": "School",
                "studentgrouptype": "AllStudents",
                "gradelevel": "All Grades",
                "districtname": "Seattle",
                "schoolname": "Roosevelt High School",
                "schoolyear": "2023-2024",
                "subject": "Math",
                "mediansgp": "55",
                "datreason": "N<10",
            },
        ]

        original_assessment = ospi_module.ASSESSMENT_DATASETS
        original_graduation = ospi_module.GRADUATION_DATASETS
        original_sgp = ospi_module.SGP_DATASETS
        original_fetch = ospi_module._fetch_csv

        ospi_module.ASSESSMENT_DATASETS = []
        ospi_module.GRADUATION_DATASETS = []
        ospi_module.SGP_DATASETS = [("2023-24", "https://fake-sgp.example")]
        ospi_module._fetch_csv = lambda url, where="": fake_sgp_rows

        try:
            result = ospi_module.fetch_ospi_metrics(self._make_schools())
        finally:
            ospi_module.ASSESSMENT_DATASETS = original_assessment
            ospi_module.GRADUATION_DATASETS = original_graduation
            ospi_module.SGP_DATASETS = original_sgp
            ospi_module._fetch_csv = original_fetch

        key = ("s1", "2023-2024")
        self.assertIn(key, result)
        self.assertIsNone(result[key].get("math_growth_percentile"))


if __name__ == "__main__":
    unittest.main()
