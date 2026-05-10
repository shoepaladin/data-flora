DISTRICT_GROUPS = {
    "puget_sound_core": [
        "Seattle",
        "Bellevue",
        "Renton",
        "Issaquah",
        "Snoqualmie Valley",
        "Lake Washington",
        "Mercer Island",
        "Bainbridge Island",
        "North Kitsap",
        "Central Kitsap",
        "Vashon Island",
    ],
}

CANONICAL_FIELD_MAP = {
    "school_id": ["school_id", "nces_school_id", "school_identifier"],
    "district_id": ["district_id", "lea_id", "district_identifier"],
    "district_name": ["district_name", "lea_name", "district"],
    "school_name": ["school_name", "name", "school"],
    "school_level": ["school_level", "level"],
    "year": ["year", "school_year"],
    "enrollment": ["enrollment", "student_count", "membership"],
    "graduation_rate": ["graduation_rate", "grad_rate"],
    "math_proficiency": ["math_proficiency", "math_pct_prof"],
    "reading_proficiency": ["reading_proficiency", "reading_pct_prof"],
}
