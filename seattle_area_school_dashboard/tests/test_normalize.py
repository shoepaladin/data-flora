from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seattle_schools_dashboard.normalize import normalize_record


class NormalizeRecordTests(unittest.TestCase):
    def test_uses_alternate_source_column_names(self) -> None:
        raw_record = {
            "nces_school_id": "123",
            "lea_id": "456",
            "lea_name": "Seattle",
            "name": "Sample High School",
            "level": "High",
            "school_year": "2024",
            "membership": "812",
            "students_of_color_pct": 0.55,
            "english_learner_pct": 0.11,
            "economically_disadvantaged_pct": 0.32,
            "grad_rate": 0.91,
        }

        normalized = normalize_record(raw_record)

        self.assertEqual(normalized["school_id"], "123")
        self.assertEqual(normalized["district_id"], "456")
        self.assertEqual(normalized["district_name"], "Seattle")
        self.assertEqual(normalized["school_name"], "Sample High School")
        self.assertEqual(normalized["school_level"], "High")
        self.assertEqual(normalized["year"], 2024)
        self.assertEqual(normalized["enrollment"], 812)
        self.assertEqual(normalized["students_of_color_pct"], 0.55)
        self.assertEqual(normalized["english_learner_pct"], 0.11)
        self.assertEqual(normalized["economically_disadvantaged_pct"], 0.32)
        self.assertEqual(normalized["graduation_rate"], 0.91)

    def test_raises_on_missing_required_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "district_id"):
            normalize_record(
                {
                    "school_id": "123",
                    "district_name": "Seattle",
                    "school_name": "Sample High School",
                    "school_level": "High",
                    "year": "2024",
                }
            )

    def test_percent_fields_are_coerced_to_floats(self) -> None:
        normalized = normalize_record(
            {
                "school_id": "123",
                "district_id": "456",
                "district_name": "Seattle",
                "school_name": "Sample High School",
                "school_level": "High",
                "year": "2024",
                "students_of_color_pct": "0.52",
                "english_learner_pct": "0.10",
                "economically_disadvantaged_pct": "0.34",
                "math_pct_prof": "0.61",
                "reading_pct_prof": "0.68",
                "grad_rate": "0.93",
            }
        )

        self.assertEqual(normalized["students_of_color_pct"], 0.52)
        self.assertEqual(normalized["english_learner_pct"], 0.10)
        self.assertEqual(normalized["economically_disadvantaged_pct"], 0.34)
        self.assertEqual(normalized["math_proficiency"], 0.61)
        self.assertEqual(normalized["reading_proficiency"], 0.68)
        self.assertEqual(normalized["graduation_rate"], 0.93)


if __name__ == "__main__":
    unittest.main()
