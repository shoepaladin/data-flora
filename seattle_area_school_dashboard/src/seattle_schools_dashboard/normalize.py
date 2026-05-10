from collections.abc import Mapping

from seattle_schools_dashboard.config import CANONICAL_FIELD_MAP


def normalize_record(raw_record: Mapping[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    missing_required: list[str] = []

    for canonical_name, candidates in CANONICAL_FIELD_MAP.items():
        value = None
        for candidate in candidates:
            if candidate in raw_record and raw_record[candidate] not in (None, ""):
                value = raw_record[candidate]
                break
        if value is None and canonical_name in REQUIRED_FIELDS:
            missing_required.append(canonical_name)
        normalized[canonical_name] = value

    if missing_required:
        missing = ", ".join(sorted(missing_required))
        raise ValueError(f"Missing required canonical fields: {missing}")

    if normalized["year"] is not None:
        normalized["year"] = int(normalized["year"])
    if normalized["enrollment"] is not None:
        normalized["enrollment"] = int(normalized["enrollment"])
    for percent_field in (
        "students_of_color_pct",
        "english_learner_pct",
        "economically_disadvantaged_pct",
        "graduation_rate",
        "math_proficiency",
        "reading_proficiency",
    ):
        if normalized[percent_field] is not None:
            normalized[percent_field] = float(normalized[percent_field])

    return normalized


REQUIRED_FIELDS = {
    "school_id",
    "district_id",
    "district_name",
    "school_name",
    "school_level",
    "year",
}
