"""Generate site/pca-analysis.html — a per-level EDA + PCA scrutiny report.

Usage:
    python scripts/generate_pca_report.py

Reads  : site/dashboard-data.json
Writes : site/pca-analysis.html
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np

from seattle_schools_dashboard.rankings import (
    METRICS_BY_LEVEL,
    METRIC_LABELS,
    RANKABLE_LEVELS,
    _collect_raw_matrix,
    _run_level_pca,
    _run_pca,
    _select_reference_records,
    _zscore_matrix,
    compute_rankings,
    compute_pca_loadings,
)


def build_report_data(data: dict) -> dict:
    """Run all analyses; return a JSON-serialisable dict."""
    from collections import Counter, defaultdict

    schools = data["schools"]
    records = data["records"]
    school_by_id = {s["id"]: s for s in schools}

    # ----- per-level PCA bundles -----
    level_schools: dict[str, list[dict]] = {lvl: [] for lvl in RANKABLE_LEVELS}
    excluded = []
    for s in schools:
        lvl = s.get("school_level", "")
        if lvl in RANKABLE_LEVELS:
            level_schools[lvl].append(s)
        else:
            excluded.append(s)

    levels_data: dict[str, dict] = {}
    for level in ("Elementary", "Middle", "High"):
        sl = level_schools[level]
        bundle = _run_level_pca(level, sl, records)
        li = bundle["loadings"]
        rankings = bundle["rankings"]

        # Score distribution
        score_vals = sorted(info["composite_score"] for info in rankings.values())
        n = len(score_vals)

        # Completeness buckets
        comp_buckets: dict[str, int] = {"100%": 0, "80-99%": 0, "60-79%": 0, "<60%": 0}
        for info in rankings.values():
            dc = info["data_completeness"] * 100
            if dc == 100:
                comp_buckets["100%"] += 1
            elif dc >= 80:
                comp_buckets["80-99%"] += 1
            elif dc >= 60:
                comp_buckets["60-79%"] += 1
            else:
                comp_buckets["<60%"] += 1

        # Top / bottom 15
        ranked_list = sorted(rankings.items(), key=lambda x: x[1]["overall_rank"])
        top15 = [
            {
                "rank": info["overall_rank"],
                "id": sid,
                "name": school_by_id.get(sid, {}).get("name", sid),
                "district": school_by_id.get(sid, {}).get("district_name", ""),
                "score": info["composite_score"],
                "overall_pct": info["overall_percentile"],
                "district_rank": info["district_rank"],
                "district_total": info["district_total"],
                "completeness": info["data_completeness"],
                "year": info["reference_year"],
            }
            for sid, info in ranked_list[:15]
        ]
        bot15 = [
            {
                "rank": info["overall_rank"],
                "id": sid,
                "name": school_by_id.get(sid, {}).get("name", sid),
                "district": school_by_id.get(sid, {}).get("district_name", ""),
                "score": info["composite_score"],
                "overall_pct": info["overall_percentile"],
                "district_rank": info["district_rank"],
                "district_total": info["district_total"],
                "completeness": info["data_completeness"],
                "year": info["reference_year"],
            }
            for sid, info in ranked_list[-15:]
        ]
        full_table = [
            {
                "rank": info["overall_rank"],
                "id": sid,
                "name": school_by_id.get(sid, {}).get("name", sid),
                "district": school_by_id.get(sid, {}).get("district_name", ""),
                "score": info["composite_score"],
                "overall_pct": info["overall_percentile"],
                "district_rank": info["district_rank"],
                "district_total": info["district_total"],
                "completeness": info["data_completeness"],
                "year": info["reference_year"],
                "raw_inputs": info.get("raw_inputs", {}),
                "z_scores": info.get("z_scores", {}),
            }
            for sid, info in ranked_list
        ]

        yr_counts = Counter(info["reference_year"] for info in rankings.values())

        levels_data[level] = {
            "level": level,
            "n_schools": li["n_schools"],
            "n_schools_total": len(sl),
            "n_excluded_no_data": len(sl) - li["n_schools"],
            "metrics": li["metrics"],
            "metric_labels": li["metric_labels"],
            "pc1_loadings": li["pc1_loadings"],
            "all_loadings": li["all_loadings"],
            "all_var": li["all_var"],
            "variance_explained": li["variance_explained"],
            "means": li["means"],
            "stds": li["stds"],
            "raw_stats": li["raw_stats"],
            "corr": li["corr"],
            "biplot_data": li["biplot_data"],
            "yr_counts": dict(yr_counts),
            "comp_buckets": comp_buckets,
            "score_min": round(score_vals[0], 3) if score_vals else 0,
            "score_max": round(score_vals[-1], 3) if score_vals else 0,
            "score_median": round(score_vals[n // 2], 3) if score_vals else 0,
            "top15": top15,
            "bot15": bot15,
            "full_table": full_table,
        }

    return {
        "levels": levels_data,
        "excluded_count": len(excluded),
        "excluded_levels": dict(Counter(s.get("school_level", "") for s in excluded)),
    }


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PCA Analysis Report &mdash; Seattle Area Schools</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root {
  --bg: #f4efe6;
  --paper: rgba(255,252,246,0.97);
  --ink: #1b2330;
  --muted: #5f6b7a;
  --teal: #0f6c74;
  --rust: #c65a1e;
  --amber: #b87c10;
  --green: #1a7a3f;
  --red: #b03020;
  --border: rgba(27,35,48,0.12);
  --shadow: 0 4px 16px rgba(27,35,48,0.08);
  --elem: #1a7a3f;
  --mid: #004b8d;
  --high: #7a3200;
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: "Trebuchet MS","Avenir Next",sans-serif; background: var(--bg); color: var(--ink); line-height: 1.6; padding-bottom: 60px; }
h1,h2,h3,h4 { font-family: Georgia,"Times New Roman",serif; }
h2 { font-size: 1.25rem; margin-bottom: .75rem; color: var(--teal); }
h3 { font-size: 1rem; margin-bottom: .5rem; }

.topbar { background: var(--teal); color: #fff; padding: 14px 32px; display: flex; align-items: center; gap: 18px; }
.topbar a { color: rgba(255,255,255,.85); text-decoration: none; font-size: .9rem; }
.topbar h1 { font-size: 1.1rem; color: #fff; flex: 1; }

.container { max-width: 1120px; margin: 0 auto; padding: 28px 20px 0; }

/* level tabs */
.tab-bar { display: flex; gap: 0; border-bottom: 2px solid var(--border); margin-bottom: 0; }
.tab-btn {
  padding: 10px 28px; border: none; background: none; cursor: pointer;
  font-family: inherit; font-size: .95rem; color: var(--muted);
  border-bottom: 3px solid transparent; margin-bottom: -2px;
  transition: color .15s;
}
.tab-btn:hover { color: var(--ink); }
.tab-btn.active-elem { color: var(--elem); border-color: var(--elem); font-weight: 700; }
.tab-btn.active-mid  { color: var(--mid);  border-color: var(--mid);  font-weight: 700; }
.tab-btn.active-high { color: var(--high); border-color: var(--high); font-weight: 700; }

.tab-panel { display: none; }
.tab-panel.active { display: block; }

.section {
  background: var(--paper); border-radius: 12px; border: 1px solid var(--border);
  box-shadow: var(--shadow); padding: 22px 26px; margin-bottom: 24px;
}
.section:first-child { border-radius: 0 12px 12px 12px; margin-top: 0; }

.callout { border-left: 4px solid var(--teal); background: rgba(15,108,116,.06); padding: 12px 16px; border-radius: 0 8px 8px 0; margin: 12px 0; font-size: .9rem; }
.callout.warn { border-color: var(--amber); background: rgba(184,124,16,.07); }
.callout.critical { border-color: var(--red); background: rgba(176,48,32,.07); }
.callout.good { border-color: var(--green); background: rgba(26,122,63,.06); }
.callout strong { display: block; margin-bottom: 3px; }

.stat-grid { display: grid; grid-template-columns: repeat(auto-fit,minmax(150px,1fr)); gap: 12px; margin: 14px 0; }
.stat-card { background: rgba(15,108,116,.07); border-radius: 8px; padding: 12px 14px; text-align: center; }
.stat-card .num { font-size: 1.8rem; font-weight: 700; color: var(--teal); line-height: 1.1; }
.stat-card .lbl { font-size: .75rem; color: var(--muted); margin-top: 2px; }

.chart-row { display: grid; grid-template-columns: 1fr 1fr; gap: 22px; margin-top: 14px; }
@media (max-width:720px) { .chart-row { grid-template-columns: 1fr; } }
.chart-wrap { position: relative; height: 260px; }
.chart-wrap-lg { position: relative; height: 340px; }
.chart-lbl { font-size: .78rem; color: var(--muted); margin-bottom: 5px; }

table { width: 100%; border-collapse: collapse; font-size: .85rem; margin-top: 10px; }
th { background: rgba(15,108,116,.1); color: var(--teal); font-weight: 600; text-align: left; padding: 7px 9px; border-bottom: 2px solid var(--border); cursor: pointer; user-select: none; white-space: nowrap; }
th:hover { background: rgba(15,108,116,.18); }
td { padding: 6px 9px; border-bottom: 1px solid var(--border); vertical-align: middle; }
tr:last-child td { border-bottom: none; }
tr:hover td { background: rgba(15,108,116,.03); }
.nr { text-align: right; font-variant-numeric: tabular-nums; }

.pill { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: .7rem; font-weight: 700; letter-spacing: .03em; white-space: nowrap; }
.pill-elem { background: #d4edda; color: var(--elem); }
.pill-mid  { background: #cce5ff; color: var(--mid); }
.pill-high { background: #ffe4cc; color: var(--high); }

.search-box { padding: 7px 11px; border: 1px solid var(--border); border-radius: 6px; font-family: inherit; font-size: .88rem; background: var(--bg); color: var(--ink); width: 100%; max-width: 340px; }
.search-box:focus { outline: 2px solid var(--teal); }

.toc-inner { display: flex; flex-wrap: wrap; gap: 8px; padding: 14px 0 4px; }
.toc-inner a { padding: 5px 13px; background: var(--paper); border: 1px solid var(--border); border-radius: 20px; font-size: .8rem; color: var(--teal); text-decoration: none; }
.toc-inner a:hover { background: rgba(15,108,116,.1); }

.corr-tbl td { text-align: center; width: 90px; padding: 5px 3px; font-size: .78rem; }
.corr-tbl th { text-align: center; font-size: .74rem; padding: 5px 3px; }
</style>
</head>
<body>

<div class="topbar">
  <a href="index.html">&larr; Dashboard</a>
  <h1>PCA Analysis Report &mdash; Per-Level School Rankings Scrutiny</h1>
</div>

<div class="container">

<!-- ===== GLOBAL INTRO ===== -->
<div class="section" style="border-radius:12px;margin-bottom:24px">
  <h2 style="margin-bottom:8px">About this report</h2>
  <p style="font-size:.92rem;color:var(--muted)">
    Schools are now ranked <strong>within their own level</strong> (Elementary, Middle, High) using
    separate PCAs. Elementary and Middle schools use 4 metrics (ELA/Math proficiency + growth).
    High schools use all 5 (including real graduation rates). Other and Prekindergarten schools
    are excluded from rankings.
  </p>
  <div id="global-stats" class="stat-grid" style="margin-top:16px"></div>
  <p id="excluded-note" style="font-size:.8rem;color:var(--muted);margin-top:8px"></p>
</div>

<!-- ===== LEVEL TABS ===== -->
<div class="tab-bar">
  <button class="tab-btn" data-level="Elementary" onclick="switchTab('Elementary')">&#127793; Elementary</button>
  <button class="tab-btn" data-level="Middle"     onclick="switchTab('Middle')">&#128218; Middle</button>
  <button class="tab-btn" data-level="High"       onclick="switchTab('High')">&#127891; High</button>
</div>

<div id="tab-Elementary" class="tab-panel"><!-- filled by JS --></div>
<div id="tab-Middle"     class="tab-panel"><!-- filled by JS --></div>
<div id="tab-High"       class="tab-panel"><!-- filled by JS --></div>

</div><!-- /container -->

<script>
const R = __REPORT_DATA__;

// ---- helpers ----
const $ = id => document.getElementById(id);
const fmt3 = v => v == null ? '—' : v.toFixed(3);
const fmt4 = v => v == null ? '—' : v.toFixed(4);

const LEVEL_COLOR = { Elementary:'#1a7a3f', Middle:'#004b8d', High:'#7a3200' };
const LEVEL_BG    = { Elementary:'rgba(26,122,63,.65)', Middle:'rgba(0,75,141,.65)', High:'rgba(122,50,0,.65)' };
const LEVEL_PILL  = { Elementary:'elem', Middle:'mid', High:'high' };

// ---- Global stats ----
const totals = Object.values(R.levels).map(l => l.n_schools);
$('global-stats').innerHTML = [
  { num: totals.reduce((a,b)=>a+b,0), lbl: 'Schools ranked' },
  { num: R.levels.Elementary.n_schools, lbl: 'Elementary' },
  { num: R.levels.Middle.n_schools,     lbl: 'Middle' },
  { num: R.levels.High.n_schools,       lbl: 'High' },
  { num: R.excluded_count, lbl: 'Excluded (Other/Pre-K)' },
].map(s => `<div class="stat-card"><div class="num">${s.num}</div><div class="lbl">${s.lbl}</div></div>`).join('');

const exParts = Object.entries(R.excluded_levels).map(([k,v])=>`${k} (${v})`).join(', ');
$('excluded-note').textContent = `Excluded from rankings: ${exParts}.`;

// ---- Build a tab panel for one level ----
const chartRegistry = {};   // level -> list of Chart instances to destroy on re-render

function corrColor(v) {
  if (v >= 0.7) return '#c8eed4';
  if (v >= 0.4) return '#e6f6ea';
  if (v <= -0.5) return '#fcd9d4';
  if (v <= -0.3) return '#fdf0ee';
  return '#f5f5f0';
}

function buildTabPanel(level) {
  const L = R.levels[level];
  const col = LEVEL_COLOR[level];
  const pill = LEVEL_PILL[level];
  const metricsCount = L.metrics.length;
  const isHigh = level === 'High';

  // sorted table data
  const tableData = L.full_table.slice().sort((a,b)=>a.rank-b.rank);

  const html = `
  <div class="section" style="border-top-left-radius:0;border-top-right-radius:0;border-top:none">
    <div class="toc-inner">
      <a href="#${level}-overview">Overview</a>
      <a href="#${level}-coverage">Coverage</a>
      <a href="#${level}-distributions">Distributions</a>
      <a href="#${level}-corr">Correlations</a>
      <a href="#${level}-pca">PCA</a>
      <a href="#${level}-scrutiny">Scrutiny</a>
      <a href="#${level}-top">Top/Bottom 15</a>
      <a href="#${level}-biplot">Biplot</a>
      <a href="#${level}-table">Full Table</a>
    </div>
  </div>

  <!-- OVERVIEW -->
  <div class="section" id="${level}-overview">
    <h2>Overview &mdash; ${level} Schools</h2>
    <div class="stat-grid" id="${level}-stat-grid"></div>
    <div class="callout" id="${level}-refyear-note" style="margin-top:12px"></div>
    ${isHigh ? '' : `<div class="callout good"><strong>&#10003; Clean metric set for ${level} schools</strong>
      This level uses 4 metrics (ELA/Math proficiency + ELA/Math growth) with no
      cross-level imputation issues. All schools in this pool are genuinely comparable.</div>`}
    ${isHigh ? `<div class="callout good"><strong>&#10003; High schools use real graduation rates</strong>
      Now that grad rate is only computed within the High school pool, all values are
      observed (no 0.0 imputation). The PC1 loading should be meaningfully positive.</div>` : ''}
  </div>

  <!-- COVERAGE -->
  <div class="section" id="${level}-coverage">
    <h2>Data Coverage</h2>
    <table>
      <thead><tr>
        <th>Metric</th><th class="nr">Observed</th><th class="nr">Missing</th>
        <th class="nr">Coverage</th><th>Note on nulls</th>
      </tr></thead>
      <tbody id="${level}-cov-body"></tbody>
    </table>
    <div class="stat-grid" style="margin-top:16px" id="${level}-comp-grid"></div>
  </div>

  <!-- DISTRIBUTIONS -->
  <div class="section" id="${level}-distributions">
    <h2>Metric Distributions &amp; Z-Score Transformation</h2>
    <p style="font-size:.85rem;color:var(--muted);margin-bottom:10px">
      Z-scores are computed from observed values only. Schools with a missing metric receive
      z&nbsp;=&nbsp;0 (the mean) and are flagged as partial data.
    </p>
    <table>
      <thead><tr>
        <th>Metric</th>
        <th class="nr">Raw mean</th><th class="nr">Raw std</th>
        <th class="nr">Raw min</th><th class="nr">Raw max</th>
        <th class="nr">Z min</th><th class="nr">Z max</th>
        <th class="nr">Z std (all)</th>
      </tr></thead>
      <tbody id="${level}-dist-body"></tbody>
    </table>
    <div class="chart-row">
      <div>
        <div class="chart-lbl">Raw metric ranges</div>
        <div class="chart-wrap"><canvas id="${level}-rawChart"></canvas></div>
      </div>
      <div>
        <div class="chart-lbl">Z-score ranges after transformation</div>
        <div class="chart-wrap"><canvas id="${level}-zChart"></canvas></div>
      </div>
    </div>
  </div>

  <!-- CORRELATIONS -->
  <div class="section" id="${level}-corr">
    <h2>Inter-Metric Correlations (z-scored data)</h2>
    <p style="font-size:.85rem;color:var(--muted);margin-bottom:10px">
      High correlations between metrics motivate PCA. Ideally, all metrics point in the
      same direction (positive correlations).
    </p>
    <div style="overflow-x:auto"><table class="corr-tbl" id="${level}-corr-table"></table></div>
    <div id="${level}-corr-note" class="callout" style="margin-top:12px"></div>
  </div>

  <!-- PCA RESULTS -->
  <div class="section" id="${level}-pca">
    <h2>PCA Results</h2>
    <div class="chart-row">
      <div>
        <div class="chart-lbl">Scree plot &mdash; variance explained per PC</div>
        <div class="chart-wrap"><canvas id="${level}-screeChart"></canvas></div>
      </div>
      <div>
        <div class="chart-lbl">PC1 loadings (contribution of each metric to composite score)</div>
        <div class="chart-wrap"><canvas id="${level}-loadingsChart"></canvas></div>
      </div>
    </div>
    <table style="margin-top:18px">
      <thead><tr>
        <th>Metric</th>
        <th class="nr">PC1 loading</th>
        <th class="nr">PC2 loading</th>
        <th>Direction</th>
        <th>Assessment</th>
      </tr></thead>
      <tbody id="${level}-loadings-body"></tbody>
    </table>
  </div>

  <!-- SCRUTINY -->
  <div class="section" id="${level}-scrutiny">
    <h2>&#9888; Scrutiny &amp; Design Observations</h2>
    <div id="${level}-scrutiny-content"></div>
  </div>

  <!-- TOP / BOTTOM 15 -->
  <div class="section" id="${level}-top">
    <h2>Top 15 &amp; Bottom 15 Schools</h2>
    <div class="chart-row">
      <div>
        <h3 style="color:var(--green);margin-bottom:8px">Top 15</h3>
        <table>
          <thead><tr><th>#</th><th>School</th><th>District</th><th class="nr">Score</th><th class="nr">%ile</th><th class="nr">Dist rank</th></tr></thead>
          <tbody id="${level}-top-body"></tbody>
        </table>
      </div>
      <div>
        <h3 style="color:var(--red);margin-bottom:8px">Bottom 15</h3>
        <table>
          <thead><tr><th>#</th><th>School</th><th>District</th><th class="nr">Score</th><th class="nr">%ile</th><th class="nr">Dist rank</th></tr></thead>
          <tbody id="${level}-bot-body"></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- BIPLOT -->
  <div class="section" id="${level}-biplot">
    <h2>PC1 vs PC2 Biplot</h2>
    <p style="font-size:.85rem;color:var(--muted);margin-bottom:10px">
      PC1 (x) = composite score. PC2 (y) captures the next-largest independent variation.
      Hover for school names.
    </p>
    <div class="chart-wrap-lg"><canvas id="${level}-biplot"></canvas></div>
    <div id="${level}-pc2-note" class="callout" style="margin-top:12px"></div>
  </div>

  <!-- FULL TABLE -->
  <div class="section" id="${level}-table">
    <h2>Full Rankings Table &mdash; ${level}</h2>
    <div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;margin-bottom:8px">
      <input type="text" class="search-box" id="${level}-search" placeholder="Filter by school or district..." />
      <label style="font-size:.82rem;color:var(--muted);display:flex;align-items:center;gap:6px;cursor:pointer">
        <input type="checkbox" id="${level}-show-z" style="cursor:pointer">
        Show z-scores instead of raw values
      </label>
    </div>
    <p id="${level}-tbl-count" style="font-size:.78rem;color:var(--muted);margin-bottom:4px"></p>
    <div style="overflow-x:auto">
      <table id="${level}-ranktable">
        <thead>
          <tr>
            <th data-col="rank" rowspan="2">#</th>
            <th data-col="name" rowspan="2">School</th>
            <th data-col="district" rowspan="2">District</th>
            <th class="nr" data-col="score" rowspan="2">Score</th>
            <th class="nr" data-col="overall_pct" rowspan="2">%ile</th>
            <th class="nr" data-col="district_rank" rowspan="2">Dist rank</th>
            <th class="nr" data-col="completeness" rowspan="2">Coverage</th>
            <th id="${level}-inputs-header" colspan="5" style="text-align:center;background:rgba(15,108,116,.06);color:var(--teal);font-size:.78rem;letter-spacing:.04em">INPUT METRICS (raw)</th>
          </tr>
          <tr id="${level}-metric-header-row"></tr>
        </thead>
        <tbody id="${level}-rank-body"></tbody>
      </table>
    </div>
    <p style="font-size:.75rem;color:var(--muted);margin-top:8px">
      Cell colour: <span style="background:rgba(26,122,63,.25);padding:1px 6px;border-radius:3px">green</span> = above pool median &nbsp;
      <span style="background:rgba(176,48,32,.2);padding:1px 6px;border-radius:3px">red</span> = below pool median &nbsp;
      <span style="background:#e4e4e4;padding:1px 6px;border-radius:3px">grey</span> = missing / imputed to mean z=0
    </p>
  </div>
  `;

  $('tab-' + level).innerHTML = html;

  const L2 = R.levels[level];

  // stat grid
  $(`${level}-stat-grid`).innerHTML = [
    { num: L2.n_schools, lbl: 'Schools ranked' },
    { num: (L2.variance_explained * 100).toFixed(1) + '%', lbl: 'PC1 variance explained' },
    { num: L2.comp_buckets['100%'], lbl: 'Full data (all metrics)' },
    { num: L2.n_schools - L2.comp_buckets['100%'], lbl: 'Partial data' },
    { num: Object.keys(L2.yr_counts).length, lbl: 'Reference years' },
  ].map(s => `<div class="stat-card"><div class="num">${s.num}</div><div class="lbl">${s.lbl}</div></div>`).join('');

  // ref year note
  const yrStr = Object.entries(L2.yr_counts).sort((a,b)=>b[1]-a[1]).map(([y,n])=>`${y} (${n})`).join(', ');
  $(`${level}-refyear-note`).innerHTML = `<strong>Reference year distribution:</strong> ${yrStr}`;

  // coverage table
  const covNotes = {
    ela_proficiency_rate: 'Null for suppressed cells (N<10)',
    math_proficiency_rate: 'Null for suppressed cells (N<10)',
    ela_growth_percentile: 'Null when N<10 or not published',
    math_growth_percentile: 'Null when N<10 or not published',
    four_year_grad_rate: 'Null when unreported; only High schools',
  };
  $(`${level}-cov-body`).innerHTML = L2.raw_stats.map(s => {
    const pct = (s.n_observed / s.n_total * 100).toFixed(1);
    const cls = s.n_observed === s.n_total ? 'color:var(--green)' : s.n_observed/s.n_total > 0.7 ? '' : 'color:var(--amber)';
    return `<tr><td><strong>${s.label}</strong></td><td class="nr">${s.n_observed}</td>
      <td class="nr">${s.n_total - s.n_observed}</td>
      <td class="nr" style="${cls};font-weight:600">${pct}%</td>
      <td style="font-size:.78rem;color:var(--muted)">${covNotes[s.key]||''}</td></tr>`;
  }).join('');

  $(`${level}-comp-grid`).innerHTML = Object.entries(L2.comp_buckets).map(([k,v]) => {
    const pct = L2.n_schools ? (v/L2.n_schools*100).toFixed(0) : 0;
    return `<div class="stat-card"><div class="num">${v}</div><div class="lbl">${k} coverage (${pct}%)</div></div>`;
  }).join('');

  // distributions table
  $(`${level}-dist-body`).innerHTML = L2.raw_stats.map(s => {
    const zStdWarn = Math.abs(s.z_std - 1.0) > 0.15 ? 'color:var(--amber);font-weight:700' : '';
    return `<tr><td><strong>${s.label}</strong></td>
      <td class="nr">${fmt3(s.raw_mean)}</td><td class="nr">${fmt3(s.raw_std)}</td>
      <td class="nr">${fmt3(s.raw_min)}</td><td class="nr">${fmt3(s.raw_max)}</td>
      <td class="nr">${fmt3(s.z_min)}</td><td class="nr">${fmt3(s.z_max)}</td>
      <td class="nr" style="${zStdWarn}">${fmt3(s.z_std)}</td></tr>`;
  }).join('');

  // raw range chart
  const initCharts = (level) => {
    if (chartRegistry[level]) { chartRegistry[level].forEach(c => c.destroy()); }
    chartRegistry[level] = [];
    const L = R.levels[level];
    const push = c => chartRegistry[level].push(c);

    push(new Chart($(`${level}-rawChart`), {
      type:'bar',
      data:{ labels: L.metric_labels, datasets:[
        {label:'Min',  data:L.raw_stats.map(s=>s.raw_min), backgroundColor:'rgba(15,108,116,.25)'},
        {label:'Mean', data:L.raw_stats.map(s=>s.raw_mean),backgroundColor:'rgba(15,108,116,.7)'},
        {label:'Max',  data:L.raw_stats.map(s=>s.raw_max), backgroundColor:'rgba(15,108,116,.12)'},
      ]},
      options:{ responsive:true, maintainAspectRatio:false, plugins:{legend:{labels:{font:{size:10}}}},
                scales:{y:{title:{display:true,text:'Raw value'}}} }
    }));

    push(new Chart($(`${level}-zChart`), {
      type:'bar',
      data:{ labels: L.metric_labels, datasets:[
        {label:'Z min',  data:L.raw_stats.map(s=>s.z_min), backgroundColor:'rgba(198,90,30,.35)'},
        {label:'Z mean', data:L.raw_stats.map(s=>s.z_mean),backgroundColor:'rgba(198,90,30,.7)'},
        {label:'Z max',  data:L.raw_stats.map(s=>s.z_max), backgroundColor:'rgba(198,90,30,.12)'},
      ]},
      options:{ responsive:true, maintainAspectRatio:false, plugins:{legend:{labels:{font:{size:10}}}},
                scales:{y:{title:{display:true,text:'Z-score'}}} }
    }));

    // corr table
    const cLabels = L.metric_labels.map(l=>l.replace(/ /g,'<br>'));
    let corrHtml = '<thead><tr><th></th>'+cLabels.map(l=>`<th>${l}</th>`).join('')+'</tr></thead><tbody>';
    L.corr.forEach((row,i) => {
      corrHtml += `<tr><th style="text-align:left;font-size:.75rem">${L.metric_labels[i]}</th>`;
      row.forEach((v,j) => {
        const bg = i===j ? '#e0f0f2' : corrColor(v);
        const bld = i!==j && Math.abs(v)>0.5 ? 'font-weight:700' : '';
        corrHtml += `<td style="background:${bg};${bld}">${i===j?'1.00':v.toFixed(2)}</td>`;
      });
      corrHtml += '</tr>';
    });
    $(`${level}-corr-table`).innerHTML = corrHtml+'</tbody>';

    // corr note
    const allPairs = [];
    for (let i=0;i<L.corr.length;i++) for (let j=i+1;j<L.corr.length;j++) allPairs.push(L.corr[i][j]);
    const minCorr = Math.min(...allPairs).toFixed(2), maxCorr = Math.max(...allPairs).toFixed(2);
    const hasNegative = allPairs.some(v => v < -0.1);
    $(`${level}-corr-note`).className = 'callout' + (hasNegative ? ' warn' : ' good');
    $(`${level}-corr-note`).innerHTML = hasNegative
      ? `<strong>&#9888; Some negative correlations detected (min r = ${minCorr})</strong> Negative inter-metric correlations reduce the variance PC1 can explain, meaning the composite score captures less of the total variation. Inspect which metrics are negatively correlated.`
      : `<strong>&#10003; All inter-metric correlations are positive (min r = ${minCorr}, max r = ${maxCorr})</strong> This is the ideal condition for PCA: all metrics are pulling in the same direction. PC1 will explain a higher fraction of variance.`;

    // scree chart
    push(new Chart($(`${level}-screeChart`), {
      type:'bar',
      data:{ labels: L.all_var.map((_,i)=>`PC${i+1}`),
             datasets:[{label:'% variance', data:L.all_var.map(v=>(v*100).toFixed(1)),
               backgroundColor: L.all_var.map((_,i)=>i===0?`${LEVEL_BG[level]}`:'rgba(100,100,100,.25)')}] },
      options:{ responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}},
                scales:{y:{title:{display:true,text:'% variance'},max:100}} }
    }));

    // loadings chart
    const pc2l = L.all_loadings[1] || L.pc1_loadings.map(()=>0);
    push(new Chart($(`${level}-loadingsChart`), {
      type:'bar',
      data:{ labels: L.metric_labels, datasets:[
        {label:'PC1', data:L.pc1_loadings,
          backgroundColor: L.pc1_loadings.map(v=>v>=0?LEVEL_BG[level]:'rgba(198,90,30,.7)')},
        {label:'PC2', data:pc2l, backgroundColor:'rgba(130,130,130,.3)'},
      ]},
      options:{ indexAxis:'y', responsive:true, maintainAspectRatio:false,
                plugins:{legend:{labels:{font:{size:10}}}},
                scales:{x:{title:{display:true,text:'Loading'},min:-1.1,max:1.1}} }
    }));

    // loadings table
    const pc2arr = L.all_loadings[1] || L.pc1_loadings.map(()=>0);
    $(`${level}-loadings-body`).innerHTML = L.metrics.map((k,i) => {
      const l1 = L.pc1_loadings[i], l2 = pc2arr[i];
      const dir = l1 > 0.05 ? '<span style="color:var(--green)">&#8593; Higher = better</span>'
                : l1 < -0.05 ? '<span style="color:var(--red)">&#8595; Higher = worse</span>'
                : '<span style="color:var(--amber)">~ Near zero (weak)</span>';
      const mag = Math.abs(l1);
      const assess = mag > 0.35 ? '<span style="color:var(--green)">Strong driver</span>'
                   : mag > 0.15 ? '<span style="color:var(--muted)">Moderate driver</span>'
                   : '<span style="color:var(--amber)">&#9888; Weak — consider excluding</span>';
      return `<tr><td><strong>${L.metric_labels[i]}</strong></td>
        <td class="nr" style="font-weight:700;color:${l1>=0?'var(--teal)':'var(--rust)'}">${l1.toFixed(4)}</td>
        <td class="nr" style="color:var(--muted)">${l2.toFixed(4)}</td>
        <td>${dir}</td><td style="font-size:.82rem">${assess}</td></tr>`;
    }).join('');

    // scrutiny
    buildScrutiny(level, L);

    // top/bottom tables
    const renderTopBot = (rows, tbodyId, isTop) => {
      const scores = rows.map(r=>r.score);
      const scoreMin = Math.min(...scores), scoreMax = Math.max(...scores);
      $(tbodyId).innerHTML = rows.map(r => {
        const norm = (r.score - scoreMin)/(scoreMax - scoreMin + 1e-9);
        const bg = r.score > 0 ? `rgba(26,122,63,${0.1+norm*0.4})` : `rgba(176,48,32,${0.1+(1-norm)*0.3})`;
        return `<tr>
          <td style="color:var(--muted);font-size:.78rem">${r.rank}</td>
          <td style="font-size:.82rem"><a href="scorecard.html#${r.id}" style="color:var(--teal);text-decoration:none">${r.name}</a></td>
          <td style="font-size:.78rem;color:var(--muted)">${r.district}</td>
          <td class="nr" style="background:${bg};font-weight:600">${r.score.toFixed(3)}</td>
          <td class="nr">${r.overall_pct.toFixed(1)}%</td>
          <td class="nr" style="color:var(--muted)">${r.district_rank}/${r.district_total}</td>
        </tr>`;
      }).join('');
    };
    renderTopBot(L.top15, `${level}-top-body`, true);
    renderTopBot(L.bot15, `${level}-bot-body`, false);

    // biplot
    push(new Chart($(`${level}-biplot`), {
      type:'scatter',
      data:{ datasets:[{
        label: level,
        data: L.biplot_data.map(d=>({x:d.pc1,y:d.pc2,name:d.name})),
        backgroundColor: LEVEL_BG[level],
        pointRadius: 5, pointHoverRadius: 8,
      }]},
      options:{ responsive:true, maintainAspectRatio:false,
        plugins:{
          legend:{display:false},
          tooltip:{callbacks:{label:ctx=>`${ctx.raw.name} (${ctx.raw.x.toFixed(2)}, ${ctx.raw.y.toFixed(2)})`}}
        },
        scales:{
          x:{title:{display:true,text:'PC1 — Composite score (→ better)'}},
          y:{title:{display:true,text:'PC2'}},
        }
      }
    }));

    // PC2 note
    const pc2abs = pc2arr.map(Math.abs);
    const maxPC2idx = pc2abs.indexOf(Math.max(...pc2abs));
    $(`${level}-pc2-note`).innerHTML =
      `<strong>PC2 dominant metric:</strong> ${L.metric_labels[maxPC2idx]}
       (loading = ${pc2arr[maxPC2idx].toFixed(3)}, explaining ${(L.all_var[1]*100).toFixed(1)}% of variance).
       PC2 captures variation that PC1 cannot — often a tradeoff between proficiency and growth.`;

    // full table
    buildTable(level);
  };

  setTimeout(() => initCharts(level), 0);
}

function buildScrutiny(level, L) {
  const varPct = (L.variance_explained * 100).toFixed(1);
  const pc1loads = L.pc1_loadings;
  const weakMetrics = L.metrics.filter((_,i) => Math.abs(pc1loads[i]) < 0.15);
  const negMetrics  = L.metrics.filter((_,i) => pc1loads[i] < -0.05);

  let html = '';

  // Variance explained
  if (L.variance_explained >= 0.65) {
    html += `<div class="callout good"><strong>&#10003; Strong PC1: ${varPct}% variance explained</strong>
      A single composite score is a reliable summary for ${level} schools —
      the majority of cross-school variation is captured by PC1.</div>`;
  } else if (L.variance_explained >= 0.50) {
    html += `<div class="callout warn"><strong>&#9888; Moderate PC1: ${varPct}% variance explained</strong>
      More than half the variation is captured by PC1, but a substantial portion
      (${(100-parseFloat(varPct)).toFixed(1)}%) lies in other components. The composite score
      is a reasonable but imperfect summary. Schools that score high on proficiency but
      low on growth (or vice versa) may be mischaracterised.</div>`;
  } else {
    html += `<div class="callout critical"><strong>&#9888; Weak PC1: only ${varPct}% variance explained</strong>
      Less than half the variation is captured by PC1. A single composite score is a
      poor summary of ${level} school performance. Consider reporting multiple dimensions
      (proficiency vs. growth) rather than a single rank.</div>`;
  }

  // Negative loadings
  if (negMetrics.length > 0) {
    const names = negMetrics.map(k => L.metric_labels[L.metrics.indexOf(k)]).join(', ');
    html += `<div class="callout critical"><strong>&#9888; Negative PC1 loading(s): ${names}</strong>
      A negative loading means higher values of this metric are associated with a <em>lower</em>
      composite score — the opposite of intent. Inspect the correlation matrix to understand why.</div>`;
  }

  // Weak loadings
  if (weakMetrics.length > 0) {
    const names = weakMetrics.map(k => L.metric_labels[L.metrics.indexOf(k)]).join(', ');
    html += `<div class="callout warn"><strong>&#9888; Weak PC1 loading(s): ${names}</strong>
      These metrics contribute little to the composite score. Consider whether they add
      meaningful signal or just noise for ${level} schools.</div>`;
  }

  // Positive
  const strongMetrics = L.metrics.filter((_,i) => pc1loads[i] > 0.3);
  if (strongMetrics.length === L.metrics.length) {
    html += `<div class="callout good"><strong>&#10003; All loadings positive</strong>
      Every metric points in the same direction — higher values always improve the composite score.
      This is the ideal outcome for a transparent ranking system.</div>`;
  }

  // Coverage
  const partialPct = (100 - L.comp_buckets['100%'] / L.n_schools * 100).toFixed(0);
  if (parseFloat(partialPct) > 30) {
    html += `<div class="callout warn"><strong>&#9888; ${partialPct}% of ${level} schools have partial data</strong>
      More than a third of schools are missing at least one metric and receive z&nbsp;=&nbsp;0 for that metric.
      Their composite scores are less reliable. The scorecard UI should flag these schools clearly.</div>`;
  } else {
    html += `<div class="callout good"><strong>&#10003; Good data completeness (${100-parseInt(partialPct)}% full coverage)</strong>
      The majority of ${level} schools have all metrics observed.</div>`;
  }

  if (level === 'High') {
    const gradIdx = L.metrics.indexOf('four_year_grad_rate');
    const gradLoad = gradIdx >= 0 ? pc1loads[gradIdx] : null;
    if (gradLoad !== null && gradLoad > 0.1) {
      html += `<div class="callout good"><strong>&#10003; Grad rate loading is positive (${gradLoad.toFixed(4)})</strong>
        Now that only real high-school grad rates are used (no cross-level 0.0 imputation),
        the graduation rate contributes meaningfully and correctly to the composite score.</div>`;
    }
  }

  $(`${level}-scrutiny-content`).innerHTML = html || '<div class="callout good">No issues detected.</div>';
}

// ---- Full sortable table ----
const tableState = {};
function buildTable(level) {
  if (!tableState[level]) tableState[level] = { sortCol:'rank', sortAsc:true, filter:'', showZ:false };
  const st = tableState[level];
  const L = R.levels[level];
  const scoreVals = L.full_table.map(r=>r.score);
  const sMin = Math.min(...scoreVals), sMax = Math.max(...scoreVals);

  // Compute per-metric pool medians for cell colouring (over observed values only)
  const metricMedians = {};
  L.metrics.forEach(key => {
    const vals = L.full_table
      .map(r => r.raw_inputs[key])
      .filter(v => v != null)
      .sort((a,b) => a-b);
    metricMedians[key] = vals.length ? vals[Math.floor(vals.length/2)] : null;
  });

  // Build metric sub-header row once
  const mhRow = $(`${level}-metric-header-row`);
  if (mhRow && !mhRow.dataset.built) {
    mhRow.innerHTML = L.metric_labels.map((lbl, i) => {
      const load = L.pc1_loadings[i];
      const tip = `Loading: ${load >= 0 ? '+' : ''}${load.toFixed(3)}`;
      return `<th class="nr" title="${tip}" style="background:rgba(15,108,116,.06);color:var(--muted);font-size:.74rem;white-space:nowrap">
        ${lbl}<br><span style="font-size:.68rem;color:var(--teal)">${load >= 0 ? '+' : ''}${load.toFixed(3)}</span>
      </th>`;
    }).join('');
    // Update colspan dynamically
    const hdrSpan = $(`${level}-inputs-header`);
    if (hdrSpan) hdrSpan.setAttribute('colspan', L.metrics.length);
    mhRow.dataset.built = '1';
  }

  function fmtRaw(key, val) {
    if (val == null) return '—';
    if (key.includes('rate')) return (val * 100).toFixed(1) + '%';
    if (key.includes('percentile')) return Math.round(val).toString();
    return val.toFixed(3);
  }

  function metricCellBg(key, val, zVal) {
    if (val == null) return '#e8e8e8';  // missing
    const med = metricMedians[key];
    if (med == null) return 'transparent';
    return val > med
      ? `rgba(26,122,63,${Math.min(0.08 + Math.abs(zVal) * 0.12, 0.45)})`
      : `rgba(176,48,32,${Math.min(0.06 + Math.abs(zVal) * 0.10, 0.35)})`;
  }

  function render() {
    const f = st.filter.toLowerCase();
    let rows = L.full_table.filter(r =>
      !f || r.name.toLowerCase().includes(f) || r.district.toLowerCase().includes(f)
    ).slice().sort((a,b) => {
      let va = a[st.sortCol], vb = b[st.sortCol];
      if (typeof va === 'string') { va = va.toLowerCase(); vb = vb.toLowerCase(); }
      return st.sortAsc ? (va>vb?1:va<vb?-1:0) : (va<vb?1:va>vb?-1:0);
    });

    $(`${level}-tbl-count`).textContent = `Showing ${rows.length} of ${L.full_table.length} schools`;

    // Update inputs-header label
    const hdr = $(`${level}-inputs-header`);
    if (hdr) hdr.textContent = `INPUT METRICS (${st.showZ ? 'z-scores' : 'raw'})`;

    $(`${level}-rank-body`).innerHTML = rows.map(r => {
      const norm = (r.score - sMin) / (sMax - sMin + 1e-9);
      const scoreBg = r.score > 0
        ? `rgba(26,122,63,${0.1+norm*0.4})`
        : `rgba(176,48,32,${0.05+(1-norm)*0.3})`;
      const compBg = r.completeness===1 ? '#d4edda' : r.completeness>=0.8 ? '#fff3cd' : '#f8d7da';

      const metricCells = L.metrics.map(key => {
        const rawVal = r.raw_inputs[key];
        const zVal   = r.z_scores[key];
        const bg = metricCellBg(key, rawVal, zVal != null ? zVal : 0);
        const display = st.showZ
          ? (zVal != null ? (zVal >= 0 ? '+' : '') + zVal.toFixed(2) : '—')
          : fmtRaw(key, rawVal);
        const missing = rawVal == null;
        return `<td class="nr" style="background:${bg};font-size:.78rem;${missing?'color:#aaa;font-style:italic':''}" title="${key}: raw=${rawVal ?? 'missing'}, z=${zVal ?? 'imputed 0'}">${display}</td>`;
      }).join('');

      return `<tr>
        <td style="color:var(--muted);font-size:.78rem">${r.rank}</td>
        <td style="font-size:.82rem"><a href="scorecard.html#${r.id}" style="color:var(--teal);text-decoration:none">${r.name}</a></td>
        <td style="font-size:.78rem;color:var(--muted)">${r.district}</td>
        <td class="nr" style="background:${scoreBg};font-weight:600">${r.score.toFixed(3)}</td>
        <td class="nr">${r.overall_pct.toFixed(1)}%</td>
        <td class="nr" style="color:var(--muted)">${r.district_rank}/${r.district_total}</td>
        <td class="nr" style="background:${compBg};font-size:.78rem">${Math.round(r.completeness*100)}%</td>
        ${metricCells}
      </tr>`;
    }).join('');
  }

  document.querySelectorAll(`#${level}-ranktable th[data-col]`).forEach(th => {
    th.addEventListener('click', () => {
      const col = th.dataset.col;
      if (st.sortCol === col) st.sortAsc = !st.sortAsc;
      else { st.sortCol = col; st.sortAsc = col === 'rank'; }
      render();
    });
  });

  $(`${level}-search`).addEventListener('input', e => {
    st.filter = e.target.value;
    render();
  });

  $(`${level}-show-z`).addEventListener('change', e => {
    st.showZ = e.target.checked;
    render();
  });

  render();
}

// ---- Tab switching ----
let activeLevel = null;
const builtPanels = new Set();

function switchTab(level) {
  ['Elementary','Middle','High'].forEach(l => {
    $('tab-' + l).classList.toggle('active', l === level);
    document.querySelector(`.tab-btn[data-level="${l}"]`)
      .className = `tab-btn${l === level ? ' active-' + l.toLowerCase().replace('elementary','elem').replace('middle','mid') : ''}`;
  });

  if (!builtPanels.has(level)) {
    buildTabPanel(level);
    builtPanels.add(level);
  }
  activeLevel = level;
}

// Initial tab
switchTab('Elementary');
</script>
</body>
</html>
"""


def main() -> None:
    data_path = ROOT / "site" / "dashboard-data.json"
    if not data_path.exists():
        print("ERROR: site/dashboard-data.json not found.", file=sys.stderr)
        sys.exit(1)

    print("Loading dashboard-data.json ...", file=sys.stderr)
    data = json.loads(data_path.read_text(encoding="utf-8"))

    print("Running per-level PCA analyses ...", file=sys.stderr)
    report_data = build_report_data(data)

    print("Writing site/pca-analysis.html ...", file=sys.stderr)
    out = ROOT / "site" / "pca-analysis.html"
    out.write_text(HTML.replace("__REPORT_DATA__", json.dumps(report_data)), encoding="utf-8")

    print(f"Done. Open: file://{out}", file=sys.stderr)
    for level in ("Elementary", "Middle", "High"):
        ld = report_data["levels"][level]
        loads = dict(zip(ld["metric_labels"], ld["pc1_loadings"]))
        print(f"  {level}: n={ld['n_schools']}, PC1 var={ld['variance_explained']:.1%}, loadings={loads}", file=sys.stderr)


if __name__ == "__main__":
    main()
