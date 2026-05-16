from __future__ import annotations

import csv
import json
import platform
import shutil
import subprocess
import tempfile
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

from seattle_schools_dashboard.config import TARGET_DISTRICT_NAME_MAP, TARGET_STATE


LOOKUP_URL = "https://nces.ed.gov/ccd/datatables/api/Lookup/"
FILE_API_TEMPLATE = "https://nces.ed.gov/ccd/datatables/api/File/2/7/{school_year_id}/0/0/0"
NCES_BASE_URL = "https://nces.ed.gov"
LATEST_YEAR_COUNT = 10
DIRECTORY_COMPONENT = "Directory"
MEMBERSHIP_COMPONENT = "Membership"
LUNCH_COMPONENT = "Lunch Program Eligibility"
SCHOOL_CHARACTERISTICS_COMPONENT = "School Characteristics "
NO_CATEGORY = "No Category Codes"
DERIVED_TOTAL_MINUS_ADULT = "Derived - Education Unit Total minus Adult Education Count"
DERIVED_SUBTOTAL_MINUS_ADULT = "Derived - Subtotal by Race/Ethnicity and Sex minus Adult Education Count"
FRPL_GROUP = "Free and Reduced-price Lunch Table"
OPEN_STATUS = "Open"
CP1252 = "cp1252"

WIDE_RACE_COLUMN_MAP = {
    "AM": "american_indian_alaska_native_share",
    "AS": "asian_share",
    "BL": "black_african_american_share",
    "HI": "hispanic_latino_share",
    "HP": "native_hawaiian_pacific_islander_share",
    "TR": "two_or_more_races_share",
    "WH": "white_share",
}

# Standalone sex-total columns published in some NCES wide-format years.
# When present these are preferred because they include students of unspecified race.
# Column names are unconfirmed; treated as optional — missing columns fall back to
# the race×sex intersection sums below.
WIDE_MALE_TOTAL_COLUMNS = ("TOTM",)
WIDE_FEMALE_TOTAL_COLUMNS = ("TOTF",)

# Race×sex intersection columns — male and female counts per identified race group.
# Used when standalone sex totals are absent; students with unspecified race are not
# captured here and will inflate sex_not_specified_share as a residual.
WIDE_MALE_COLUMNS = ("AMALM", "ASALM", "BLALM", "HIALM", "HPALM", "TRALM", "WHALM")
WIDE_FEMALE_COLUMNS = ("AMALF", "ASALF", "BLALF", "HIALF", "HPALF", "TRALF", "WHALF")
LEGACY_SCHOOL_LEVEL_MAP = {
    "1": "Elementary",
    "2": "Middle",
    "3": "High",
    "4": "Other",
    "N": "Other",
}

RACE_METRIC_MAP = {
    "American Indian or Alaska Native": "american_indian_alaska_native_share",
    "Asian": "asian_share",
    "Black or African American": "black_african_american_share",
    "Hispanic/Latino": "hispanic_latino_share",
    "Native Hawaiian or Other Pacific Islander": "native_hawaiian_pacific_islander_share",
    "Two or more races": "two_or_more_races_share",
    "White": "white_share",
    "Not Specified": "race_not_specified_share",
}

SEX_METRIC_MAP = {
    "Female": "female_share",
    "Male": "male_share",
    "Not Specified": "sex_not_specified_share",
}

METRIC_DEFINITIONS = {
    "enrollment": {
        "label": "Enrollment",
        "category": "Enrollment",
        "format": "integer",
        "description": "Education unit total minus adult education count from the NCES CCD membership file.",
    },
    "combined_frpl_share": {
        "label": "Combined FRPL share",
        "category": "Economic Disadvantage",
        "format": "percent",
        "description": "Free lunch plus reduced-price lunch counts divided by education unit total minus adult education.",
    },
    "female_share": {
        "label": "Female share",
        "category": "Sex",
        "format": "percent",
        "description": "Female share of enrollment using the derived NCES membership denominator with adult education removed.",
    },
    "male_share": {
        "label": "Male share",
        "category": "Sex",
        "format": "percent",
        "description": "Male share of enrollment using the NCES membership file with adult education removed. Note: in 2015-16 (row-based NCES schema) sex is counted independently of race; in later years it is derived from race-by-sex columns, so students with unspecified race may be undercounted in male/female and overrepresented in 'sex not specified'.",
    },
    "sex_not_specified_share": {
        "label": "Sex not specified",
        "category": "Sex",
        "format": "percent",
        "description": "Share of enrollment with sex not specified. In years using the wide NCES schema (2016-17 onward) this is a residual that includes students whose race is also unspecified, so it may be slightly overstated relative to 2015-16.",
    },
    "american_indian_alaska_native_share": {
        "label": "American Indian or Alaska Native",
        "category": "Race/Ethnicity",
        "format": "percent",
        "description": "Race/ethnicity share from the NCES membership file with adult education removed. 'Race not specified' is an explicit category in 2015-16 and a residual in later years; small discontinuities at the 2015-16/2016-17 boundary are a schema artifact, not a real demographic shift.",
    },
    "asian_share": {
        "label": "Asian share",
        "category": "Race/Ethnicity",
        "format": "percent",
        "description": "Race/ethnicity share from the NCES membership file with adult education removed. 'Race not specified' is an explicit category in 2015-16 and a residual in later years; small discontinuities at the 2015-16/2016-17 boundary are a schema artifact, not a real demographic shift.",
    },
    "black_african_american_share": {
        "label": "Black or African American",
        "category": "Race/Ethnicity",
        "format": "percent",
        "description": "Race/ethnicity share from the NCES membership file with adult education removed. 'Race not specified' is an explicit category in 2015-16 and a residual in later years; small discontinuities at the 2015-16/2016-17 boundary are a schema artifact, not a real demographic shift.",
    },
    "hispanic_latino_share": {
        "label": "Hispanic/Latino share",
        "category": "Race/Ethnicity",
        "format": "percent",
        "description": "Race/ethnicity share from the NCES membership file with adult education removed. 'Race not specified' is an explicit category in 2015-16 and a residual in later years; small discontinuities at the 2015-16/2016-17 boundary are a schema artifact, not a real demographic shift.",
    },
    "native_hawaiian_pacific_islander_share": {
        "label": "Native Hawaiian or Pacific Islander",
        "category": "Race/Ethnicity",
        "format": "percent",
        "description": "Race/ethnicity share from the NCES membership file with adult education removed. 'Race not specified' is an explicit category in 2015-16 and a residual in later years; small discontinuities at the 2015-16/2016-17 boundary are a schema artifact, not a real demographic shift.",
    },
    "two_or_more_races_share": {
        "label": "Two or more races",
        "category": "Race/Ethnicity",
        "format": "percent",
        "description": "Race/ethnicity share from the NCES membership file with adult education removed. 'Race not specified' is an explicit category in 2015-16 and a residual in later years; small discontinuities at the 2015-16/2016-17 boundary are a schema artifact, not a real demographic shift.",
    },
    "white_share": {
        "label": "White share",
        "category": "Race/Ethnicity",
        "format": "percent",
        "description": "Race/ethnicity share from the NCES membership file with adult education removed. 'Race not specified' is an explicit category in 2015-16 and a residual in later years; small discontinuities at the 2015-16/2016-17 boundary are a schema artifact, not a real demographic shift.",
    },
    "race_not_specified_share": {
        "label": "Race not specified",
        "category": "Race/Ethnicity",
        "format": "percent",
        "description": "Share of enrollment with race/ethnicity not specified. In 2015-16 this is an explicit NCES-reported category; in 2016-17 onward it is computed as enrollment minus the sum of the seven identified-race counts, so it absorbs any rounding or suppression gaps.",
    },
    "ela_proficiency_rate": {
        "label": "ELA proficiency",
        "category": "Assessment",
        "format": "percent",
        "description": "Share of tested students meeting or exceeding standard on the Smarter Balanced ELA assessment (OSPI). 2019-20 statewide testing was cancelled (COVID). 2020-21 statewide participation was ~54% — well below the 95% federal threshold — so individual school values may not be representative. OSPI changed the reporting label from 'percent met standard' to 'percent consistent grade-level knowledge' in 2022-23; the underlying Smarter Balanced cut scores are unchanged.",
        "caveat_years": {"2020-2021": "Low test participation (~54% statewide). Values may not be representative."},
    },
    "math_proficiency_rate": {
        "label": "Math proficiency",
        "category": "Assessment",
        "format": "percent",
        "description": "Share of tested students meeting or exceeding standard on the Smarter Balanced Math assessment (OSPI). 2019-20 statewide testing was cancelled (COVID). 2020-21 statewide participation was ~54% — well below the 95% federal threshold — so individual school values may not be representative. OSPI changed the reporting label from 'percent met standard' to 'percent consistent grade-level knowledge' in 2022-23; the underlying Smarter Balanced cut scores are unchanged.",
        "caveat_years": {"2020-2021": "Low test participation (~54% statewide). Values may not be representative."},
    },
    "four_year_grad_rate": {
        "label": "4-yr graduation rate",
        "category": "Graduation",
        "format": "percent",
        "description": "Four-year cohort graduation rate for all students (OSPI). Only meaningful for high schools; other school levels will show no data.",
    },
    "ela_growth_percentile": {
        "label": "ELA growth (median SGP)",
        "category": "Growth",
        "format": "integer",
        "description": "Median Student Growth Percentile for ELA across all tested grades (OSPI). 50 = typical growth; above 50 = above-typical. Grades 4–8 only (requires prior-year score). Not available 2019-20 through 2021-22.",
    },
    "math_growth_percentile": {
        "label": "Math growth (median SGP)",
        "category": "Growth",
        "format": "integer",
        "description": "Median Student Growth Percentile for Math across all tested grades (OSPI). 50 = typical growth; above 50 = above-typical. Grades 4–8 only (requires prior-year score). Not available 2019-20 through 2021-22.",
    },
}


@dataclass(frozen=True)
class SchoolYearInfo:
    id: int
    label: str
    data_year: str


def build_dashboard_payload(project_root: Path) -> dict[str, object]:
    working_root = project_root / ".tmp-build"
    working_root.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix="nces-build-", dir=working_root))

    try:
        school_years = fetch_recent_school_years()
        districts_by_id: dict[str, dict[str, object]] = {}
        schools_by_id: dict[str, dict[str, object]] = {}
        records: list[dict[str, object]] = []

        for school_year in school_years:
            year_payload = process_school_year(temp_root, school_year)
            for district in year_payload["districts"]:
                districts_by_id[district["id"]] = district
            for school in year_payload["schools"]:
                existing = schools_by_id.get(school["id"], {})
                schools_by_id[school["id"]] = existing | school
            records.extend(year_payload["records"])

        ordered_districts = [
            districts_by_id[district_id]
            for district_id in sorted(districts_by_id, key=lambda current: districts_by_id[current]["name"])
        ]
        ordered_schools = [
            schools_by_id[school_id]
            for school_id in sorted(schools_by_id, key=lambda current: schools_by_id[current]["name"])
        ]
        initial_school_ids = [
            school["id"]
            for school in ordered_schools
            if school["district_name"] in {"Seattle", "Bellevue"}
        ]

        return {
            "generated_at": _utc_timestamp(),
            "years": [school_year.data_year for school_year in school_years],
            "districts": ordered_districts,
            "schools": ordered_schools,
            "records": records,
            "initial_school_ids": initial_school_ids,
        }
    finally:
        _remove_tree(temp_root)
        _remove_tree(working_root)


def fetch_recent_school_years() -> list[SchoolYearInfo]:
    payload = _read_json_from_url(LOOKUP_URL)
    school_years = [
        SchoolYearInfo(
            id=entry["id"],
            label=entry["name"],
            data_year=entry["name"].replace(" ", ""),
        )
        for entry in payload["schoolYears"]
        if entry["id"] > 0
    ]
    return list(reversed(school_years[:LATEST_YEAR_COUNT]))


def process_school_year(temp_root: Path, school_year: SchoolYearInfo) -> dict[str, object]:
    year_root = temp_root / f"school-year-{school_year.id}"
    year_root.mkdir(parents=True, exist_ok=True)

    try:
        listing = _read_json_from_url(FILE_API_TEMPLATE.format(school_year_id=school_year.id))
        urls = get_required_component_urls(listing)
        csv_paths = {
            component: download_and_extract_csv(year_root, component, url)
            for component, url in urls.items()
        }

        districts, schools = read_directory(csv_paths[DIRECTORY_COMPONENT])
        selected_school_ids = set(schools)
        if not selected_school_ids:
            return {"districts": [], "schools": [], "records": []}

        enrich_school_characteristics(csv_paths[SCHOOL_CHARACTERISTICS_COMPONENT], schools, selected_school_ids)
        school_year_records = read_membership(csv_paths[MEMBERSHIP_COMPONENT], selected_school_ids)
        apply_lunch_metrics(csv_paths[LUNCH_COMPONENT], school_year_records, selected_school_ids)

        records = finalize_records(school_year.data_year, schools, school_year_records)
        district_list = []
        for district_id, district in districts.items():
            district_list.append(
                {
                    "id": district_id,
                    "name": district["name"],
                    "school_ids": sorted(district["school_ids"], key=lambda current: schools[current]["name"]),
                }
            )

        school_list = list(schools.values())
        school_list.sort(key=lambda school: school["name"])
        district_list.sort(key=lambda district: district["name"])

        return {"districts": district_list, "schools": school_list, "records": records}
    finally:
        _remove_tree(year_root)


def get_required_component_urls(listing: dict[str, object]) -> dict[str, str]:
    title_group = listing["selectionGroupModels"][0]["titleGroups"][0]
    urls: dict[str, str] = {}

    for element_group in title_group["elementGroups"]:
        if element_group["elementType"] != "Data File":
            continue
        for component_group in element_group["componentGroups"]:
            component = component_group["component"]
            if component in {
                DIRECTORY_COMPONENT,
                MEMBERSHIP_COMPONENT,
                LUNCH_COMPONENT,
                SCHOOL_CHARACTERISTICS_COMPONENT,
            }:
                urls[component] = component_group["files"][0]["fileURL"]

    return urls


def download_and_extract_csv(year_root: Path, component: str, url: str) -> Path:
    zip_dir = year_root / "zip"
    extract_dir = year_root / "extract" / _slugify(component)
    zip_dir.mkdir(parents=True, exist_ok=True)
    extract_dir.mkdir(parents=True, exist_ok=True)

    zip_name = url.rsplit("/", 1)[-1]
    zip_path = zip_dir / zip_name

    _download_file(url, zip_path)
    data_entry_name = _find_data_entry_name(zip_path)
    extracted_path = extract_dir / Path(data_entry_name).name
    _extract_csv(zip_path, extract_dir, data_entry_name)
    return extracted_path


def read_directory(csv_path: Path) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]]]:
    districts: dict[str, dict[str, object]] = {}
    schools: dict[str, dict[str, object]] = {}

    for row in _iter_csv_rows(csv_path):
        state = _get_first(row, "ST", "STABR", default="")
        if state != TARGET_STATE:
            continue
        lea_name = _get_first(row, "LEA_NAME", default="")
        if lea_name not in TARGET_DISTRICT_NAME_MAP:
            continue
        if not is_open_school(row):
            continue

        district_name = TARGET_DISTRICT_NAME_MAP[lea_name]
        district_id = _slugify(district_name)
        school_id = _get_first(row, "NCESSCH", default="")

        districts.setdefault(
            district_id,
            {"id": district_id, "name": district_name, "school_ids": []},
        )
        districts[district_id]["school_ids"].append(school_id)

        schools[school_id] = {
            "id": school_id,
            "name": _get_first(row, "SCH_NAME", default=""),
            "district_id": district_id,
            "district_name": district_name,
            "school_level": normalize_school_level(_get_first(row, "LEVEL", default="")),
            "school_type": _get_first(row, "SCH_TYPE_TEXT", default=""),
            "charter": _get_first(row, "CHARTER_TEXT", default=""),
        }

    return districts, schools


def enrich_school_characteristics(
    csv_path: Path,
    schools: dict[str, dict[str, object]],
    selected_school_ids: set[str],
) -> None:
    for row in _iter_csv_rows(csv_path):
        school_id = _get_first(row, "NCESSCH", default="")
        if school_id not in selected_school_ids:
            continue
        schools[school_id]["nslp_status"] = _get_first(row, "NSLP_STATUS_TEXT", "NSLPSTATUS_TEXT", default="")
        schools[school_id]["virtual_status"] = _get_first(row, "VIRTUAL_TEXT", "VIRTUAL", default="")
        schools[school_id]["shared_time"] = _get_first(row, "SHARED_TIME", default="")


def read_membership(csv_path: Path, selected_school_ids: set[str]) -> dict[str, dict[str, object]]:
    school_year_records: dict[str, dict[str, object]] = {}

    for row in _iter_csv_rows(csv_path):
        school_id = _get_first(row, "NCESSCH", default="")
        if school_id not in selected_school_ids:
            continue

        record = school_year_records.setdefault(school_id, make_school_year_record(school_id))
        # Some NCES years (e.g. 2017-18, 2021-22) carry TOTAL_INDICATOR in the schema
        # alongside MEMBER; checking MEMBER first ensures those files use the wide path.
        if "MEMBER" in row:
            apply_wide_membership_row(record, row)
        elif "TOTAL_INDICATOR" in row:
            apply_membership_row(record, row)

    return school_year_records


def make_school_year_record(school_id: str) -> dict[str, object]:
    return {
        "school_id": school_id,
        "enrollment": None,
        "frpl_count": 0,
        "race_counts": {metric_key: 0 for metric_key in RACE_METRIC_MAP.values()},
        "sex_counts": {metric_key: 0 for metric_key in SEX_METRIC_MAP.values()},
    }


def apply_membership_row(record: dict[str, object], row: dict[str, str]) -> None:
    total_indicator = row["TOTAL_INDICATOR"]
    grade = row["GRADE"]
    race = row["RACE_ETHNICITY"]
    sex = row["SEX"]
    student_count = _safe_int(row["STUDENT_COUNT"])
    if student_count is None:
        return

    if (
        total_indicator == DERIVED_TOTAL_MINUS_ADULT
        and grade == NO_CATEGORY
        and race == NO_CATEGORY
        and sex == NO_CATEGORY
    ):
        record["enrollment"] = student_count
        return

    if total_indicator != DERIVED_SUBTOTAL_MINUS_ADULT or grade != NO_CATEGORY:
        return

    race_metric = RACE_METRIC_MAP.get(race)
    if race_metric:
        record["race_counts"][race_metric] += student_count

    sex_metric = SEX_METRIC_MAP.get(sex)
    if sex_metric:
        record["sex_counts"][sex_metric] += student_count


def apply_wide_membership_row(record: dict[str, object], row: dict[str, str]) -> None:
    enrollment = _safe_int(row.get("MEMBER"))
    if enrollment is None:
        return

    record["enrollment"] = enrollment

    known_race_total = 0
    for column, metric_key in WIDE_RACE_COLUMN_MAP.items():
        count = _safe_int(row.get(column)) or 0
        record["race_counts"][metric_key] = count
        known_race_total += count

    # Prefer standalone sex totals (include all-race students); fall back to
    # summing race×sex intersections (excludes students with unspecified race).
    male_standalone = next(
        (_safe_int(row.get(col)) for col in WIDE_MALE_TOTAL_COLUMNS if _safe_int(row.get(col)) is not None),
        None,
    )
    female_standalone = next(
        (_safe_int(row.get(col)) for col in WIDE_FEMALE_TOTAL_COLUMNS if _safe_int(row.get(col)) is not None),
        None,
    )
    male_total = male_standalone if male_standalone is not None else sum(
        (_safe_int(row.get(column)) or 0) for column in WIDE_MALE_COLUMNS
    )
    female_total = female_standalone if female_standalone is not None else sum(
        (_safe_int(row.get(column)) or 0) for column in WIDE_FEMALE_COLUMNS
    )
    record["sex_counts"]["female_share"] = female_total
    record["sex_counts"]["male_share"] = male_total
    record["race_counts"]["race_not_specified_share"] = max(enrollment - known_race_total, 0)
    record["sex_counts"]["sex_not_specified_share"] = max(enrollment - male_total - female_total, 0)


def apply_lunch_metrics(
    csv_path: Path,
    school_year_records: dict[str, dict[str, object]],
    selected_school_ids: set[str],
) -> None:
    for row in _iter_csv_rows(csv_path):
        school_id = _get_first(row, "NCESSCH", default="")
        if school_id not in selected_school_ids:
            continue
        if "TOTFRL" in row:
            frpl_count = _safe_int(row.get("TOTFRL"))
            if frpl_count is None:
                free_count = _safe_int(row.get("FRELCH")) or 0
                reduced_count = _safe_int(row.get("REDLCH")) or 0
                frpl_count = free_count + reduced_count
            school_year_records.setdefault(school_id, make_school_year_record(school_id))["frpl_count"] = frpl_count or 0
            continue

        if row["DATA_GROUP"] != FRPL_GROUP or row["TOTAL_INDICATOR"] != "Category Set A":
            continue
        if row["LUNCH_PROGRAM"] not in {"Free lunch qualified", "Reduced-price lunch qualified"}:
            continue
        student_count = _safe_int(row["STUDENT_COUNT"])
        if student_count is None:
            continue

        school_year_records.setdefault(school_id, make_school_year_record(school_id))["frpl_count"] += student_count


def finalize_records(
    year_label: str,
    schools: dict[str, dict[str, object]],
    school_year_records: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    finalized: list[dict[str, object]] = []

    for school_id in sorted(school_year_records):
        record = school_year_records[school_id]
        school = schools[school_id]
        enrollment = record["enrollment"]
        finalized_record = {
            "district_id": school["district_id"],
            "district_name": school["district_name"],
            "school_id": school_id,
            "school_name": school["name"],
            "school_level": school["school_level"],
            "year": year_label,
            "enrollment": enrollment,
            "combined_frpl_share": safe_share(record["frpl_count"], enrollment),
        }

        for metric_key, count in record["race_counts"].items():
            finalized_record[metric_key] = safe_share(count, enrollment)
        for metric_key, count in record["sex_counts"].items():
            finalized_record[metric_key] = safe_share(count, enrollment)

        finalized.append(finalized_record)

    return finalized


def fetch_nces_data(destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    return destination


def is_open_school(row: dict[str, str]) -> bool:
    return row.get("UPDATED_STATUS_TEXT") == OPEN_STATUS or row.get("SY_STATUS_TEXT") == OPEN_STATUS


def normalize_school_level(value: str) -> str:
    return LEGACY_SCHOOL_LEVEL_MAP.get(value, value or "Unknown")


def safe_share(numerator: int | None, denominator: int | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return round(numerator / denominator, 6)


def _read_json_from_url(url: str) -> dict[str, object]:
    with urllib.request.urlopen(url) as response:
        return json.load(response)


def _download_file(url: str, destination: Path) -> None:
    with urllib.request.urlopen(urljoin(NCES_BASE_URL, url)) as response, destination.open("wb") as handle:
        handle.write(response.read())


def _extract_csv(zip_path: Path, output_dir: Path, data_entry_name: str) -> None:
    if platform.system() == "Windows":
        _extract_csv_with_shell(zip_path, output_dir, data_entry_name)
    else:
        _extract_csv_with_7z(zip_path, output_dir, data_entry_name)


def _extract_csv_with_shell(zip_path: Path, output_dir: Path, data_entry_name: str) -> None:
    resolved_zip_path = zip_path.resolve()
    resolved_output_dir = output_dir.resolve()
    script = f"""
$zip = '{_ps_escape(resolved_zip_path)}'
$dest = '{_ps_escape(resolved_output_dir)}'
$entryName = '{_ps_escape(data_entry_name)}'
$targetName = '{_ps_escape(Path(data_entry_name).name)}'
$shell = New-Object -ComObject Shell.Application
$source = $shell.NameSpace($zip)
$target = $shell.NameSpace($dest)
if ($null -eq $source) {{ throw 'Could not open ZIP archive.' }}
if ($null -eq $target) {{ throw 'Could not open extraction destination.' }}
$expectedPath = "$zip\\$entryName"
$targetBase = [System.IO.Path]::GetFileNameWithoutExtension($targetName)
$item = $source.Items() | Where-Object {{
    $_.Path -eq $expectedPath -or
    $_.Path -like "*$entryName" -or
    $_.Path -like "*$targetName" -or
    $_.Name -eq $targetName -or
    $_.Name -eq $targetBase
}} | Select-Object -First 1
if ($null -eq $item) {{ throw 'CSV entry not found inside archive.' }}
$target.CopyHere($item, 16)
$targetPath = Join-Path $dest $targetName
$stable = 0
$previous = -1
for ($i = 0; $i -lt 900; $i++) {{
    if (Test-Path $targetPath) {{
        $current = (Get-Item $targetPath).Length
        if ($current -gt 0 -and $current -eq $previous) {{
            $stable++
            if ($stable -ge 3) {{ break }}
        }} else {{
            $stable = 0
        }}
        $previous = $current
    }}
    Start-Sleep -Seconds 1
}}
if (-not (Test-Path $targetPath)) {{ throw 'CSV extraction did not finish.' }}
"""
    subprocess.run(
        [
            r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
            "-NoProfile",
            "-Command",
            script,
        ],
        check=True,
    )


def _extract_csv_with_7z(zip_path: Path, output_dir: Path, data_entry_name: str) -> None:
    subprocess.run(
        ["7z", "e", "-y", f"-o{output_dir}", str(zip_path), data_entry_name],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _iter_csv_rows(csv_path: Path):
    handle = csv_path.open("r", encoding=_detect_csv_encoding(csv_path), errors="replace", newline="")
    try:
        reader = csv.DictReader(handle)
        for row in reader:
            yield row
    finally:
        handle.close()


def _remove_tree(path: Path) -> None:
    if not path.exists():
        return

    import os
    import stat

    def _on_error(func, error_path, exc_info):
        # On Windows, read-only or locked files need chmod before removal
        try:
            os.chmod(error_path, stat.S_IWRITE)
            func(error_path)
        except OSError:
            time.sleep(1)
            try:
                func(error_path)
            except OSError:
                pass

    shutil.rmtree(path, onerror=_on_error)


def _slugify(value: str) -> str:
    return value.lower().replace(".", "").replace(",", "").replace(" ", "-")


def _ps_escape(path: Path | str) -> str:
    return str(path).replace("'", "''")


def _safe_int(value: str | None) -> int | None:
    if value in (None, "", "#"):
        return None
    parsed = int(value)
    if parsed < 0:
        return None
    return parsed


def _detect_csv_encoding(csv_path: Path) -> str:
    if "_1516_" in csv_path.name:
        return CP1252

    size = csv_path.stat().st_size
    sample_points = [0]
    if size > 8192:
        sample_points.extend([size // 2, max(size - 4096, 0)])

    with csv_path.open("rb") as handle:
        for point in sample_points:
            handle.seek(point)
            sample = handle.read(4096)
            try:
                sample.decode("utf-8-sig")
            except UnicodeDecodeError:
                return CP1252
    return "utf-8-sig"


def _get_first(row: dict[str, str], *keys: str, default: str) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return default


def _find_data_entry_name(zip_path: Path) -> str:
    with zipfile.ZipFile(zip_path) as archive:
        candidates = [
            entry.filename
            for entry in archive.infolist()
            if not entry.filename.lower().endswith(".sas7bdat")
        ]
    if not candidates:
        raise ValueError(f"No flat data file found inside {zip_path.name}")
    return candidates[0]


def _utc_timestamp() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()
