from __future__ import annotations

from datetime import UTC, datetime

from seattle_schools_dashboard.config import DISTRICT_GROUPS


YEARS = list(range(2015, 2025))

METRIC_DEFINITIONS = {
    "enrollment": {
        "label": "Enrollment",
        "category": "Enrollment",
        "format": "integer",
        "description": "Total student enrollment for the school-year snapshot.",
    },
    "students_of_color_pct": {
        "label": "Students of color",
        "category": "Demographics",
        "format": "percent",
        "description": "Share of enrolled students identified as students of color.",
    },
    "english_learner_pct": {
        "label": "English learners",
        "category": "Demographics",
        "format": "percent",
        "description": "Share of enrolled students participating in English learner services.",
    },
    "economically_disadvantaged_pct": {
        "label": "Economically disadvantaged",
        "category": "Demographics",
        "format": "percent",
        "description": "Share of enrolled students identified as economically disadvantaged.",
    },
    "math_proficiency": {
        "label": "Math proficiency",
        "category": "Proficiency",
        "format": "percent",
        "description": "Share of students meeting or exceeding math standards.",
    },
    "reading_proficiency": {
        "label": "Reading proficiency",
        "category": "Proficiency",
        "format": "percent",
        "description": "Share of students meeting or exceeding reading standards.",
    },
    "graduation_rate": {
        "label": "Graduation rate",
        "category": "Graduation",
        "format": "percent",
        "description": "Four-year graduation rate for high schools where available.",
    },
}

_SCHOOL_PATTERNS = [
    ("Harbor Elementary", "Elementary"),
    ("Ridge Middle", "Middle"),
    ("Summit High", "High"),
]


def build_pilot_dashboard_payload() -> dict[str, object]:
    district_names = DISTRICT_GROUPS["puget_sound_core"]
    districts: list[dict[str, object]] = []
    schools: list[dict[str, object]] = []
    records: list[dict[str, object]] = []

    for district_index, district_name in enumerate(district_names):
        district_id = _slugify(district_name)
        district_school_ids: list[str] = []

        for school_index, (pattern_name, school_level) in enumerate(_SCHOOL_PATTERNS):
            school_name = f"{district_name} {pattern_name}"
            school_id = _slugify(school_name)
            district_school_ids.append(school_id)
            schools.append(
                {
                    "id": school_id,
                    "name": school_name,
                    "district_id": district_id,
                    "district_name": district_name,
                    "school_level": school_level,
                }
            )

            records.extend(
                _generate_school_records(
                    district_index=district_index,
                    district_id=district_id,
                    district_name=district_name,
                    school_index=school_index,
                    school_id=school_id,
                    school_name=school_name,
                    school_level=school_level,
                )
            )

        districts.append(
            {
                "id": district_id,
                "name": district_name,
                "school_ids": district_school_ids,
            }
        )

    initial_school_ids = [
        school["id"]
        for school in schools
        if school["district_name"] in {"Seattle", "Bellevue"}
    ]

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "title": "Seattle Area School Dashboard Pilot",
        "subtitle": "Pilot build with synthetic data until live NCES ingestion is connected.",
        "years": YEARS,
        "districts": districts,
        "schools": schools,
        "records": records,
        "metrics": METRIC_DEFINITIONS,
        "initial_state": {
            "selected_school_ids": initial_school_ids,
            "metric_key": "enrollment",
            "year_window": 5,
        },
    }


def build_pilot_raw_rows() -> list[dict[str, object]]:
    payload = build_pilot_dashboard_payload()
    rows: list[dict[str, object]] = []

    for record in payload["records"]:
        school = next(
            school_info
            for school_info in payload["schools"]
            if school_info["id"] == record["school_id"]
        )
        rows.append(
            {
                "nces_school_id": record["school_id"],
                "lea_id": school["district_id"],
                "lea_name": school["district_name"],
                "name": school["name"],
                "level": school["school_level"],
                "school_year": record["year"],
                "membership": record["enrollment"],
                "students_of_color_pct": record["students_of_color_pct"],
                "english_learner_pct": record["english_learner_pct"],
                "economically_disadvantaged_pct": record["economically_disadvantaged_pct"],
                "math_pct_prof": record["math_proficiency"],
                "reading_pct_prof": record["reading_proficiency"],
                "grad_rate": record["graduation_rate"],
            }
        )

    return rows


def _generate_school_records(
    *,
    district_index: int,
    district_id: str,
    district_name: str,
    school_index: int,
    school_id: str,
    school_name: str,
    school_level: str,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    level_adjustment = {
        "Elementary": -0.02,
        "Middle": 0.01,
        "High": 0.03,
    }[school_level]

    for year in YEARS:
        year_offset = year - YEARS[0]
        pulse = ((district_index + 1) * (school_index + 2) + year_offset) % 5
        enrollment = 360 + (district_index * 38) + (school_index * 120) + (year_offset * 9) + (pulse * 6)
        students_of_color_pct = _clamp(
            0.22 + (district_index * 0.018) + (school_index * 0.012) + (year_offset * 0.003),
            0.18,
            0.86,
        )
        english_learner_pct = _clamp(
            0.04 + (district_index * 0.007) + (school_index * 0.004) + (year_offset * 0.0015),
            0.03,
            0.42,
        )
        economically_disadvantaged_pct = _clamp(
            0.16 + (district_index * 0.015) + (school_index * 0.008) + (year_offset * 0.002),
            0.12,
            0.74,
        )
        math_proficiency = _clamp(
            0.48 + (district_index * 0.012) + level_adjustment + (year_offset * 0.005) - (school_index * 0.01),
            0.28,
            0.94,
        )
        reading_proficiency = _clamp(
            0.55 + (district_index * 0.01) + level_adjustment + (year_offset * 0.004),
            0.3,
            0.96,
        )
        graduation_rate = None
        if school_level == "High":
            graduation_rate = _clamp(
                0.8 + (district_index * 0.008) + (year_offset * 0.004),
                0.7,
                0.98,
            )
            if district_index % 4 == 0 and year in {2015, 2016}:
                graduation_rate = None

        records.append(
            {
                "district_id": district_id,
                "district_name": district_name,
                "school_id": school_id,
                "school_name": school_name,
                "school_level": school_level,
                "year": year,
                "enrollment": enrollment,
                "students_of_color_pct": round(students_of_color_pct, 3),
                "english_learner_pct": round(english_learner_pct, 3),
                "economically_disadvantaged_pct": round(economically_disadvantaged_pct, 3),
                "math_proficiency": round(math_proficiency, 3),
                "reading_proficiency": round(reading_proficiency, 3),
                "graduation_rate": None if graduation_rate is None else round(graduation_rate, 3),
            }
        )

    return records


def _slugify(value: str) -> str:
    return (
        value.lower()
        .replace("&", "and")
        .replace(".", "")
        .replace(",", "")
        .replace(" ", "-")
    )


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))
