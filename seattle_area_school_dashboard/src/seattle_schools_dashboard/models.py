from dataclasses import dataclass


@dataclass(frozen=True)
class SchoolRecord:
    school_id: str
    district_id: str
    district_name: str
    school_name: str
    school_level: str
    year: int
    enrollment: int | None = None
    graduation_rate: float | None = None
    math_proficiency: float | None = None
    reading_proficiency: float | None = None
