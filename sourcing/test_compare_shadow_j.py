from __future__ import annotations

import unittest

import pandas as pd

from sourcing.compare_shadow_j import compare_live_to_shadow


class CompareShadowJTests(unittest.TestCase):
    def test_explains_kept_moderate_blocked_missing_and_history(self) -> None:
        live = pd.DataFrame([
            {"job_id": "keep", "company": "A", "title": "Keep", "market": "Germany", "semantic_fit": "Strong"},
            {"job_id": "moderate", "company": "B", "title": "Moderate", "market": "UK", "semantic_fit": "Moderate"},
            {"job_id": "blocked", "company": "C", "title": "Blocked", "market": "Germany", "semantic_fit": "Strong"},
            {"job_id": "missing", "company": "D", "title": "Missing", "market": "Austria", "semantic_fit": "Strong"},
            {"job_id": "applied", "company": "E", "title": "Applied", "market": "Germany", "semantic_fit": "Strong"},
        ])
        candidates = pd.DataFrame([{"job_id": x} for x in ["keep", "moderate", "blocked", "applied"]])
        semantic = pd.DataFrame([
            {"opportunity_id": "keep", "fit": "Strong"},
            {"opportunity_id": "moderate", "fit": "Moderate"},
            {"opportunity_id": "blocked", "fit": "Strong"},
            {"opportunity_id": "applied", "fit": "Strong"},
        ])
        actionability = pd.DataFrame([
            {"opportunity_id": "keep", "actionable": True, "blockers": ""},
            {"opportunity_id": "moderate", "actionable": True, "blockers": ""},
            {"opportunity_id": "blocked", "actionable": False, "blockers": "language:German C1"},
            {"opportunity_id": "applied", "actionable": True, "blockers": ""},
        ])
        history = pd.DataFrame([{"opportunity_id": "applied", "action": "Apply"}])
        shadow_j = pd.DataFrame([{"opportunity_id": "keep", "company": "A", "title": "Keep"}])

        report, new = compare_live_to_shadow(live, candidates, semantic, actionability, history, shadow_j)
        by_id = report.set_index("job_id")
        self.assertEqual(by_id.loc["keep", "explanation"], "kept_in_shadow_j")
        self.assertEqual(by_id.loc["moderate", "explanation"], "semantic_moderate_excluded")
        self.assertEqual(by_id.loc["blocked", "explanation"], "actionability_blocked")
        self.assertEqual(by_id.loc["missing", "explanation"], "missing_from_shadow_g_sources")
        self.assertEqual(by_id.loc["applied", "explanation"], "history_apply_removed_from_working_queue")
        self.assertTrue(new.empty)

    def test_reports_new_shadow_j_roles(self) -> None:
        live = pd.DataFrame([{"job_id": "old", "company": "Old", "title": "Old"}])
        shadow_j = pd.DataFrame([
            {"opportunity_id": "old", "company": "Old", "title": "Old"},
            {
                "opportunity_id": "new", "company": "New", "title": "New",
                "country_bucket": "Switzerland", "company_rating": "A",
                "selection_origin": "quota:Switzerland", "priority_order": 1,
            },
        ])
        report, new = compare_live_to_shadow(
            live,
            pd.DataFrame([{"job_id": "old"}]),
            pd.DataFrame(),
            pd.DataFrame(),
            pd.DataFrame(),
            shadow_j,
        )
        self.assertEqual(len(report), 1)
        self.assertEqual(list(new["opportunity_id"]), ["new"])
        self.assertEqual(new.iloc[0]["explanation"], "new_shadow_j_role")


if __name__ == "__main__":
    unittest.main()
