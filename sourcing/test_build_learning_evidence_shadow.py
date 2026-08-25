from __future__ import annotations

import unittest

import pandas as pd

from sourcing.build_learning_evidence_shadow import build_a_evidence, build_c_evidence, build_h_evidence


class LearningEvidenceShadowTests(unittest.TestCase):
    def test_b_interested_is_c_positive_but_not_a_positive(self) -> None:
        history = pd.DataFrame([{
            "opportunity_id": "b1", "source_stream": "B", "decision_at": "2026-08-20",
            "company": "Example", "title": "Treasury Analyst", "action": "Interested",
            "company_feedback": "Not rated", "role_feedback": "Not rated",
        }])
        a_events, a_summary = build_a_evidence(history)
        c_events = build_c_evidence(history)
        self.assertTrue(a_events.empty)
        self.assertTrue(a_summary.empty)
        self.assertEqual(len(c_events), 1)
        self.assertEqual(c_events.iloc[0]["c_signal"], "positive")

    def test_explicit_company_feedback_only_drives_a_evidence(self) -> None:
        history = pd.DataFrame([
            {"opportunity_id": "1", "decision_at": "2026-08-20", "canonical_company_id": "x", "company": "X", "company_category": "Bank", "company_feedback": "Positive", "action": "Apply"},
            {"opportunity_id": "2", "decision_at": "2026-08-21", "canonical_company_id": "x", "company": "X", "company_category": "Bank", "company_feedback": "Negative", "action": "Skip"},
            {"opportunity_id": "3", "decision_at": "2026-08-22", "canonical_company_id": "y", "company": "Y", "company_feedback": "Not rated", "action": "Apply"},
        ])
        events, summary = build_a_evidence(history)
        self.assertEqual(len(events), 2)
        row = summary[summary["canonical_company_id"].eq("x")].iloc[0]
        self.assertEqual(int(row["positive"]), 1)
        self.assertEqual(int(row["negative"]), 1)
        self.assertFalse(summary["canonical_company_id"].eq("y").any())

    def test_explicit_role_feedback_overrides_action_fallback(self) -> None:
        history = pd.DataFrame([{
            "opportunity_id": "x", "decision_at": "2026-08-20", "title": "Role",
            "action": "Apply", "role_feedback": "Neutral",
        }])
        result = build_c_evidence(history)
        self.assertEqual(result.iloc[0]["c_signal"], "neutral")

    def test_h_uses_application_stage_only(self) -> None:
        history = pd.DataFrame([
            {"opportunity_id": "1", "company": "X", "canonical_company_id": "x", "company_category": "Bank", "market": "Germany", "application_stage": "Applied"},
            {"opportunity_id": "2", "company": "X", "canonical_company_id": "x", "company_category": "Bank", "market": "Germany", "application_stage": "1st interview"},
            {"opportunity_id": "3", "company": "Y", "market": "Austria", "action": "Skip", "application_stage": ""},
        ])
        events, summary = build_h_evidence(history)
        self.assertEqual(len(events), 2)
        self.assertFalse(events["opportunity_id"].eq("3").any())
        company = summary[(summary["dimension"].eq("company")) & (summary["value"].eq("x"))].iloc[0]
        self.assertEqual(int(company["applications"]), 2)
        self.assertEqual(int(company["reached_interview"]), 1)


if __name__ == "__main__":
    unittest.main()
