# Technical Specification: Seattle Area School Dashboard

## 1. Purpose

Build a public-facing school performance dashboard for Seattle-area schools and adjacent configured regions. The site will be deployed on GitHub Pages and refreshed through GitHub Actions. A Python data pipeline will download, normalize, test, and publish educational data sourced from the National Center for Education Statistics (NCES).

## 2. Product Goals

- Allow the public to explore school-level trends over time.
- Support selection by individual school and by school district using checkboxes.
- Show 5-year and 10-year metric trends using line charts.
- Provide a resilient data pipeline that can withstand NCES file and schema changes.
- Keep hosting and deployment simple enough for a small maintenance footprint.

## 3. Scope

### In Scope

- Public static dashboard hosted on GitHub Pages
- Python pipeline for NCES download, validation, normalization, and site-ready exports
- Unit tests for download and transformation logic
- GitHub Actions workflow for test, build, and deployment
- Configurable school and district scope for the Seattle area

### Out of Scope for v1

- User accounts
- Server-side filtering APIs
- Real-time data updates
- School comparison scoring beyond raw and normalized trend displays

## 4. Geographic Scope

The project should support configuration-driven inclusion of districts. The initial district set includes:

- Seattle
- Bellevue
- Renton
- Issaquah
- Snoqualmie Valley
- Lake Washington
- Mercer Island
- Bainbridge Island
- North Kitsap
- Central Kitsap
- Vashon Island

The initial release should stay focused on the Puget Sound core districts listed above. Olympic Peninsula districts are out of scope for v1.

## 5. Data Sources

Primary source:

- NCES public datasets and related metadata definitions

Likely source categories:

- Common Core of Data directory and school universe files
- Assessment or academic performance files where publicly available
- Graduation and enrollment trend data where available and legally publishable

## 6. Core Metrics for v1

The starter implementation assumes these canonical metric groups:

- Enrollment
- Demographics
- Proficiency
- Graduation

Recommended canonical metrics within those groups:

- `enrollment`
- Race and ethnicity composition fields
- English learner share, if consistently available
- Economically disadvantaged share, if consistently available
- `math_proficiency`
- `reading_proficiency`
- `graduation_rate`

The pipeline must mark any metric as unavailable when source coverage is inconsistent, rather than silently mixing incompatible definitions.

## 7. Functional Requirements

### 7.1 Selection UX

- Users can select one or more districts with checkboxes.
- Users can select one or more schools with checkboxes.
- District and school selections must remain fully synced.
- Checking a district should check all schools in that district.
- Unchecking a district should uncheck all schools in that district.
- If every school in a district is checked individually, the district checkbox should appear checked.
- The UI should make selected school counts visible.
- Users should be able to clear all selections quickly.
- The dashboard must include all school levels in v1.
- The dashboard should not group schools by school level in the selection UI.

### 7.2 Trends

- Users can switch between 5-year and 10-year windows.
- The starter recommendation is a single chart area with a time-range toggle.
- Each chart should show yearly values for the selected metric.
- Multiple schools may appear on the same chart for comparison.
- Charts should clearly show missing years instead of interpolating hidden values.

### 7.3 Filtering and State

- The dashboard should preserve current selections in the URL query string when feasible.
- The interface should remain usable on desktop and mobile widths.

## 8. Non-Functional Requirements

- Static-site architecture only
- GitHub Pages compatible output
- Reproducible builds
- Strong unit test coverage for normalization and schema mapping
- Graceful handling of missing or changed columns in NCES extracts

## 9. Architecture

### 9.1 Overview

The system has three layers:

1. Data ingestion and normalization in Python
2. Static artifact generation into JSON files and HTML assets
3. Client-side rendering with Chart.js and plain JavaScript

### 9.2 Proposed Repository Structure

```text
.github/workflows/
docs/
scripts/
site/
src/seattle_schools_dashboard/
tests/
```

### 9.3 Pipeline Stages

1. Download raw NCES source files
2. Validate file presence and expected base structure
3. Normalize source-specific columns into canonical field names
4. Validate metric definitions and year compatibility
5. Filter records to configured districts and schools
6. Export compact JSON payloads for the frontend
7. Render static HTML entry point

## 10. Canonical Schema Strategy

To keep naming and definitions stable across years, the pipeline should implement:

- A canonical field dictionary keyed by business meaning, not source column names
- Per-year or per-source mapping rules from raw columns to canonical fields
- Validation rules that fail loudly when a required canonical field cannot be constructed
- Metadata tracking for each metric indicating source, year range, and confidence level

Example canonical fields:

- `school_id`
- `district_id`
- `district_name`
- `school_name`
- `school_level`
- `year`
- `enrollment`
- `graduation_rate`
- `math_proficiency`
- `reading_proficiency`

## 11. Testing Strategy

Unit tests should cover:

- Column mapping from raw NCES headers to canonical names
- Handling of renamed or missing columns
- District and region filtering
- Trend output generation
- Site build output creation

Test fixtures should include multiple synthetic yearly schemas to simulate NCES format drift.

## 12. Frontend Implementation

### 12.1 Stack

- Plain HTML
- Plain CSS
- Plain JavaScript
- Chart.js for trend charts

This is the recommended frontend approach for v1 because it keeps GitHub Pages deployment simple and reduces maintenance overhead while still supporting checkbox-driven filtering and trend rendering.

### 12.2 UI Components

- District checkbox panel
- School checkbox panel
- Metric selector
- Time-range selector for 5-year and 10-year views
- One or more line charts
- Summary text for active selections and missing data caveats

School lists should appear as a flat selectable list scoped by chosen districts rather than grouped by elementary, middle, or high school categories.

## 13. Deployment and Automation

### 13.1 GitHub Actions

The repository should include a workflow that:

1. Runs on push to `main`, manual dispatch, and a schedule
2. Sets up Python
3. Installs dependencies
4. Runs unit tests
5. Executes the dashboard build script
6. Uploads the generated static site artifact
7. Deploys to GitHub Pages

### 13.2 GitHub Pages

- The published output should come from the generated `site/` directory
- Deployment should use the official Pages artifact and deploy actions

## 14. Risks and Mitigations

- NCES schema drift
  - Mitigation: canonical mapping layer and failing validation
- Incomplete metric coverage across years
  - Mitigation: metric-level availability metadata and explicit chart gaps
- Regional scope ambiguity
  - Mitigation: configuration-based district sets and named regions

## 15. Delivery Plan

### Phase 1

- Establish repo skeleton
- Implement schema model and tests
- Add placeholder site generation and CI

### Phase 2

- Integrate live NCES downloads
- Expand metric normalization
- Build checkbox-driven dashboard interactions

### Phase 3

- Improve UX polish
- Add documentation for data refresh and maintenance
- Tune scheduled refresh cadence
