from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seattle_schools_dashboard.nces import (
    DERIVED_SUBTOTAL_MINUS_ADULT,
    DERIVED_TOTAL_MINUS_ADULT,
    apply_lunch_metrics,
    apply_membership_row,
    apply_wide_membership_row,
    finalize_records,
    is_open_school,
    make_school_year_record,
    normalize_school_level,
    read_membership,
    safe_share,
)


class NcesAggregationTests(unittest.TestCase):
    def test_apply_membership_row_uses_derived_minus_adult_totals(self) -> None:
        record = {
            "school_id": "123",
            "enrollment": None,
            "frpl_count": 0,
            "race_counts": {
                "american_indian_alaska_native_share": 0,
                "asian_share": 0,
                "black_african_american_share": 0,
                "hispanic_latino_share": 0,
                "native_hawaiian_pacific_islander_share": 0,
                "two_or_more_races_share": 0,
                "white_share": 0,
                "race_not_specified_share": 0,
            },
            "sex_counts": {
                "female_share": 0,
                "male_share": 0,
                "sex_not_specified_share": 0,
            },
        }

        apply_membership_row(
            record,
            {
                "TOTAL_INDICATOR": DERIVED_TOTAL_MINUS_ADULT,
                "GRADE": "No Category Codes",
                "RACE_ETHNICITY": "No Category Codes",
                "SEX": "No Category Codes",
                "STUDENT_COUNT": "100",
            },
        )
        apply_membership_row(
            record,
            {
                "TOTAL_INDICATOR": DERIVED_SUBTOTAL_MINUS_ADULT,
                "GRADE": "No Category Codes",
                "RACE_ETHNICITY": "White",
                "SEX": "Female",
                "STUDENT_COUNT": "40",
            },
        )
        apply_membership_row(
            record,
            {
                "TOTAL_INDICATOR": DERIVED_SUBTOTAL_MINUS_ADULT,
                "GRADE": "No Category Codes",
                "RACE_ETHNICITY": "White",
                "SEX": "Male",
                "STUDENT_COUNT": "35",
            },
        )
        apply_membership_row(
            record,
            {
                "TOTAL_INDICATOR": DERIVED_SUBTOTAL_MINUS_ADULT,
                "GRADE": "No Category Codes",
                "RACE_ETHNICITY": "Black or African American",
                "SEX": "Female",
                "STUDENT_COUNT": "10",
            },
        )

        self.assertEqual(record["enrollment"], 100)
        self.assertEqual(record["race_counts"]["white_share"], 75)
        self.assertEqual(record["race_counts"]["black_african_american_share"], 10)
        self.assertEqual(record["sex_counts"]["female_share"], 50)
        self.assertEqual(record["sex_counts"]["male_share"], 35)

    def test_finalize_records_computes_shares(self) -> None:
        schools = {
            "123": {
                "id": "123",
                "name": "Sample School",
                "district_id": "seattle",
                "district_name": "Seattle",
                "school_level": "High",
            }
        }
        school_year_records = {
            "123": {
                "school_id": "123",
                "enrollment": 100,
                "frpl_count": 60,
                "race_counts": {
                    "american_indian_alaska_native_share": 0,
                    "asian_share": 10,
                    "black_african_american_share": 15,
                    "hispanic_latino_share": 25,
                    "native_hawaiian_pacific_islander_share": 0,
                    "two_or_more_races_share": 5,
                    "white_share": 40,
                    "race_not_specified_share": 5,
                },
                "sex_counts": {
                    "female_share": 48,
                    "male_share": 50,
                    "sex_not_specified_share": 2,
                },
            }
        }

        records = finalize_records("2024-2025", schools, school_year_records)

        self.assertEqual(records[0]["combined_frpl_share"], 0.6)
        self.assertEqual(records[0]["asian_share"], 0.1)
        self.assertEqual(records[0]["female_share"], 0.48)

    def test_apply_wide_membership_row_uses_member_and_aggregate_columns(self) -> None:
        record = {
            "school_id": "123",
            "enrollment": None,
            "frpl_count": 0,
            "race_counts": {
                "american_indian_alaska_native_share": 0,
                "asian_share": 0,
                "black_african_american_share": 0,
                "hispanic_latino_share": 0,
                "native_hawaiian_pacific_islander_share": 0,
                "two_or_more_races_share": 0,
                "white_share": 0,
                "race_not_specified_share": 0,
            },
            "sex_counts": {
                "female_share": 0,
                "male_share": 0,
                "sex_not_specified_share": 0,
            },
        }

        apply_wide_membership_row(
            record,
            {
                "MEMBER": "100",
                "AM": "3",
                "AS": "7",
                "BL": "10",
                "HI": "15",
                "HP": "1",
                "TR": "4",
                "WH": "58",
                "AMALM": "1",
                "ASALM": "4",
                "BLALM": "6",
                "HIALM": "7",
                "HPALM": "1",
                "TRALM": "2",
                "WHALM": "30",
                "AMALF": "2",
                "ASALF": "3",
                "BLALF": "4",
                "HIALF": "8",
                "HPALF": "0",
                "TRALF": "2",
                "WHALF": "28",
            },
        )

        self.assertEqual(record["enrollment"], 100)
        self.assertEqual(record["race_counts"]["white_share"], 58)
        self.assertEqual(record["sex_counts"]["male_share"], 51)
        self.assertEqual(record["sex_counts"]["female_share"], 47)
        self.assertEqual(record["sex_counts"]["sex_not_specified_share"], 2)

    def test_wide_standalone_sex_totals_preferred_over_race_x_sex(self) -> None:
        # TOTM=55, TOTF=45 should win over the race×sex intersection sums.
        # A student with unknown race is in TOTM but not in any WHALM/BLALM/etc.,
        # so TOTM gives the more accurate male count.
        record = make_school_year_record("123")
        apply_wide_membership_row(
            record,
            {
                "MEMBER": "100",
                "AM": "0", "AS": "0", "BL": "10", "HI": "0", "HP": "0", "TR": "0", "WH": "80",
                # Race×sex sums would give male=45, female=45 (10 unspecified-race students missing)
                "AMALM": "0", "ASALM": "0", "BLALM": "5", "HIALM": "0", "HPALM": "0", "TRALM": "0", "WHALM": "40",
                "AMALF": "0", "ASALF": "0", "BLALF": "5", "HIALF": "0", "HPALF": "0", "TRALF": "0", "WHALF": "40",
                # Standalone totals correctly account for the 10 unspecified-race students
                "TOTM": "55",
                "TOTF": "45",
            },
        )
        self.assertEqual(record["sex_counts"]["male_share"], 55)
        self.assertEqual(record["sex_counts"]["female_share"], 45)
        self.assertEqual(record["sex_counts"]["sex_not_specified_share"], 0)

    def test_wide_sex_falls_back_to_race_x_sex_when_no_standalone(self) -> None:
        # Without TOTM/TOTF, the race×sex intersection sums are used and the 10
        # students with unknown race inflate sex_not_specified_share.
        record = make_school_year_record("123")
        apply_wide_membership_row(
            record,
            {
                "MEMBER": "100",
                "AM": "0", "AS": "0", "BL": "10", "HI": "0", "HP": "0", "TR": "0", "WH": "80",
                "AMALM": "0", "ASALM": "0", "BLALM": "5", "HIALM": "0", "HPALM": "0", "TRALM": "0", "WHALM": "40",
                "AMALF": "0", "ASALF": "0", "BLALF": "5", "HIALF": "0", "HPALF": "0", "TRALF": "0", "WHALF": "40",
                # No TOTM / TOTF
            },
        )
        self.assertEqual(record["sex_counts"]["male_share"], 45)
        self.assertEqual(record["sex_counts"]["female_share"], 45)
        self.assertEqual(record["sex_counts"]["sex_not_specified_share"], 10)

    def test_is_open_school_accepts_updated_or_sy_status(self) -> None:
        self.assertTrue(is_open_school({"UPDATED_STATUS_TEXT": "Open", "SY_STATUS_TEXT": "Closed"}))
        self.assertTrue(is_open_school({"UPDATED_STATUS_TEXT": "Closed", "SY_STATUS_TEXT": "Open"}))
        self.assertFalse(is_open_school({"UPDATED_STATUS_TEXT": "Closed", "SY_STATUS_TEXT": "Closed"}))

    def test_safe_share_handles_missing_denominator(self) -> None:
        self.assertIsNone(safe_share(4, None))
        self.assertIsNone(safe_share(4, 0))
        self.assertEqual(safe_share(1, 4), 0.25)

    def test_normalize_school_level_maps_legacy_codes(self) -> None:
        self.assertEqual(normalize_school_level("1"), "Elementary")
        self.assertEqual(normalize_school_level("3"), "High")
        self.assertEqual(normalize_school_level("N"), "Other")


class MembershipSchemaRoutingTests(unittest.TestCase):
    """Ensure read_membership routes to the wide path when MEMBER is present,
    even if TOTAL_INDICATOR is also in the schema (2017-18 / 2021-22 pattern)."""

    def _make_csv(self, rows: list[dict], tmp_path: Path) -> Path:
        import csv
        path = tmp_path / "membership.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        return path

    def setUp(self):
        import tempfile
        self._tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmp)

    def test_wide_path_taken_when_member_present_alongside_total_indicator(self):
        # Simulates the 2017-18 / 2021-22 schema: both MEMBER and TOTAL_INDICATOR exist.
        # The wide path must win so enrollment is populated.
        rows = [{
            "NCESSCH": "SCHOOL1",
            "MEMBER": "500",
            "TOTAL_INDICATOR": "Some Other Value",
            "AM": "5", "AS": "50", "BL": "40", "HI": "80", "HP": "5", "TR": "20", "WH": "290",
            "AMALM": "2", "ASALM": "25", "BLALM": "20", "HIALM": "40", "HPALM": "2", "TRALM": "10", "WHALM": "145",
            "AMALF": "3", "ASALF": "25", "BLALF": "20", "HIALF": "40", "HPALF": "3", "TRALF": "10", "WHALF": "145",
        }]
        csv_path = self._make_csv(rows, self._tmp)
        result = read_membership(csv_path, {"SCHOOL1"})
        self.assertIsNotNone(result["SCHOOL1"]["enrollment"], "enrollment must not be None")
        self.assertEqual(result["SCHOOL1"]["enrollment"], 500)

    def test_legacy_path_taken_when_only_total_indicator_present(self):
        # 2015-16 style: no MEMBER column.
        rows = [
            {
                "NCESSCH": "SCHOOL1",
                "TOTAL_INDICATOR": DERIVED_TOTAL_MINUS_ADULT,
                "GRADE": "No Category Codes",
                "RACE_ETHNICITY": "No Category Codes",
                "SEX": "No Category Codes",
                "STUDENT_COUNT": "200",
            },
        ]
        csv_path = self._make_csv(rows, self._tmp)
        result = read_membership(csv_path, {"SCHOOL1"})
        self.assertEqual(result["SCHOOL1"]["enrollment"], 200)


if __name__ == "__main__":
    unittest.main()
