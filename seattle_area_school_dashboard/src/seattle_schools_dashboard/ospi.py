from __future__ import annotations

import csv
import io
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from seattle_schools_dashboard.config import TARGET_DISTRICT_NAME_MAP


ASSESSMENT_DATASETS = [
    ("2014-15 to 2021-22", "https://data.wa.gov/resource/292v-tb9r.csv"),
    ("2022-23", "https://data.wa.gov/resource/xh7m-utwp.csv"),
    ("2023-24", "https://data.wa.gov/resource/x73g-mrqp.csv"),
    ("2024-25", "https://data.wa.gov/resource/h5d9-vgwi.csv"),
]

# Chronic Absenteeism — % of students missing 10%+ of school days (OSPI Report Card).
# Resource IDs discovered via probe_ospi_schemas.py; populated after schema verification.
CHRONIC_ABSENTEEISM_DATASETS: list[tuple[str, str]] = [
    # ("2024-25", "https://data.wa.gov/resource/XXXX-XXXX.csv"),  # TODO: fill from probe
]

# Discipline — short-term out-of-school suspension rate (OSPI Report Card Discipline).
DISCIPLINE_DATASETS = [
    ("2024-25", "https://data.wa.gov/resource/c9tq-ntbq.csv"),
]

# English Learner share — % of students designated EL (OSPI Report Card Student Counts).
# Resource IDs discovered via probe_ospi_schemas.py; populated after schema verification.
ENGLISH_LEARNER_DATASETS: list[tuple[str, str]] = [
    # ("2024-25", "https://data.wa.gov/resource/XXXX-XXXX.csv"),  # TODO: fill from probe
]

# Non-English home language — % of students speaking a language other than English at home.
LANGUAGE_DATASETS = [
    ("2024-25", "https://data.wa.gov/resource/g4qj-yi5j.csv"),
]

GRADUATION_DATASETS = [
    ("2016-17", "https://data.wa.gov/resource/ef3e-qpb8.csv"),
    ("2018-19", "https://data.wa.gov/resource/6iji-4nux.csv"),
    ("2019-20", "https://data.wa.gov/resource/gges-4vcv.csv"),
    ("2020-21", "https://data.wa.gov/resource/rrud-rd4u.csv"),
    ("2021-22", "https://data.wa.gov/resource/i23g-ymbg.csv"),
    ("2022-23", "https://data.wa.gov/resource/kigx-4b2d.csv"),
    ("2023-24", "https://data.wa.gov/resource/76iv-8ed4.csv"),
]

# Student Growth Percentile datasets — median SGP at school/subject/All-Grades level.
# Not available 2019-20 through 2021-22 (COVID cancelled testing / OSPI stopped publishing).
SGP_DATASETS = [
    ("2014-15", "https://data.wa.gov/resource/7na8-mwsc.csv"),
    ("2015-16", "https://data.wa.gov/resource/4rjj-n636.csv"),
    ("2016-17", "https://data.wa.gov/resource/x7f4-cm3f.csv"),
    ("2017-18", "https://data.wa.gov/resource/ekki-gi8u.csv"),
    ("2018-19", "https://data.wa.gov/resource/uj4q-wr8d.csv"),
    ("2022-23", "https://data.wa.gov/resource/jum2-3mgi.csv"),
    ("2023-24", "https://data.wa.gov/resource/cxts-amj6.csv"),
    ("2024-25", "https://data.wa.gov/resource/hv7j-ib7g.csv"),
]

_SOCRATA_LIMIT = "?$limit=5000000"

# Canonical district names used as filter (values from TARGET_DISTRICT_NAME_MAP)
_TARGET_DISTRICTS = set(TARGET_DISTRICT_NAME_MAP.values())

# Generic words removed from token comparison so only distinctive words drive the match.
# The exact (primary) join is unaffected; stop words only filter the fallback scoring.
_STOP_WORDS = frozenset({
    "school", "schools", "academy", "academies",
    "community", "elementary", "middle", "high", "junior",
    "senior", "primary", "secondary", "stem", "steam",
    "the", "a", "an", "of", "at", "and", "for", "in",
})


def _norm_name(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _parse_pct_string(raw: str | None) -> float | None:
    """Parse a proficiency string like '73.5%' or '0.4' into a 0-1 float.

    Returns None for suppressed/missing values.
    """
    if raw is None or raw.strip() in ("", "*", "NULL"):
        return None
    s = raw.strip()
    # Patterns like "Suppressed: N<10", "<10%"
    if "Suppressed" in s or s.startswith("<"):
        return None
    s = s.rstrip("%")
    try:
        value = float(s)
    except ValueError:
        return None
    # Values > 1 are percentages (0-100 scale); normalise to 0-1
    if value > 1:
        return value / 100.0
    return value


def _parse_sgp(raw: str, datreason: str = "") -> int | None:
    """Parse a median SGP value into an integer 1–99, or None if suppressed."""
    if datreason and datreason.strip() not in ("", "NULL"):
        return None
    if raw is None or raw.strip() in ("", "*", "NULL", "N/A"):
        return None
    try:
        return round(float(raw))
    except ValueError:
        return None


def _proficiency_value(row: dict[str, str]) -> float | None:
    # 2022-23 schema
    raw = row.get("percent_consistent_grade_level_knowledge_and_above")
    # 2024-25 schema (column renamed)
    if raw is None:
        raw = row.get("percent_consistent_grade")
    # pre-2022-23 schema
    if raw is None:
        raw = row.get("percentmetstandard")
    return _parse_pct_string(raw)


_ASSESSMENT_WHERE = (
    "organizationlevel='School'"
    " AND studentgrouptype='All'"
    " AND gradelevel='All Grades'"
)
_GRADUATION_WHERE = (
    "organizationlevel='School'"
    " AND studentgrouptype='All'"
    " AND cohort='Four Year'"
)
# SGP uses 'AllStudents' (no space) unlike assessment which uses 'All'
_SGP_WHERE = (
    "organizationlevel='School'"
    " AND studentgrouptype='AllStudents'"
    " AND gradelevel='All Grades'"
)
_ABSENTEEISM_WHERE = (
    "organizationlevel='School'"
    " AND studentgrouptype='All'"
)
# Discipline: filter to short-term out-of-school suspensions only.
# DataLabel value verified by probe_ospi_schemas.py — update if probe shows a different string.
_SUSPENSION_LABEL = "Short-Term Out-of-School Suspension Rate"
_DISCIPLINE_WHERE = (
    "organizationlevel='School'"
    " AND studentgrouptype='All'"
    f" AND datalabel='{_SUSPENSION_LABEL}'"
)
# Language dataset is one row per language per school — no studentgrouptype filter.
_LANGUAGE_WHERE = "organizationlevel='School'"
# English row identifier — skip when aggregating non-English share.
_ENGLISH_LANGUAGE_NAMES = frozenset({"English", "ENGLISH", "english"})


def _absenteeism_value(row: dict[str, str]) -> float | None:
    """Extract chronic absenteeism rate, trying multiple known column name variants."""
    # Try most-likely OSPI Report Card generic column first, then dataset-specific names.
    for col in ("percentagevalue", "chronicabsenteeismrate", "percentageabsent",
                "chronicabsent", "percentchronic"):
        raw = row.get(col)
        if raw is not None:
            return _parse_pct_string(raw)
    # Log actual columns so CI output reveals the correct name.
    value_cols = [k for k in row if any(t in k.lower() for t in ("percent", "rate", "absent", "value"))]
    if value_cols:
        print(f"  WARNING: chronic absenteeism — unexpected columns, found: {value_cols[:8]}", file=sys.stderr)
    return None


def _suspension_value(row: dict[str, str]) -> float | None:
    """Extract out-of-school suspension rate, trying multiple column name variants."""
    for col in ("percentagevalue", "suspensionrate", "datavalue", "rate", "percentvalue"):
        raw = row.get(col)
        if raw is not None:
            return _parse_pct_string(raw)
    value_cols = [k for k in row if any(t in k.lower() for t in ("percent", "rate", "suspend", "value"))]
    if value_cols:
        print(f"  WARNING: discipline — unexpected columns, found: {value_cols[:8]}", file=sys.stderr)
    return None


def _language_is_english(row: dict[str, str]) -> bool:
    """Return True if this row represents English speakers."""
    for col in ("primarylanguage", "languagename", "language", "homelanguage"):
        val = row.get(col, "")
        if val:
            return val.strip() in _ENGLISH_LANGUAGE_NAMES
    return False


def _language_student_count(row: dict[str, str]) -> int | None:
    """Extract student count from a language row."""
    for col in ("studentcount", "count", "students", "numberofstudents", "student_count"):
        raw = row.get(col)
        if raw is not None:
            try:
                return int(float(raw))
            except (ValueError, TypeError):
                return None
    return None


def _fetch_csv(url: str, where: str = "") -> list[dict[str, str]]:
    params = _SOCRATA_LIMIT
    if where:
        params += "&$where=" + urllib.parse.quote(where)
    full_url = url + params
    with urllib.request.urlopen(full_url, timeout=120) as resp:
        data = resp.read().decode("utf-8")
    return list(csv.DictReader(io.StringIO(data)))


def _build_name_index(
    schools: list[dict],
) -> tuple[dict[tuple[str, str], str], dict[str, list[tuple[str, str, str]]]]:
    """Return (exact_index, district_tokens_index).

    exact_index: (norm_district, norm_school) -> school_id
    district_tokens_index: norm_district -> [(school_id, norm_name, tokens_frozenset)]
    """
    exact: dict[tuple[str, str], str] = {}
    by_district: dict[str, list[tuple[str, str, frozenset]]] = {}
    for school in schools:
        sid = school["id"]
        nd = _norm_name(school["district_name"])
        ns = _norm_name(school["name"])
        exact[(nd, ns)] = sid
        content_tokens = frozenset(t for t in ns.split() if t not in _STOP_WORDS)
        by_district.setdefault(nd, []).append((sid, ns, content_tokens))
    return exact, by_district


def _lookup_school_id(
    district_name: str,
    school_name: str,
    exact: dict,
    by_district: dict,
) -> str | None:
    nd = _norm_name(district_name)
    ns = _norm_name(school_name)
    sid = exact.get((nd, ns))
    if sid:
        return sid
    candidates = by_district.get(nd, [])
    if not candidates:
        return None
    tokens_q = frozenset(t for t in ns.split() if t not in _STOP_WORDS)
    best_score = 0.0
    best_sid = None
    for cand_sid, cand_ns, cand_tokens in candidates:
        denom = max(len(tokens_q), len(cand_tokens))
        if denom == 0:
            continue
        score = len(tokens_q & cand_tokens) / denom
        if score > best_score:
            best_score = score
            best_sid = cand_sid
    if best_score >= 0.80:
        return best_sid
    return None


def _expand_year(short: str) -> str:
    """Convert OSPI short year '2023-24' to NCES full year '2023-2024'."""
    parts = short.split("-")
    if len(parts) == 2 and len(parts[1]) == 2:
        start = int(parts[0])
        end_short = int(parts[1])
        # End year is always start+1; derive century from that
        end_full = (start + 1) // 100 * 100 + end_short
        return f"{parts[0]}-{end_full}"
    return short


def _norm_district(raw: str) -> str | None:
    """Return canonical district name if raw district is in target list, else None."""
    return TARGET_DISTRICT_NAME_MAP.get(raw) or (raw if raw in _TARGET_DISTRICTS else None)


def load_overrides(project_root: Path) -> dict[tuple[str, str], str]:
    """Load manual school-name overrides from data/ospi_overrides.csv.

    Each row: ospi_district, ospi_school, nces_school_id
    Returns {(norm_district, norm_school): nces_school_id}.
    """
    path = project_root / "data" / "ospi_overrides.csv"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return {
            (_norm_name(row["ospi_district"]), _norm_name(row["ospi_school"])): row["nces_school_id"]
            for row in csv.DictReader(f)
        }


def fetch_ospi_metrics(
    schools: list[dict],
    project_root: Path | None = None,
) -> dict[tuple[str, str], dict[str, float | None]]:
    """Download and join OSPI assessment and graduation data.

    Returns a dict keyed by (nces_school_id, year_label) mapping to metric values.
    Pass project_root to load manual overrides from data/ospi_overrides.csv.
    """
    overrides = load_overrides(project_root) if project_root else {}
    exact, by_district = _build_name_index(schools)

    def _resolve_school_id(canonical: str, school_name: str) -> str | None:
        key = (_norm_name(canonical), _norm_name(school_name))
        return overrides.get(key) or _lookup_school_id(canonical, school_name, exact, by_district)

    # key: (school_id, year) -> {ela_proficiency_rate, math_proficiency_rate, four_year_grad_rate}
    result: dict[tuple[str, str], dict[str, float | None]] = {}
    unmatched: set[tuple[str, str]] = set()

    def _get_or_create(sid: str, year: str) -> dict[str, float | None]:
        key = (sid, year)
        if key not in result:
            result[key] = {}
        return result[key]

    for _label, url in ASSESSMENT_DATASETS:
        print(f"Fetching assessment data: {url}", file=sys.stderr)
        try:
            rows = _fetch_csv(url, _ASSESSMENT_WHERE)
        except Exception as exc:
            print(f"  WARNING: failed to fetch {url}: {exc}", file=sys.stderr)
            continue

        for row in rows:
            raw_district = row.get("districtname", "")
            canonical = _norm_district(raw_district)
            if not canonical:
                continue

            school_name = row.get("schoolname", "")
            sid = _resolve_school_id(canonical, school_name)
            if not sid:
                unmatched.add((canonical, school_name))
                continue

            year = _expand_year(row.get("schoolyear", ""))
            subject = row.get("testsubject", "")
            value = _proficiency_value(row)

            entry = _get_or_create(sid, year)
            if subject == "ELA":
                entry["ela_proficiency_rate"] = value
            elif subject == "Math":
                entry["math_proficiency_rate"] = value

    for _label, url in GRADUATION_DATASETS:
        print(f"Fetching graduation data: {url}", file=sys.stderr)
        try:
            rows = _fetch_csv(url, _GRADUATION_WHERE)
        except Exception as exc:
            print(f"  WARNING: failed to fetch {url}: {exc}", file=sys.stderr)
            continue

        for row in rows:
            raw_district = row.get("districtname", "")
            canonical = _norm_district(raw_district)
            if not canonical:
                continue

            school_name = row.get("schoolname", "")
            sid = _resolve_school_id(canonical, school_name)
            if not sid:
                unmatched.add((canonical, school_name))
                continue

            year = _expand_year(row.get("schoolyear", ""))
            raw_rate = row.get("graduationrate", "")
            rate = _parse_pct_string(raw_rate)

            entry = _get_or_create(sid, year)
            entry["four_year_grad_rate"] = rate

    for _label, url in SGP_DATASETS:
        print(f"Fetching SGP data: {url}", file=sys.stderr)
        try:
            rows = _fetch_csv(url, _SGP_WHERE)
        except Exception as exc:
            print(f"  WARNING: failed to fetch {url}: {exc}", file=sys.stderr)
            continue

        for row in rows:
            raw_district = row.get("districtname", "")
            canonical = _norm_district(raw_district)
            if not canonical:
                continue

            school_name = row.get("schoolname", "")
            sid = _resolve_school_id(canonical, school_name)
            if not sid:
                unmatched.add((canonical, school_name))
                continue

            year = _expand_year(row.get("schoolyear", ""))
            subject = row.get("subject", "")
            sgp = _parse_sgp(row.get("mediansgp", ""), row.get("datreason", row.get("suppression", "")))

            entry = _get_or_create(sid, year)
            if subject == "English Language Arts":
                entry["ela_growth_percentile"] = sgp
            elif subject == "Math":
                entry["math_growth_percentile"] = sgp

    if unmatched:
        for district, school in sorted(unmatched):
            print(f"  UNMATCHED OSPI school: {district!r} / {school!r}", file=sys.stderr)

    return result


def fetch_new_metrics(
    schools: list[dict],
    project_root: Path | None = None,
) -> dict[tuple[str, str], dict[str, float | None]]:
    """Download chronic absenteeism, discipline, EL share, and language data.

    Returns {(school_id, year): {metric_key: value}}.
    Each metric is absent from the dict (not None) if its dataset list is empty.
    """
    overrides = load_overrides(project_root) if project_root else {}
    exact, by_district = _build_name_index(schools)

    def _resolve(canonical: str, school_name: str) -> str | None:
        key = (_norm_name(canonical), _norm_name(school_name))
        return overrides.get(key) or _lookup_school_id(canonical, school_name, exact, by_district)

    result: dict[tuple[str, str], dict[str, float | None]] = {}
    unmatched: set[tuple[str, str]] = set()

    def _entry(sid: str, year: str) -> dict:
        return result.setdefault((sid, year), {})

    # ── Chronic absenteeism ──────────────────────────────────────────────────
    for _label, url in CHRONIC_ABSENTEEISM_DATASETS:
        print(f"Fetching chronic absenteeism data: {url}", file=sys.stderr)
        try:
            rows = _fetch_csv(url, _ABSENTEEISM_WHERE)
        except Exception as exc:
            print(f"  WARNING: failed to fetch {url}: {exc}", file=sys.stderr)
            continue
        for row in rows:
            canonical = _norm_district(row.get("districtname", ""))
            if not canonical:
                continue
            sid = _resolve(canonical, row.get("schoolname", ""))
            if not sid:
                unmatched.add((canonical, row.get("schoolname", "")))
                continue
            year = _expand_year(row.get("schoolyear", ""))
            value = _absenteeism_value(row)
            _entry(sid, year)["chronic_absentee_rate"] = value

    # ── Discipline (short-term out-of-school suspension) ─────────────────────
    for _label, url in DISCIPLINE_DATASETS:
        print(f"Fetching discipline data: {url}", file=sys.stderr)
        try:
            rows = _fetch_csv(url, _DISCIPLINE_WHERE)
        except Exception as exc:
            print(f"  WARNING: failed to fetch {url}: {exc}", file=sys.stderr)
            continue
        for row in rows:
            canonical = _norm_district(row.get("districtname", ""))
            if not canonical:
                continue
            sid = _resolve(canonical, row.get("schoolname", ""))
            if not sid:
                unmatched.add((canonical, row.get("schoolname", "")))
                continue
            year = _expand_year(row.get("schoolyear", ""))
            value = _suspension_value(row)
            _entry(sid, year)["suspension_rate"] = value

    # ── English Learner share ─────────────────────────────────────────────────
    for _label, url in ENGLISH_LEARNER_DATASETS:
        print(f"Fetching English Learner data: {url}", file=sys.stderr)
        try:
            rows = _fetch_csv(url, _ABSENTEEISM_WHERE)
        except Exception as exc:
            print(f"  WARNING: failed to fetch {url}: {exc}", file=sys.stderr)
            continue
        for row in rows:
            canonical = _norm_district(row.get("districtname", ""))
            if not canonical:
                continue
            sid = _resolve(canonical, row.get("schoolname", ""))
            if not sid:
                unmatched.add((canonical, row.get("schoolname", "")))
                continue
            year = _expand_year(row.get("schoolyear", ""))
            value = _absenteeism_value(row)  # same percent column pattern
            _entry(sid, year)["english_learner_share"] = value

    # ── Non-English home language share ──────────────────────────────────────
    # Language dataset is one row per language per school; aggregate here.
    lang_totals: dict[tuple[str, str], tuple[int, int]] = {}  # (sid, year) -> (non_eng, total)
    for _label, url in LANGUAGE_DATASETS:
        print(f"Fetching language data: {url}", file=sys.stderr)
        try:
            rows = _fetch_csv(url, _LANGUAGE_WHERE)
        except Exception as exc:
            print(f"  WARNING: failed to fetch {url}: {exc}", file=sys.stderr)
            continue
        for row in rows:
            canonical = _norm_district(row.get("districtname", ""))
            if not canonical:
                continue
            sid = _resolve(canonical, row.get("schoolname", ""))
            if not sid:
                unmatched.add((canonical, row.get("schoolname", "")))
                continue
            year = _expand_year(row.get("schoolyear", ""))
            count = _language_student_count(row)
            if count is None or count < 0:
                continue
            is_eng = _language_is_english(row)
            key = (sid, year)
            non_eng, total = lang_totals.get(key, (0, 0))
            lang_totals[key] = (non_eng + (0 if is_eng else count), total + count)

    for (sid, year), (non_eng, total) in lang_totals.items():
        share = non_eng / total if total > 0 else None
        _entry(sid, year)["non_english_home_language_share"] = share

    if unmatched:
        for district, school in sorted(unmatched):
            print(f"  UNMATCHED new-metric school: {district!r} / {school!r}", file=sys.stderr)

    return result
