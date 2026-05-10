"""PCA-based composite scores and rankings for Seattle Area School Dashboard.

Algorithm overview
------------------
Schools are ranked **within their level** (Elementary, Middle, High) using
separate PCAs. Other and Prekindergarten schools are excluded.

Per-level metric sets
---------------------
  Elementary / Middle : ela_proficiency_rate, math_proficiency_rate,
                        ela_growth_percentile, math_growth_percentile  (4 metrics)
  High                : all four above + four_year_grad_rate            (5 metrics)

Within each level pool:
1. Select most recent year per school (prefer 2023-2024 -> 2022-2023 -> 2021-2022).
2. Z-score each metric column using mean/std of non-null values only.
   Schools with a missing metric get z = 0 (imputed mean) and are flagged
   with data_completeness < 1.0.
3. SVD-based PCA; take PC1 as the composite.  Sign is flipped if needed so
   higher ELA proficiency -> higher composite score.
4. Rank within level pool descending (1 = best) -> overall_rank.
5. Rank within level x district -> district_rank.
"""

from __future__ import annotations

from typing import Any

import numpy as np

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RANKABLE_LEVELS: set[str] = {"Elementary", "Middle", "High"}

# Metrics used per level
METRICS_BY_LEVEL: dict[str, list[str]] = {
    "Elementary": [
        "ela_proficiency_rate",
        "math_proficiency_rate",
        "ela_growth_percentile",
        "math_growth_percentile",
    ],
    "Middle": [
        "ela_proficiency_rate",
        "math_proficiency_rate",
        "ela_growth_percentile",
        "math_growth_percentile",
    ],
    "High": [
        "ela_proficiency_rate",
        "math_proficiency_rate",
        "ela_growth_percentile",
        "math_growth_percentile",
        "four_year_grad_rate",
    ],
}

# Kept for backward-compat imports elsewhere (e.g. report script)
METRIC_KEYS: list[str] = [
    "ela_proficiency_rate",
    "math_proficiency_rate",
    "ela_growth_percentile",
    "math_growth_percentile",
    "four_year_grad_rate",
]

PREFERRED_YEARS: list[str] = ["2023-2024", "2022-2023", "2021-2022"]

METRIC_LABELS: dict[str, str] = {
    "ela_proficiency_rate": "ELA Proficiency",
    "math_proficiency_rate": "Math Proficiency",
    "ela_growth_percentile": "ELA Growth (SGP)",
    "math_growth_percentile": "Math Growth (SGP)",
    "four_year_grad_rate": "4-Year Grad Rate",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _select_reference_records(
    records: list[dict],
    school_ids: set[str],
) -> dict[str, dict]:
    """Return {school_id: record} using the most recent preferred year."""
    by_school: dict[str, dict[str, dict]] = {}
    for rec in records:
        sid = rec["school_id"]
        if sid not in school_ids:
            continue
        yr = rec.get("year", "")
        if yr in PREFERRED_YEARS:
            by_school.setdefault(sid, {})[yr] = rec

    selected: dict[str, dict] = {}
    for sid in school_ids:
        for yr in PREFERRED_YEARS:
            if sid in by_school and yr in by_school[sid]:
                selected[sid] = by_school[sid][yr]
                break
    return selected


def _collect_raw_matrix(
    school_list: list[dict],
    ref_records: dict[str, dict],
    metric_keys: list[str],
) -> tuple[list[str], np.ndarray, np.ndarray]:
    """Collect raw metric values into an (n, p) float array.

    Parameters
    ----------
    school_list  : schools in this level pool
    ref_records  : {school_id: record} for the full dataset
    metric_keys  : metrics to include (level-specific)

    Returns
    -------
    school_ids_ordered : list[str]  (schools that have a ref record)
    raw_matrix         : (n, p) float array, np.nan where missing
    observed_mask      : (n, p) bool array, True where originally non-null
    """
    school_ids_ordered = [s["id"] for s in school_list if s["id"] in ref_records]
    n = len(school_ids_ordered)
    p = len(metric_keys)

    raw = np.full((n, p), np.nan)
    observed = np.zeros((n, p), dtype=bool)

    for i, sid in enumerate(school_ids_ordered):
        rec = ref_records[sid]
        for j, key in enumerate(metric_keys):
            val = rec.get(key)
            if val is not None:
                raw[i, j] = float(val)
                observed[i, j] = True
            # else: remains np.nan / False  (will be imputed to z=0)

    return school_ids_ordered, raw, observed


def _zscore_matrix(
    raw: np.ndarray,
    observed: np.ndarray,
) -> tuple[np.ndarray, list[float], list[float]]:
    """Z-score each column using stats from observed values only.

    Missing entries (observed==False) are imputed with 0 (the column mean).

    Returns
    -------
    z     : (n, p) z-scored matrix with no NaNs
    means : per-column means  (over observed values)
    stds  : per-column stds   (over observed values, ddof=1)
    """
    n, p = raw.shape
    z = np.zeros((n, p))
    means: list[float] = []
    stds: list[float] = []

    for j in range(p):
        col = raw[:, j]
        obs_mask = observed[:, j]
        obs_vals = col[obs_mask]

        if len(obs_vals) < 2:
            means.append(float(np.nanmean(col)) if obs_mask.any() else 0.0)
            stds.append(1.0)
            continue

        mu = float(np.mean(obs_vals))
        sd = float(np.std(obs_vals, ddof=1))
        if sd == 0.0:
            sd = 1.0

        means.append(mu)
        stds.append(sd)

        for i in range(n):
            if obs_mask[i]:
                z[i, j] = (col[i] - mu) / sd
            else:
                z[i, j] = 0.0  # impute with mean

    return z, means, stds


def _run_pca(
    z: np.ndarray,
    metric_keys: list[str],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """SVD-based PCA; returns PC1 scores, all loadings matrix, PC1 loadings, variance explained.

    Sign convention: ELA proficiency loading is always positive
    (higher score = better school).

    Returns
    -------
    scores       : (n,)    PC1 composite scores
    all_loadings : (p, p)  full Vt matrix (row i = PCi loadings)
    pc1_loadings : (p,)    PC1 loadings after sign correction
    var_explained: float   fraction of variance explained by PC1
    """
    z_c = z - z.mean(axis=0)
    _U, S, Vt = np.linalg.svd(z_c, full_matrices=False)

    pc1_loadings = Vt[0].copy()
    scores = z_c @ pc1_loadings

    var_explained = float(S[0] ** 2 / np.sum(S ** 2))

    # Sign flip: ELA proficiency loading must be positive
    ela_idx = metric_keys.index("ela_proficiency_rate")
    if pc1_loadings[ela_idx] < 0:
        pc1_loadings = -pc1_loadings
        scores = -scores
        Vt[0] = -Vt[0]

    return scores, Vt, pc1_loadings, var_explained


def _percentile_from_rank(rank: int, total: int) -> float:
    """Convert rank (1=best) to percentile 0–100 (100=best)."""
    if total <= 1:
        return 100.0
    return round(100.0 * (total - rank) / (total - 1), 1)


def _rank_scores(
    id_score_pairs: list[tuple[str, float]],
) -> dict[str, tuple[int, float]]:
    """Return {school_id: (rank, percentile)} descending by score."""
    sorted_pairs = sorted(id_score_pairs, key=lambda x: x[1], reverse=True)
    total = len(sorted_pairs)
    result: dict[str, tuple[int, float]] = {}
    for rank, (sid, _) in enumerate(sorted_pairs, start=1):
        result[sid] = (rank, _percentile_from_rank(rank, total))
    return result


def _run_level_pca(
    level: str,
    school_list: list[dict],
    records: list[dict],
) -> dict[str, Any]:
    """Run PCA for one level pool; return analysis bundle."""
    metric_keys = METRICS_BY_LEVEL[level]
    school_ids = {s["id"] for s in school_list}
    ref_records = _select_reference_records(records, school_ids)

    if not ref_records:
        return {"rankings": {}, "loadings": None}

    school_ids_ordered, raw, observed = _collect_raw_matrix(
        school_list, ref_records, metric_keys
    )
    z, means, stds = _zscore_matrix(raw, observed)
    scores, all_loadings_vt, pc1_loadings, var_exp = _run_pca(z, metric_keys)

    completeness = observed.mean(axis=1)

    # Level-wide rankings
    id_score_pairs = list(zip(school_ids_ordered, scores.tolist()))
    level_rankings = _rank_scores(id_score_pairs)
    level_total = len(id_score_pairs)

    # District-within-level rankings
    district_by_school = {s["id"]: s.get("district_id", "") for s in school_list}
    district_groups: dict[str, list[tuple[str, float]]] = {}
    for sid, sc in id_score_pairs:
        did = district_by_school.get(sid, "")
        district_groups.setdefault(did, []).append((sid, sc))
    district_rankings = {
        did: _rank_scores(pairs) for did, pairs in district_groups.items()
    }

    # Majority reference year
    year_counts: dict[str, int] = {}
    for sid in school_ids_ordered:
        yr = ref_records[sid].get("year", "")
        year_counts[yr] = year_counts.get(yr, 0) + 1
    ref_year = max(year_counts, key=lambda y: year_counts[y]) if year_counts else ""

    # Per-school ranking dicts
    rankings: dict[str, dict[str, Any]] = {}
    for i, sid in enumerate(school_ids_ordered):
        did = district_by_school.get(sid, "")
        o_rank, o_pct = level_rankings[sid]
        d_rank, d_pct = district_rankings[did][sid]
        dc = float(completeness[i])

        # Raw input values and z-scores for transparency
        raw_inputs: dict[str, Any] = {}
        z_scores: dict[str, Any] = {}
        for j, key in enumerate(metric_keys):
            raw_inputs[key] = round(float(raw[i, j]), 4) if observed[i, j] else None
            z_scores[key] = round(float(z[i, j]), 4)

        rankings[sid] = {
            "composite_score": round(float(scores[i]), 4),
            "school_level": level,
            "overall_rank": o_rank,
            "overall_total": level_total,
            "overall_percentile": o_pct,
            "district_rank": d_rank,
            "district_total": len(district_groups[did]),
            "district_percentile": d_pct,
            "data_completeness": round(dc, 2),
            "partial_data": dc < 1.0,
            "reference_year": ref_records[sid].get("year", ""),
            "raw_inputs": raw_inputs,
            "z_scores": z_scores,
        }

    # Per-metric raw stats for report
    raw_stats = []
    for j, key in enumerate(metric_keys):
        obs_mask = observed[:, j]
        obs_vals = raw[:, j][obs_mask]
        raw_stats.append(
            {
                "key": key,
                "label": METRIC_LABELS[key],
                "n_observed": int(obs_mask.sum()),
                "n_total": len(school_ids_ordered),
                "raw_min": round(float(np.min(obs_vals)), 4) if len(obs_vals) else None,
                "raw_max": round(float(np.max(obs_vals)), 4) if len(obs_vals) else None,
                "raw_mean": round(float(means[j]), 4),
                "raw_std": round(float(stds[j]), 4),
                "z_min": round(float(np.min(z[:, j])), 3),
                "z_max": round(float(np.max(z[:, j])), 3),
                "z_mean": round(float(np.mean(z[:, j])), 3),
                "z_std": round(float(np.std(z[:, j])), 3),
            }
        )

    # All PCs variance
    z_c = z - z.mean(axis=0)
    _U2, S2, _Vt2 = np.linalg.svd(z_c, full_matrices=False)
    total_sv = float(np.sum(S2 ** 2))
    all_var = [round(float(s ** 2 / total_sv), 4) for s in S2]

    # Correlation matrix
    corr = np.corrcoef(z.T)
    corr_list = [[round(float(v), 3) for v in row] for row in corr]

    # Biplot data (PC1 vs PC2)
    pc2_scores = (z_c @ all_loadings_vt[1]).tolist() if len(all_loadings_vt) > 1 else [0.0] * len(school_ids_ordered)
    school_by_id_local = {s["id"]: s for s in school_list}
    biplot_data = [
        {
            "id": school_ids_ordered[i],
            "name": school_by_id_local.get(school_ids_ordered[i], {}).get("name", ""),
            "pc1": round(float(scores[i]), 3),
            "pc2": round(float(pc2_scores[i]), 3),
        }
        for i in range(len(school_ids_ordered))
    ]

    loadings_info = {
        "level": level,
        "metrics": metric_keys,
        "metric_labels": [METRIC_LABELS[k] for k in metric_keys],
        "pc1_loadings": [round(float(v), 4) for v in pc1_loadings],
        "all_loadings": [[round(float(v), 4) for v in row] for row in all_loadings_vt],
        "all_var": all_var,
        "variance_explained": round(var_exp, 4),
        "means": [round(float(v), 4) for v in means],
        "stds": [round(float(v), 4) for v in stds],
        "reference_year": ref_year,
        "n_schools": len(school_ids_ordered),
        "raw_stats": raw_stats,
        "corr": corr_list,
        "biplot_data": biplot_data,
    }

    return {"rankings": rankings, "loadings": loadings_info}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_rankings(
    records: list[dict],
    schools: list[dict],
) -> dict[str, dict[str, Any]]:
    """Compute PCA-based composite scores and rankings, separated by school level.

    Only Elementary, Middle, and High schools are ranked.
    Other / Prekindergarten schools are excluded.

    Returns
    -------
    dict mapping school_id -> {
        composite_score    : float,
        school_level       : str,
        overall_rank       : int   (1 = best within level),
        overall_total      : int   (number of schools in level pool),
        overall_percentile : float (0-100, 100 = top, within level),
        district_rank      : int   (within level x district),
        district_total     : int,
        district_percentile: float,
        data_completeness  : float (0.0-1.0),
        partial_data       : bool,
        reference_year     : str,
    }
    """
    # Split schools by level; exclude Other/Prekindergarten
    level_schools: dict[str, list[dict]] = {lvl: [] for lvl in RANKABLE_LEVELS}
    for s in schools:
        lvl = s.get("school_level", "")
        if lvl in RANKABLE_LEVELS:
            level_schools[lvl].append(s)

    result: dict[str, dict[str, Any]] = {}
    for level, school_list in level_schools.items():
        if not school_list:
            continue
        bundle = _run_level_pca(level, school_list, records)
        result.update(bundle["rankings"])

    return result


def compute_pca_loadings(
    records: list[dict],
    schools: list[dict],
) -> dict[str, Any]:
    """Return per-level PCA loadings and variance explained.

    Returns
    -------
    {
        "by_level": {
            "Elementary": { metrics, pc1_loadings, variance_explained, ... },
            "Middle":     { ... },
            "High":       { ... },
        }
    }
    """
    level_schools: dict[str, list[dict]] = {lvl: [] for lvl in RANKABLE_LEVELS}
    for s in schools:
        lvl = s.get("school_level", "")
        if lvl in RANKABLE_LEVELS:
            level_schools[lvl].append(s)

    by_level: dict[str, Any] = {}
    for level, school_list in level_schools.items():
        if not school_list:
            continue
        bundle = _run_level_pca(level, school_list, records)
        if bundle["loadings"] is not None:
            by_level[level] = bundle["loadings"]

    return {"by_level": by_level}
