from __future__ import annotations

import unittest

import pandas as pd

from sourcing.build_semantic_fit_shadow import build_semantic_shadow


class SemanticShadowTests(unittest.TestCase):
    def test_existing_canonical_semantic_wins_over_curated(self) -> None:
        canonical = pd.DataFrame([
            {"opportunity_id": "x", "fit": "Strong", "reasoning": "canonical", "generated_at": "2026-08-20"},
        ])
        curated = pd.DataFrame([
            {"job_id": "x", "semantic_fit": "Moderate", "semantic_reasoning": "curated"},
        ])
        result = build_semantic_shadow(canonical, curated).set_index("opportunity_id")
        self.assertEqual(result.loc["x", "fit"], "Strong")
        self.assertEqual(result.loc["x", "reasoning"], "canonical")
        self.assertEqual(result.loc["x", "semantic_source"], "canonical_existing")

    def test_missing_curated_role_is_backfilled(self) -> None:
        canonical = pd.DataFrame([
            {"opportunity_id": "x", "fit": "Strong", "reasoning": "canonical"},
        ])
        curated = pd.DataFrame([
            {"job_id": "y", "semantic_fit": "Strong", "semantic_reasoning": "curated y", "date_posted": "2026-08-21"},
        ])
        result = build_semantic_shadow(canonical, curated).set_index("opportunity_id")
        self.assertIn("y", result.index)
        self.assertEqual(result.loc["y", "semantic_source"], "curated_j_backfill")
        self.assertEqual(result.loc["y", "reasoning"], "curated y")

    def test_invalid_fit_is_not_promoted_to_canonical_shadow(self) -> None:
        canonical = pd.DataFrame([
            {"opportunity_id": "x", "fit": "Unknown", "reasoning": "bad"},
        ])
        curated = pd.DataFrame([
            {"job_id": "y", "semantic_fit": "", "semantic_reasoning": "blank"},
        ])
        result = build_semantic_shadow(canonical, curated)
        self.assertTrue(result.empty)


if __name__ == "__main__":
    unittest.main()
