from __future__ import annotations

import unittest

import pandas as pd

from sourcing.prepare_j_candidates_shadow import prepare_j_candidates


class PrepareJCandidatesShadowTests(unittest.TestCase):
    def test_manual_b_duplicate_is_removed_by_role_identity(self) -> None:
        candidates = pd.DataFrame([
            {"candidate_id": "1", "company": "Porsche Holding", "canonical_company_id": "porsche-holding", "title": "Group Treasury Specialist - Markets", "job_url": "https://example.com/job/1"},
            {"candidate_id": "2", "company": "Other Co", "canonical_company_id": "other", "title": "Treasury Analyst", "job_url": "https://example.com/job/2"},
        ])
        manual = pd.DataFrame([
            {"company": "Porsche Holding", "canonical_company_id": "porsche-holding", "title": "Group Treasury Specialist - Markets", "job_url": "https://different.example/job/99"},
        ])
        allowed, excluded = prepare_j_candidates(candidates, pd.DataFrame(), manual, pd.DataFrame(columns=["company", "aliases_entities", "company_category"]))
        self.assertEqual(allowed["candidate_id"].tolist(), ["2"])
        self.assertEqual(excluded.iloc[0]["excluded_reason"], "manual_B_already_applied")

    def test_comment_only_history_counts_as_reviewed(self) -> None:
        candidates = pd.DataFrame([
            {"candidate_id": "1", "company": "A Co", "title": "M&A Analyst", "job_url": "https://example.com/job/1"},
        ])
        history = pd.DataFrame([
            {"company": "A Co", "title": "M&A Analyst", "job_url": "https://example.com/job/1", "action": "New", "company_feedback": "Not rated", "role_feedback": "Not rated", "user_comment": "Kind of boring", "application_stage": ""},
        ])
        allowed, excluded = prepare_j_candidates(candidates, history, pd.DataFrame(), pd.DataFrame(columns=["company", "aliases_entities", "company_category"]))
        self.assertTrue(allowed.empty)
        self.assertEqual(excluded.iloc[0]["excluded_reason"], "already_reviewed_history")

    def test_big_four_is_separate_batch(self) -> None:
        candidates = pd.DataFrame([
            {"candidate_id": "1", "company": "Deloitte", "title": "CDD Consultant", "job_url": "https://example.com/job/1"},
            {"candidate_id": "2", "company": "Industrial Co", "title": "Treasury Analyst", "job_url": "https://example.com/job/2"},
        ])
        universe = pd.DataFrame([
            {"company": "Deloitte", "aliases_entities": "", "company_category": "Big Four", "canonical_company_id": "deloitte"},
            {"company": "Industrial Co", "aliases_entities": "", "company_category": "Corporate", "canonical_company_id": "industrial-co"},
        ])
        allowed, excluded = prepare_j_candidates(candidates, pd.DataFrame(), pd.DataFrame(), universe)
        self.assertEqual(allowed["candidate_id"].tolist(), ["2"])
        self.assertEqual(excluded.iloc[0]["excluded_reason"], "big4_separate_batch")


if __name__ == "__main__":
    unittest.main()
