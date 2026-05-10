"""Unit tests for seattle_schools_dashboard.rankings."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seattle_schools_dashboard.rankings import (
    METRICS_BY_LEVEL,
    compute_pca_loadings,
    compute_rankings,
)


def _make_school(sid, district_id="d1", level="Elementary"):
    return {"id": sid, "name": sid, "district_id": district_id, "school_level": level}


def _make_record(sid, year="2023-2024", **metrics):
    rec = {"school_id": sid, "year": year}
    all_keys = [
        "ela_proficiency_rate", "math_proficiency_rate",
        "ela_growth_percentile", "math_growth_percentile",
        "four_year_grad_rate",
    ]
    for k in all_keys:
        rec[k] = metrics.get(k)
    return rec


class TestCompositeScoreDirection(unittest.TestCase):
    """School A (high proficiency) should rank above school B (low proficiency)."""

    def test_composite_scores_higher_for_better_schools(self):
        schools = [_make_school("A"), _make_school("B"), _make_school("C")]
        records = [
            _make_record(
                "A",
                ela_proficiency_rate=0.90,
                math_proficiency_rate=0.85,
                ela_growth_percentile=70,
                math_growth_percentile=72,
            ),
            _make_record(
                "B",
                ela_proficiency_rate=0.50,
                math_proficiency_rate=0.45,
                ela_growth_percentile=50,
                math_growth_percentile=52,
            ),
            _make_record(
                "C",
                ela_proficiency_rate=0.20,
                math_proficiency_rate=0.18,
                ela_growth_percentile=35,
                math_growth_percentile=33,
            ),
        ]
        rankings = compute_rankings(records, schools)
        self.assertGreater(rankings["A"]["composite_score"], rankings["B"]["composite_score"])
        self.assertGreater(rankings["B"]["composite_score"], rankings["C"]["composite_score"])


class TestDistrictRanking(unittest.TestCase):
    """Within a level+district, the school with highest composite gets district_rank=1."""

    def test_ranking_within_district(self):
        schools = [
            _make_school("X1", district_id="dx"),
            _make_school("X2", district_id="dx"),
            _make_school("X3", district_id="dx"),
        ]
        records = [
            _make_record("X1", ela_proficiency_rate=0.80, math_proficiency_rate=0.75,
                         ela_growth_percentile=65, math_growth_percentile=66),
            _make_record("X2", ela_proficiency_rate=0.55, math_proficiency_rate=0.50,
                         ela_growth_percentile=50, math_growth_percentile=51),
            _make_record("X3", ela_proficiency_rate=0.30, math_proficiency_rate=0.25,
                         ela_growth_percentile=38, math_growth_percentile=37),
        ]
        rankings = compute_rankings(records, schools)
        # X1 should be district_rank 1 and overall_rank 1
        self.assertEqual(rankings["X1"]["district_rank"], 1)
        self.assertEqual(rankings["X1"]["overall_rank"], 1)
        self.assertEqual(rankings["X3"]["district_rank"], 3)
        # Only one district in pool, so district_rank == overall_rank
        for sid in ("X1", "X2", "X3"):
            self.assertEqual(rankings[sid]["district_rank"], rankings[sid]["overall_rank"])


class TestMissingMetricImputed(unittest.TestCase):
    """School with null metrics still gets a composite score (imputed to mean z=0)."""

    def test_missing_metric_imputed(self):
        # Three high schools: one missing ela_growth, one missing math_growth
        schools = [
            _make_school("H1", level="High"),
            _make_school("H2", level="High"),
            _make_school("H3", level="High"),
        ]
        records = [
            _make_record("H1", ela_proficiency_rate=0.75, math_proficiency_rate=0.70,
                         ela_growth_percentile=58, math_growth_percentile=60,
                         four_year_grad_rate=0.90),
            _make_record("H2", ela_proficiency_rate=0.65, math_proficiency_rate=0.60,
                         ela_growth_percentile=None,  # missing — imputed to z=0
                         math_growth_percentile=54,
                         four_year_grad_rate=0.85),
            _make_record("H3", ela_proficiency_rate=0.50, math_proficiency_rate=0.45,
                         ela_growth_percentile=48, math_growth_percentile=46,
                         four_year_grad_rate=None),  # missing — imputed to z=0
        ]
        rankings = compute_rankings(records, schools)
        for sid in ("H1", "H2", "H3"):
            self.assertIn(sid, rankings)
            score = rankings[sid]["composite_score"]
            self.assertIsInstance(score, float)
            self.assertFalse(score != score, f"{sid} composite_score is NaN")

        # H2 has partial data for ela_growth
        self.assertTrue(rankings["H2"]["partial_data"])
        # H1 has all 5 metrics observed
        self.assertFalse(rankings["H1"]["partial_data"])


class TestLoadingsSign(unittest.TestCase):
    """ELA proficiency loading must be positive (higher ELA -> higher score)."""

    def test_loadings_sign(self):
        schools = [_make_school(f"S{i}") for i in range(6)]
        ela_vals = [0.90, 0.80, 0.65, 0.50, 0.35, 0.20]
        records = [
            _make_record(
                f"S{i}",
                ela_proficiency_rate=ela_vals[i],
                math_proficiency_rate=ela_vals[i] - 0.05,
                ela_growth_percentile=int(30 + ela_vals[i] * 40),
                math_growth_percentile=int(28 + ela_vals[i] * 40),
            )
            for i in range(6)
        ]
        loadings = compute_pca_loadings(records, schools)
        elem_loadings = loadings["by_level"]["Elementary"]
        ela_idx = elem_loadings["metrics"].index("ela_proficiency_rate")
        self.assertGreater(
            elem_loadings["pc1_loadings"][ela_idx],
            0,
            "ELA proficiency loading should be positive",
        )


class TestOverallPercentileRange(unittest.TestCase):
    """All overall_percentile values must be in [0, 100]."""

    def test_overall_percentile_range(self):
        n = 10
        schools = [_make_school(f"P{i}") for i in range(n)]
        records = [
            _make_record(
                f"P{i}",
                ela_proficiency_rate=0.3 + i * 0.06,
                math_proficiency_rate=0.25 + i * 0.06,
                ela_growth_percentile=35 + i * 4,
                math_growth_percentile=33 + i * 4,
            )
            for i in range(n)
        ]
        rankings = compute_rankings(records, schools)
        for sid, info in rankings.items():
            pct = info["overall_percentile"]
            self.assertGreaterEqual(pct, 0.0, f"{sid} percentile {pct} < 0")
            self.assertLessEqual(pct, 100.0, f"{sid} percentile {pct} > 100")


class TestLevelSeparation(unittest.TestCase):
    """Elementary, Middle, High schools are ranked in separate pools; Other excluded."""

    def test_levels_ranked_separately(self):
        schools = [
            _make_school("E1", level="Elementary"),
            _make_school("E2", level="Elementary"),
            _make_school("M1", level="Middle"),
            _make_school("M2", level="Middle"),
            _make_school("H1", level="High"),
            _make_school("H2", level="High"),
            _make_school("O1", level="Other"),       # excluded
            _make_school("P1", level="Prekindergarten"),  # excluded
        ]
        records = [
            _make_record("E1", ela_proficiency_rate=0.80, math_proficiency_rate=0.75,
                         ela_growth_percentile=65, math_growth_percentile=66),
            _make_record("E2", ela_proficiency_rate=0.40, math_proficiency_rate=0.35,
                         ela_growth_percentile=42, math_growth_percentile=40),
            _make_record("M1", ela_proficiency_rate=0.72, math_proficiency_rate=0.68,
                         ela_growth_percentile=60, math_growth_percentile=62),
            _make_record("M2", ela_proficiency_rate=0.45, math_proficiency_rate=0.40,
                         ela_growth_percentile=46, math_growth_percentile=44),
            _make_record("H1", ela_proficiency_rate=0.78, math_proficiency_rate=0.73,
                         ela_growth_percentile=63, math_growth_percentile=65,
                         four_year_grad_rate=0.92),
            _make_record("H2", ela_proficiency_rate=0.50, math_proficiency_rate=0.45,
                         ela_growth_percentile=50, math_growth_percentile=48,
                         four_year_grad_rate=0.78),
            _make_record("O1", ela_proficiency_rate=0.60, math_proficiency_rate=0.55,
                         ela_growth_percentile=55, math_growth_percentile=53),
            _make_record("P1", ela_proficiency_rate=0.55, math_proficiency_rate=0.50,
                         ela_growth_percentile=52, math_growth_percentile=50),
        ]
        rankings = compute_rankings(records, schools)

        # Other and Prekindergarten are excluded
        self.assertNotIn("O1", rankings)
        self.assertNotIn("P1", rankings)

        # Each level pool has overall_total matching its level size
        self.assertEqual(rankings["E1"]["overall_total"], 2)
        self.assertEqual(rankings["M1"]["overall_total"], 2)
        self.assertEqual(rankings["H1"]["overall_total"], 2)

        # Within each level, ranks are 1 and 2
        self.assertIn(rankings["E1"]["overall_rank"], (1, 2))
        self.assertIn(rankings["M1"]["overall_rank"], (1, 2))
        self.assertIn(rankings["H1"]["overall_rank"], (1, 2))

        # school_level field is populated correctly
        self.assertEqual(rankings["E1"]["school_level"], "Elementary")
        self.assertEqual(rankings["M1"]["school_level"], "Middle")
        self.assertEqual(rankings["H1"]["school_level"], "High")

    def test_high_school_uses_grad_rate(self):
        """High schools use 5 metrics; grad_rate is null for non-high — not imputed as 0."""
        schools = [
            _make_school("H1", level="High"),
            _make_school("H2", level="High"),
            _make_school("H3", level="High"),
        ]
        records = [
            _make_record("H1", ela_proficiency_rate=0.80, math_proficiency_rate=0.75,
                         ela_growth_percentile=65, math_growth_percentile=66,
                         four_year_grad_rate=0.95),
            _make_record("H2", ela_proficiency_rate=0.60, math_proficiency_rate=0.55,
                         ela_growth_percentile=55, math_growth_percentile=54,
                         four_year_grad_rate=0.80),
            _make_record("H3", ela_proficiency_rate=0.40, math_proficiency_rate=0.35,
                         ela_growth_percentile=42, math_growth_percentile=40,
                         four_year_grad_rate=0.60),
        ]
        loadings = compute_pca_loadings(records, schools)
        self.assertIn("High", loadings["by_level"])
        high = loadings["by_level"]["High"]
        self.assertIn("four_year_grad_rate", high["metrics"])
        # With all real grad rates, the loading should be meaningfully positive
        grad_idx = high["metrics"].index("four_year_grad_rate")
        self.assertGreater(high["pc1_loadings"][grad_idx], 0.0)

    def test_elementary_excludes_grad_rate(self):
        """Elementary PCA uses only 4 metrics — no four_year_grad_rate."""
        schools = [_make_school(f"E{i}") for i in range(5)]
        records = [
            _make_record(f"E{i}", ela_proficiency_rate=0.3 + i * 0.1,
                         math_proficiency_rate=0.25 + i * 0.1,
                         ela_growth_percentile=40 + i * 5,
                         math_growth_percentile=38 + i * 5)
            for i in range(5)
        ]
        loadings = compute_pca_loadings(records, schools)
        self.assertIn("Elementary", loadings["by_level"])
        elem = loadings["by_level"]["Elementary"]
        self.assertNotIn("four_year_grad_rate", elem["metrics"])
        self.assertEqual(len(elem["metrics"]), 4)


if __name__ == "__main__":
    unittest.main()
