# Seattle Area School Dashboard

A static dashboard tracking school performance trends across 11 Puget Sound districts, built on
public data from National Center for Education Statistics (NCES) and Washington Office of Superintendent of Public Instruction (OSPI). 

## Districts

Bainbridge Island · Bellevue · Central Kitsap · Issaquah · Lake Washington · Mercer Island ·
North Kitsap · Renton · Seattle · Snoqualmie Valley · Vashon Island

## Metrics

| Metric | Source | Notes |
|--------|--------|-------|
| Enrollment | NCES CCD | Student count, adult ed excluded |
| Demographics | NCES CCD | Race/ethnicity, FRPL share, English learners |
| ELA Proficiency | OSPI | Share meeting standard |
| Math Proficiency | OSPI | Share meeting standard |
| ELA Growth (SGP) | OSPI | Student growth percentile; 50 = typical |
| Math Growth (SGP) | OSPI | Student growth percentile; 50 = typical |
| Graduation Rate | OSPI | 4-year cohort, high schools only |

**Known gaps:** Assessment and graduation data are absent for 2019-20 and 2020-21 (COVID —
statewide testing cancelled). OSPI school name matching uses an 80% token-overlap threshold;
a small number of schools may be unmatched.

## Architecture

```
NCES CCD API  ─┐
OSPI Socrata   ─┴─► src/seattle_schools_dashboard/  ─► site/dashboard-data.json
                         Python pipeline                      │
                                                        Chart.js frontend
                                                        site/index.html
```

The pipeline downloads, normalizes, and joins NCES enrollment/demographics with OSPI assessment,
graduation, and growth data. A PCA-based composite ranking is computed separately
(`scripts/generate_pca_report.py`) and output to `site/pca-analysis.html`. Raw NCES downloads
are temporary and never committed. The `site/` output is rebuilt by CI and not tracked in git.

## Layout

```
.github/workflows/    CI/CD and Pages deployment
scripts/              Build entry points
site/                 Generated output (gitignored; rebuilt by CI)
src/                  Python package — data collection, normalization, rankings
tests/                Unit tests
```

## Local development

```bash
pip install -e .[dev]
python -m unittest discover -s tests
python scripts/build_dashboard.py      # writes to site/
```

## Deployment

GitHub Actions (`.github/workflows/build-and-deploy.yml`) runs on push to `main`, on manual
dispatch, and on a weekly Monday schedule. It runs tests, builds the site, and deploys to
GitHub Pages.
