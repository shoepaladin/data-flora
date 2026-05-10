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

TARGET_STATE = "WA"

TARGET_DISTRICT_NAME_MAP = {
    "Seattle School District No. 1": "Seattle",
    "Seattle Public Schools": "Seattle",
    "Bellevue School District": "Bellevue",
    "Renton School District": "Renton",
    "Issaquah School District": "Issaquah",
    "Snoqualmie Valley School District": "Snoqualmie Valley",
    "Lake Washington School District": "Lake Washington",
    "Mercer Island School District": "Mercer Island",
    "Bainbridge Island School District": "Bainbridge Island",
    "North Kitsap School District": "North Kitsap",
    "Central Kitsap School District": "Central Kitsap",
    "Vashon Island School District": "Vashon Island",
}

CANONICAL_FIELD_MAP = {
    "school_id": ["school_id", "nces_school_id", "school_identifier"],
    "district_id": ["district_id", "lea_id", "district_identifier"],
    "district_name": ["district_name", "lea_name", "district"],
    "school_name": ["school_name", "name", "school"],
    "school_level": ["school_level", "level"],
    "year": ["year", "school_year"],
    "enrollment": ["enrollment", "student_count", "membership"],
    "students_of_color_pct": ["students_of_color_pct", "students_of_color_share"],
    "english_learner_pct": ["english_learner_pct", "ell_share", "english_learners_pct"],
    "economically_disadvantaged_pct": [
        "economically_disadvantaged_pct",
        "econ_disadvantaged_share",
        "frpl_pct",
    ],
    "graduation_rate": ["graduation_rate", "grad_rate"],
    "math_proficiency": ["math_proficiency", "math_pct_prof"],
    "reading_proficiency": ["reading_proficiency", "reading_pct_prof"],
}
