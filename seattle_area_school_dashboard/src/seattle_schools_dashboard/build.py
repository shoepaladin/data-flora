import json
from pathlib import Path

from seattle_schools_dashboard.nces import METRIC_DEFINITIONS, build_dashboard_payload
from seattle_schools_dashboard.ospi import fetch_ospi_metrics


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Seattle Area School Dashboard</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    :root {
      --bg: #f4efe6;
      --paper: rgba(255, 252, 246, 0.92);
      --ink: #1b2330;
      --muted: #5f6b7a;
      --teal: #0f6c74;
      --rust: #c65a1e;
      --border: rgba(27, 35, 48, 0.12);
      --shadow: 0 16px 40px rgba(27, 35, 48, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Trebuchet MS", "Avenir Next", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top right, rgba(198, 90, 30, 0.16), transparent 30%),
        radial-gradient(circle at left center, rgba(15, 108, 116, 0.12), transparent 28%),
        linear-gradient(180deg, #fbf6ee 0%, var(--bg) 100%);
    }
    main {
      max-width: 1400px;
      margin: 0 auto;
      padding: 20px 18px 48px;
    }
    .hero, .panel, .card {
      background: var(--paper);
      border: 1px solid var(--border);
      border-radius: 18px;
      box-shadow: var(--shadow);
    }
    .hero {
      padding: 18px 24px;
      margin-bottom: 16px;
      display: flex;
      align-items: center;
      gap: 20px;
      flex-wrap: wrap;
    }
    .hero h1 {
      margin: 0;
      font-family: Georgia, \"Times New Roman\", serif;
      font-size: clamp(1.5rem, 2vw, 2.2rem);
    }
    .eyebrow {
      text-transform: uppercase;
      letter-spacing: 0.14em;
      color: var(--teal);
      font-size: 0.73rem;
      font-weight: 700;
      margin-bottom: 2px;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      font-size: 0.76rem;
      color: var(--muted);
      background: rgba(255, 255, 255, 0.78);
      border: 1px solid rgba(27, 35, 48, 0.08);
      border-radius: 999px;
      padding: 4px 10px;
      margin-left: auto;
    }
    .layout {
      display: grid;
      grid-template-columns: var(--sidebar-width, 230px) 1fr;
      gap: 16px;
      align-items: start;
      position: relative;
    }
    /* Prevent grid children from overflowing their column — without this,
       items default to min-width:auto and the right panel won't shrink. */
    .layout > * { min-width: 0; }
    aside { position: relative; }
    #resize-handle {
      position: absolute;
      top: 0;
      left: calc(var(--sidebar-width, 230px) + 8px);
      width: 8px;
      height: 100%;
      cursor: col-resize;
      z-index: 10;
      border-radius: 4px;
      transition: background 120ms;
    }
    #resize-handle:hover,
    #resize-handle.dragging {
      background: rgba(15, 108, 116, 0.25);
    }
    .panel, .card { padding: 16px; }
    .main-stack { display: grid; gap: 14px; }

    /* Sidebar control labels */
    .ctrl-label {
      display: block;
      font-size: 0.71rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--muted);
      margin: 13px 0 4px;
    }
    .ctrl-label:first-child { margin-top: 0; }

    /* Select */
    select {
      width: 100%;
      border-radius: 9px;
      border: 1px solid rgba(27, 35, 48, 0.15);
      padding: 8px 10px;
      font: inherit;
      font-size: 0.86rem;
      background: rgba(255, 255, 255, 0.85);
      color: var(--ink);
      cursor: pointer;
    }

    /* Toggle buttons */
    .toggle { display: flex; gap: 5px; }
    button {
      background: var(--teal);
      color: white;
      border: 0;
      border-radius: 999px;
      padding: 7px 12px;
      cursor: pointer;
      font: inherit;
      font-size: 0.83rem;
      transition: opacity 130ms;
    }
    button:hover { opacity: 0.85; }
    button.ghost {
      background: rgba(255,255,255,0.85);
      color: var(--ink);
      border: 1px solid rgba(27,35,48,0.12);
    }
    button.active { background: var(--ink); color: white; border-color: var(--ink); }
    button.secondary { background: var(--rust); }
    .toolbar { display: flex; gap: 5px; margin-top: 7px; }

    /* Log scale */
    .log-row {
      display: flex;
      align-items: center;
      gap: 7px;
      font-size: 0.84rem;
      padding: 2px 0;
      cursor: pointer;
    }
    .log-row input[type=\"checkbox\"] {
      width: 14px; height: 14px;
      cursor: pointer;
      accent-color: var(--teal);
    }

    /* District dropdown */
    details.dropdown > summary {
      list-style: none;
      padding: 8px 10px;
      border-radius: 9px;
      border: 1px solid rgba(27,35,48,0.15);
      background: rgba(255,255,255,0.85);
      cursor: pointer;
      font-size: 0.86rem;
      display: flex;
      justify-content: space-between;
      user-select: none;
    }
    details.dropdown > summary::after { content: \"▾\"; color: var(--muted); }
    details[open].dropdown > summary { border-radius: 9px 9px 0 0; border-bottom-color: transparent; }
    details.dropdown > summary::-webkit-details-marker { display: none; }
    .dropdown-panel {
      border: 1px solid rgba(27,35,48,0.15);
      border-top: none;
      border-radius: 0 0 9px 9px;
      background: rgba(255,255,255,0.92);
      padding: 5px;
      max-height: 190px;
      overflow-y: auto;
    }
    .chk-row {
      display: flex;
      align-items: center;
      gap: 7px;
      padding: 5px 7px;
      border-radius: 7px;
      font-size: 0.83rem;
      cursor: pointer;
    }
    .chk-row:hover { background: rgba(15,108,116,0.07); }
    .chk-row input[type=\"checkbox\"] {
      width: 13px; height: 13px;
      cursor: pointer;
      accent-color: var(--teal);
      flex-shrink: 0;
    }

    /* School list */
    .search-input {
      width: 100%;
      border-radius: 9px;
      border: 1px solid rgba(27,35,48,0.15);
      padding: 7px 10px;
      font: inherit;
      font-size: 0.84rem;
      background: rgba(255,255,255,0.85);
      margin-bottom: 5px;
    }
    .school-list {
      max-height: 190px;
      overflow-y: auto;
      display: grid;
      gap: 3px;
    }
    .empty-state {
      padding: 9px;
      font-size: 0.81rem;
      color: var(--muted);
      border-radius: 7px;
      background: rgba(255,255,255,0.6);
    }

    /* Level filter pills */
    .level-filter { display: flex; gap: 4px; flex-wrap: wrap; }
    .level-filter button { font-size: 0.78rem; padding: 5px 10px; border-radius: 999px; }

    /* Chart */
    .chart-panel { position: relative; padding-bottom: 28px; }
    .chart-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 10px;
      gap: 12px;
      flex-wrap: wrap;
    }
    .chart-header h2 { margin: 0 0 2px; font-size: 1rem; }
    .chart-desc { font-size: 0.8rem; color: var(--muted); }
    .chart-wrap { height: 380px; position: relative; }
    .footnote {
      position: absolute;
      bottom: 6px; left: 16px; right: 16px;
      font-size: 0.76rem;
      color: var(--muted);
      text-align: center;
    }

    /* Stats */
    .stats { display: grid; grid-template-columns: repeat(4,1fr); gap: 12px; }
    .card-value { font-size: clamp(1.25rem,1.7vw,1.8rem); font-weight: 700; margin: 5px 0 3px; }
    .card-label { font-size: 0.78rem; color: var(--muted); }
    .caption { font-size: 0.75rem; color: var(--muted); }

    @media (max-width: 900px) {
      .layout { grid-template-columns: 1fr; }
      .stats { grid-template-columns: repeat(2,1fr); }
      #resize-handle { display: none; }
    }
  </style>
</head>
<body>
  <div id=\"loading\" style=\"text-align:center;padding:80px;font-size:1.1rem;color:#5f6b7a;\">Loading dashboard data…</div>
  <main style=\"display:none\">
    <section class=\"hero\">
      <div>
        <div class=\"eyebrow\">NCES CCD Data</div>
        <h1>Seattle Area School Dashboard</h1>
      </div>
      <div class=\"pill\" id=\"build-meta\"></div>
      <a href=\"https://github.com/shoepaladin/data-flora\" target=\"_blank\" rel=\"noopener\"
         style=\"margin-left:auto;display:inline-flex;align-items:center;gap:6px;font-size:0.82rem;color:var(--teal);text-decoration:none;white-space:nowrap;\">
        <svg width=\"16\" height=\"16\" viewBox=\"0 0 16 16\" fill=\"currentColor\" aria-hidden=\"true\">
          <path d=\"M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38
            0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13
            -.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66
            .07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15
            -.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0
            1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82
            1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01
            1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z\"/>
        </svg>
        Source code
      </a>
    </section>
    <div class=\"layout\">
      <aside>
        <section class=\"panel\">
          <span class=\"ctrl-label\">Metric</span>
          <select id=\"metric-select\"></select>

          <span class=\"ctrl-label\">Year range</span>
          <div style=\"display:flex;gap:6px;align-items:center;\">
            <select id=\"start-year-select\" style=\"flex:1\"></select>
            <span style=\"color:var(--muted);font-size:0.8rem;\">to</span>
            <select id=\"end-year-select\" style=\"flex:1\"></select>
          </div>
          <div id=\"year-range-error\" style=\"display:none;font-size:0.78rem;color:var(--rust);margin-top:4px;\"></div>

          <div id=\"log-scale-section\">
            <span class=\"ctrl-label\">Scale</span>
            <label class=\"log-row\">
              <input type=\"checkbox\" id=\"log-scale-checkbox\"> Log scale
            </label>
          </div>

          <span class=\"ctrl-label\">Districts</span>
          <details class=\"dropdown\" id=\"district-dropdown\">
            <summary id=\"district-summary\">No districts selected</summary>
            <div class=\"dropdown-panel\" id=\"district-panel\"></div>
          </details>
          <div class=\"toolbar\">
            <button id=\"select-all-districts\">All</button>
            <button id=\"clear-all\" class=\"secondary\">Clear</button>
          </div>

          <span class=\"ctrl-label\">School level</span>
          <div class=\"level-filter\" id=\"level-filter\"></div>

          <span class=\"ctrl-label\">Schools <span id=\"school-count-label\" style=\"font-weight:400;text-transform:none;letter-spacing:0;\"></span></span>
          <input id=\"school-search\" class=\"search-input\" type=\"search\" placeholder=\"Search…\">
          <div id=\"schools\" class=\"school-list\"></div>
          <div class=\"toolbar\">
            <button id=\"select-visible-schools\">All</button>
            <button id=\"clear-visible-schools\" class=\"secondary\">Clear</button>
          </div>
        </section>
      </aside>
      <div id=\"resize-handle\"></div>
      <section class=\"main-stack\">
        <section class=\"panel chart-panel\">
          <div class=\"chart-header\">
            <div>
              <h2 id=\"chart-title\"></h2>
              <div class=\"chart-desc\" id=\"chart-description\"></div>
            </div>
          </div>
          <div class=\"chart-wrap\">
            <canvas id=\"trendChart\"></canvas>
          </div>
          <div class=\"footnote\" id=\"chart-note\"></div>
          <div id=\"caveat-banner\" style=\"display:none;margin-top:8px;padding:7px 12px;border-radius:8px;background:rgba(198,90,30,0.10);border:1px solid rgba(198,90,30,0.25);font-size:0.8rem;color:#7a3810;\"></div>
        </section>
        <section class=\"card stats\">
          <article>
            <div class=\"card-label\">Selected districts</div>
            <div class=\"card-value\" id=\"selected-districts-value\">0</div>
            <div class=\"caption\" id=\"selected-districts-caption\"></div>
          </article>
          <article>
            <div class=\"card-label\">Selected schools</div>
            <div class=\"card-value\" id=\"selected-schools-value\">0</div>
            <div class=\"caption\" id=\"selected-schools-caption\"></div>
          </article>
          <article>
            <div class=\"card-label\">Current-year average</div>
            <div class=\"card-value\" id=\"average-value\">--</div>
            <div class=\"caption\" id=\"average-caption\"></div>
          </article>
          <article>
            <div class=\"card-label\">Coverage</div>
            <div class=\"card-value\" id=\"coverage-value\">--</div>
            <div class=\"caption\" id=\"coverage-caption\"></div>
          </article>
        </section>
        <section class=\"panel chart-panel\">
          <div class=\"chart-header\">
            <div>
              <h2 id=\"avg-chart-title\"></h2>
              <div class=\"chart-desc\" id=\"avg-chart-description\"></div>
            </div>
          </div>
          <div class=\"chart-wrap\" style=\"height:220px;\">
            <canvas id=\"avgChart\"></canvas>
          </div>
        </section>
      </section>
    </div>
  </main>
  <script>
    fetch('./dashboard-data.json')
      .then(r => { if (!r.ok) throw new Error(r.statusText); return r.json(); })
      .then(dashboardData => {
    document.getElementById('loading').style.display = 'none';
    document.querySelector('main').style.display = '';
    const schoolSearch = document.getElementById('school-search');
    const palette = ['#0f6c74','#c65a1e','#4f7f29','#7d4e9f','#af405b','#3666b0','#8b6f18','#247b5f'];

    const districtById = Object.fromEntries(dashboardData.districts.map((d) => [d.id, d]));
    const schoolById = Object.fromEntries(dashboardData.schools.map((s) => [s.id, s]));
    const recordsBySchool = dashboardData.records.reduce((acc, rec) => {
      (acc[rec.school_id] = acc[rec.school_id] || {})[rec.year] = rec;
      return acc;
    }, {});

    const initialDistrictIds = new Set(
      dashboardData.schools
        .filter((s) => dashboardData.initial_state.selected_school_ids.includes(s.id))
        .map((s) => s.district_id)
    );
    const ALL_LEVELS = ['Elementary', 'Middle', 'High', 'Other', 'Unknown'];
    const state = {
      selectedDistrictIds: initialDistrictIds,
      selectedSchoolIds: new Set(dashboardData.initial_state.selected_school_ids),
      selectedLevels: new Set(ALL_LEVELS),
      metricKey: dashboardData.initial_state.metric_key,
      startYear: dashboardData.initial_state.start_year,
      endYear:   dashboardData.initial_state.end_year,
      logScale: false,
      schoolSearch: '',
    };

    const chart = new Chart(document.getElementById('trendChart'), {
      type: 'line',
      data: { labels: [], datasets: [] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'nearest', intersect: false },
        plugins: {
          legend: { position: 'bottom' },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const def = dashboardData.metrics[state.metricKey];
                return `${ctx.dataset.label}: ${formatValue(ctx.raw, def.format)}`;
              }
            }
          }
        },
        scales: {
          y: {
            type: 'linear',
            ticks: { callback: (v) => formatAxisValue(v, dashboardData.metrics[state.metricKey].format) }
          }
        }
      }
    });

    const avgChart = new Chart(document.getElementById('avgChart'), {
      type: 'line',
      data: { labels: [], datasets: [] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'nearest', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const def = dashboardData.metrics[state.metricKey];
                return formatValue(ctx.raw, def.format);
              }
            }
          }
        },
        scales: {
          y: {
            type: 'linear',
            ticks: { callback: (v) => formatAxisValue(v, dashboardData.metrics[state.metricKey].format) }
          }
        }
      }
    });

    document.getElementById('build-meta').textContent =
      `Generated ${new Date(dashboardData.generated_at).toLocaleDateString()} · NCES Common Core of Data`;
    document.getElementById('select-all-districts').addEventListener('click', () => {
      dashboardData.districts.forEach((d) => {
        state.selectedDistrictIds.add(d.id);
        d.school_ids.forEach((id) => state.selectedSchoolIds.add(id));
      });
      renderAll();
    });
    document.getElementById('clear-all').addEventListener('click', () => {
      state.selectedDistrictIds.clear();
      state.selectedSchoolIds.clear();
      renderAll();
    });
    document.getElementById('select-visible-schools').addEventListener('click', () => {
      getVisibleSchools().forEach((s) => state.selectedSchoolIds.add(s.id));
      renderAll();
    });
    document.getElementById('clear-visible-schools').addEventListener('click', () => {
      getVisibleSchools().forEach((s) => state.selectedSchoolIds.delete(s.id));
      renderAll();
    });
    schoolSearch.addEventListener('input', (e) => {
      state.schoolSearch = e.target.value.trim().toLowerCase();
      renderSchools();
    });
    document.getElementById('log-scale-checkbox').addEventListener('change', (e) => {
      state.logScale = e.target.checked;
      updateView();
    });

    renderMetricSelect();
    renderYearSelects();
    renderLevelFilter();
    renderDistrictDropdown();
    renderSchools();
    updateView();

    (function () {
      const handle = document.getElementById('resize-handle');
      const layout  = handle.closest('.layout');
      let dragging  = false;
      handle.addEventListener('mousedown', (e) => {
        dragging = true;
        handle.classList.add('dragging');
        e.preventDefault();
      });
      document.addEventListener('mousemove', (e) => {
        if (!dragging) return;
        const rect     = layout.getBoundingClientRect();
        const maxWidth = rect.width / 2;
        const newWidth = Math.min(Math.max(e.clientX - rect.left, 180), maxWidth);
        layout.style.setProperty('--sidebar-width', newWidth + 'px');
        handle.style.left = (newWidth + 8) + 'px';
        chart.resize();
        avgChart.resize();
      });
      document.addEventListener('mouseup', () => {
        if (!dragging) return;
        dragging = false;
        handle.classList.remove('dragging');
      });
    })();

    function renderAll() {
      renderDistrictDropdown();
      renderSchools();
      updateView();
    }

    function renderMetricSelect() {
      const sel = document.getElementById('metric-select');
      const groups = {};
      Object.entries(dashboardData.metrics).forEach(([key, def]) => {
        (groups[def.category] = groups[def.category] || []).push({ key, def });
      });
      sel.innerHTML = '';
      Object.entries(groups).forEach(([cat, items]) => {
        const grp = document.createElement('optgroup');
        grp.label = cat;
        items.forEach(({ key, def }) => {
          const opt = document.createElement('option');
          opt.value = key;
          opt.textContent = def.label;
          opt.selected = key === state.metricKey;
          grp.appendChild(opt);
        });
        sel.appendChild(grp);
      });
      sel.addEventListener('change', (e) => {
        state.metricKey = e.target.value;
        if (dashboardData.metrics[state.metricKey].format !== 'integer') state.logScale = false;
        updateView();
      });
    }

    function renderYearSelects() {
      const startSel = document.getElementById('start-year-select');
      const endSel   = document.getElementById('end-year-select');
      [startSel, endSel].forEach(sel => {
        sel.innerHTML = '';
        dashboardData.years.forEach(yr => {
          const opt = document.createElement('option');
          opt.value = opt.textContent = yr;
          sel.appendChild(opt);
        });
      });
      startSel.value = state.startYear;
      endSel.value   = state.endYear;
      startSel.addEventListener('change', e => { state.startYear = e.target.value; updateView(); });
      endSel.addEventListener('change',   e => { state.endYear   = e.target.value; updateView(); });
    }

    function renderDistrictDropdown() {
      const panel = document.getElementById('district-panel');
      panel.innerHTML = '';
      dashboardData.districts.forEach((district) => {
        const lbl = document.createElement('label');
        lbl.className = 'chk-row';
        const chk = document.createElement('input');
        chk.type = 'checkbox';
        chk.checked = state.selectedDistrictIds.has(district.id);
        chk.addEventListener('change', () => {
          if (chk.checked) {
            state.selectedDistrictIds.add(district.id);
            district.school_ids.forEach((id) => state.selectedSchoolIds.add(id));
          } else {
            state.selectedDistrictIds.delete(district.id);
            district.school_ids.forEach((id) => state.selectedSchoolIds.delete(id));
          }
          renderAll();
        });
        lbl.appendChild(chk);
        lbl.appendChild(document.createTextNode(district.name));
        panel.appendChild(lbl);
      });
      const n = state.selectedDistrictIds.size;
      document.getElementById('district-summary').textContent =
        n === 0 ? 'No districts selected'
        : n === dashboardData.districts.length ? 'All districts'
        : `${n} district${n > 1 ? 's' : ''} selected`;
    }

    function renderSchools() {
      const container = document.getElementById('schools');
      container.innerHTML = '';
      const visible = getVisibleSchools();
      document.getElementById('school-count-label').textContent = visible.length ? `(${visible.length})` : '';
      if (!visible.length) {
        container.innerHTML = '<div class=\"empty-state\">Select a district to see schools.</div>';
        return;
      }
      visible.forEach((school) => {
        const lbl = document.createElement('label');
        lbl.className = 'chk-row';
        const chk = document.createElement('input');
        chk.type = 'checkbox';
        chk.checked = state.selectedSchoolIds.has(school.id);
        chk.addEventListener('change', () => {
          chk.checked ? state.selectedSchoolIds.add(school.id) : state.selectedSchoolIds.delete(school.id);
          renderSchools();
          updateView();
        });
        const txt = document.createElement('span');
        txt.textContent = school.name;
        lbl.appendChild(chk);
        lbl.appendChild(txt);
        container.appendChild(lbl);
      });
    }

    function updateView() {
      const errEl = document.getElementById('year-range-error');
      const startIdx = dashboardData.years.indexOf(state.startYear);
      const endIdx   = dashboardData.years.indexOf(state.endYear);
      if (startIdx > endIdx) {
        errEl.textContent = 'Start year must be before end year.';
        errEl.style.display = '';
        return;
      }
      const yearsInRange = dashboardData.years.slice(startIdx, endIdx + 1);
      const hasData = Array.from(state.selectedSchoolIds).some(id =>
        yearsInRange.some(yr => recordsBySchool[id]?.[yr] !== undefined)
      );
      if (!hasData && state.selectedSchoolIds.size > 0) {
        errEl.textContent = 'No data available for the selected schools and year range.';
        errEl.style.display = '';
        return;
      }
      errEl.style.display = 'none';

      const def = dashboardData.metrics[state.metricKey];
      document.getElementById('chart-title').textContent = def.label;
      document.getElementById('chart-description').textContent = def.description;
      const logSection = document.getElementById('log-scale-section');
      logSection.style.display = def.format === 'integer' ? '' : 'none';
      document.getElementById('log-scale-checkbox').checked = state.logScale;

      const caveatBanner = document.getElementById('caveat-banner');
      const caveats = def.caveat_years || {};
      const startIdx = dashboardData.years.indexOf(state.startYear);
      const endIdx   = dashboardData.years.indexOf(state.endYear);
      const activeYears = endIdx >= startIdx ? dashboardData.years.slice(startIdx, endIdx + 1) : [];
      const activeCaveats = activeYears.filter(yr => caveats[yr]).map(yr => `${yr}: ${caveats[yr]}`);
      if (activeCaveats.length) {
        caveatBanner.textContent = '⚠ ' + activeCaveats.join(' · ');
        caveatBanner.style.display = '';
      } else {
        caveatBanner.style.display = 'none';
      }

      updateSummaryCards(def);
      updateChart(def);
      updateAverageChart(def);
    }

    function updateAverageChart(def) {
      const isEnrollment = state.metricKey === 'enrollment';
      const years = dashboardData.years.slice(dashboardData.years.indexOf(state.startYear), dashboardData.years.indexOf(state.endYear) + 1);
      const useLog = state.logScale && def.format === 'integer';

      const data = years.map((yr) => {
        let sumWeighted = 0, sumEnrollment = 0;
        for (const id of state.selectedSchoolIds) {
          const rec = recordsBySchool[id]?.[yr];
          if (!rec) continue;
          const val = rec[state.metricKey];
          const enroll = rec.enrollment;
          if (val === null || val === undefined) continue;
          if (isEnrollment) {
            sumWeighted += val;
            sumEnrollment += 1;
          } else {
            if (!enroll) continue;
            sumWeighted += val * enroll;
            sumEnrollment += enroll;
          }
        }
        if (sumEnrollment === 0) return null;
        return isEnrollment ? sumWeighted : sumWeighted / sumEnrollment;
      });

      const label = isEnrollment ? 'Total enrollment (selected schools)' : `Enrollment-weighted average — ${def.label}`;
      document.getElementById('avg-chart-title').textContent = isEnrollment ? 'Total enrollment' : 'Weighted average';
      document.getElementById('avg-chart-description').textContent = isEnrollment
        ? 'Sum of enrollment across all selected schools.'
        : `Enrollment-weighted average of ${def.label.toLowerCase()} across all selected schools.`;

      avgChart.options.scales.y.type = useLog ? 'logarithmic' : 'linear';
      avgChart.options.scales.y.ticks.callback = useLog
        ? (v) => Number(v).toLocaleString()
        : (v) => formatAxisValue(v, def.format);

      avgChart.data.labels = years;
      avgChart.data.datasets = [{
        label,
        data,
        borderColor: '#1b2330',
        backgroundColor: 'rgba(27,35,48,0.08)',
        borderWidth: 2.5,
        pointRadius: 3,
        tension: 0.2,
        fill: true,
        spanGaps: false,
      }];
      avgChart.update();
    }

    function updateSummaryCards(def) {
      const selected = dashboardData.schools.filter((s) => state.selectedSchoolIds.has(s.id));
      const activeIds = getActiveDistrictIds();
      const curYear = dashboardData.years[dashboardData.years.length - 1];
      const vals = selected
        .map((s) => recordsBySchool[s.id]?.[curYear]?.[state.metricKey] ?? null)
        .filter((v) => v !== null);

      document.getElementById('selected-districts-value').textContent = String(activeIds.length);
      document.getElementById('selected-districts-caption').textContent = activeIds.length
        ? activeIds.map((id) => districtById[id].name).slice(0, 2).join(', ') + (activeIds.length > 2 ? ` +${activeIds.length - 2} more` : '')
        : 'No districts selected';
      document.getElementById('selected-schools-value').textContent = String(selected.length);
      document.getElementById('selected-schools-caption').textContent = selected.length
        ? `across ${activeIds.length} district${activeIds.length !== 1 ? 's' : ''}`
        : 'Choose districts to compare schools';
      document.getElementById('average-value').textContent = vals.length
        ? formatValue(vals.reduce((a, b) => a + b, 0) / vals.length, def.format) : '--';
      document.getElementById('average-caption').textContent = vals.length
        ? `Average across ${vals.length} schools in ${curYear}` : 'No data for selection';
      document.getElementById('coverage-value').textContent = vals.length ? `${vals.length}/${selected.length}` : '--';
      document.getElementById('coverage-caption').textContent = `${def.label} coverage in ${curYear}`;
    }

    function updateChart(def) {
      const schoolIds = Array.from(state.selectedSchoolIds)
        .sort((a, b) => schoolById[a].name.localeCompare(schoolById[b].name))
        .slice(0, 8);
      const years = dashboardData.years.slice(dashboardData.years.indexOf(state.startYear), dashboardData.years.indexOf(state.endYear) + 1);
      const useLog = state.logScale && def.format === 'integer';

      chart.options.scales.y.type = useLog ? 'logarithmic' : 'linear';
      chart.options.scales.y.ticks.callback = useLog
        ? (v) => Number(v).toLocaleString()
        : (v) => formatAxisValue(v, def.format);

      chart.data.labels = years;
      chart.data.datasets = schoolIds.map((id, i) => ({
        label: schoolById[id].name,
        data: years.map((yr) => recordsBySchool[id]?.[yr]?.[state.metricKey] ?? null),
        borderColor: palette[i % palette.length],
        backgroundColor: palette[i % palette.length],
        borderWidth: 2.5,
        pointRadius: 3,
        tension: 0.2,
        spanGaps: false,
      }));
      chart.update();

      const all = Array.from(state.selectedSchoolIds);
      document.getElementById('chart-note').textContent =
        !schoolIds.length ? 'Select districts and schools to draw trend lines.'
        : all.length > schoolIds.length ? `Showing first 8 of ${all.length} selected schools.`
        : useLog ? 'Y-axis is logarithmic — hover to see level values.'
        : def.format === 'percent' ? 'Missing values are left blank, not interpolated.'
        : '';
    }

    function renderLevelFilter() {
      const container = document.getElementById('level-filter');
      container.innerHTML = '';
      const labels = { Elementary: 'K–5', Middle: '6–8', High: '9–12', Other: 'Other', Unknown: '?' };
      ALL_LEVELS.filter((l) => l !== 'Unknown').forEach((level) => {
        const btn = document.createElement('button');
        btn.className = state.selectedLevels.has(level) ? 'active' : 'ghost';
        btn.textContent = labels[level] || level;
        btn.title = level;
        btn.addEventListener('click', () => {
          state.selectedLevels.has(level) ? state.selectedLevels.delete(level) : state.selectedLevels.add(level);
          renderLevelFilter();
          renderSchools();
          updateView();
        });
        container.appendChild(btn);
      });
    }

    function getVisibleSchools() {
      return dashboardData.schools
        .filter((s) => {
          if (!state.selectedDistrictIds.has(s.district_id)) return false;
          if (state.schoolSearch && !s.name.toLowerCase().includes(state.schoolSearch)) return false;
          const level = s.school_level || 'Unknown';
          return state.selectedLevels.has(level) || (level !== 'Elementary' && level !== 'Middle' && level !== 'High' && state.selectedLevels.has('Other'));
        })
        .sort((a, b) => a.name.localeCompare(b.name));
    }

    function getActiveDistrictIds() {
      return Array.from(state.selectedDistrictIds);
    }

    function formatValue(value, format) {
      if (value === null || value === undefined) return '--';
      return format === 'percent' ? `${(value * 100).toFixed(1)}%` : Math.round(value).toLocaleString();
    }

    function formatAxisValue(value, format) {
      return format === 'percent' ? `${Math.round(value * 100)}%` : Number(value).toLocaleString();
    }
  })
  .catch(() => {
    document.getElementById('loading').textContent = 'Failed to load dashboard data. Please refresh the page.';
  });
  </script>
</body>
</html>
"""


def build_site(project_root: Path) -> None:
    site_dir = project_root / "site"
    site_dir.mkdir(parents=True, exist_ok=True)

    nces_payload = build_dashboard_payload(project_root)
    ospi_metrics = fetch_ospi_metrics(nces_payload["schools"], project_root=project_root)

    for record in nces_payload["records"]:
        match = ospi_metrics.get((record["school_id"], record["year"]), {})
        record["ela_proficiency_rate"] = match.get("ela_proficiency_rate")
        record["math_proficiency_rate"] = match.get("math_proficiency_rate")
        record["four_year_grad_rate"] = match.get("four_year_grad_rate")
        record["ela_growth_percentile"] = match.get("ela_growth_percentile")
        record["math_growth_percentile"] = match.get("math_growth_percentile")

    initial_school_ids = nces_payload.pop("initial_school_ids")

    dashboard_payload = {
        **nces_payload,
        "title": "Seattle Area School Dashboard",
        "subtitle": "Real NCES CCD build using the ten latest school-year releases from 2015-2016 through 2024-2025.",
        "metrics": METRIC_DEFINITIONS,
        "initial_state": {
            "selected_school_ids": initial_school_ids,
            "metric_key": "enrollment",
            "start_year": nces_payload["years"][0],
            "end_year":   nces_payload["years"][-1],
        },
    }

    (site_dir / "dashboard-data.json").write_text(
        json.dumps(dashboard_payload, indent=2),
        encoding="utf-8",
    )
    (site_dir / "index.html").write_text(
        HTML_TEMPLATE,
        encoding="utf-8",
    )
