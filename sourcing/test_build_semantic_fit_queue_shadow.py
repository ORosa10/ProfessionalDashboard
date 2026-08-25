from __future__ import annotations

import unittest

import pandas as pd

from sourcing.build_semantic_fit_queue_shadow import build_shadow_queue


class SemanticQueueShadowTests(unittest.TestCase):
    def test_existing_semantic_and_decided_history_are_excluded(self) -> None:
        candidates = pd.DataFrame([
            {"candidate_id": "c1", "job_id": "one", "company": "A", "title": "Treasury Analyst", "status": "Open", "country_bucket": "Germany"},
            {"candidate_id": "c2", "job_id": "two", "company": "B", "title": "Risk Analyst", "status": "Open", "country_bucket": "Germany"},
            {"candidate_id": "c3", "job_id": "three", "company": "C", "title": "Investment Analyst", "status": "Open", "country_bucket": "Germany"},
        ])
        semantic = pd.DataFrame([{"opportunity_id": "one", "fit": "Strong"}])
        history = pd.DataFrame([{"opportunity_id": "two", "action": "Apply"}])
        result = build_shadow_queue(candidates, semantic, history, limit=20)
        self.assertEqual(list(result["opportunity_id"]), ["three"])

    def test_language_requirement_is_not_a_c_queue_filter(self) -> None:
        candidates = pd.DataFrame([
            {
                "candidate_id": "c1",
                "job_id": "lang",
                "company": "Example",
                "title": "Market Risk Manager",
                "status": "Open",
                "country_bucket": "Germany",
                "description_en": "Excellent role content. Requires native German C2.",
            }
        ])
        result = build_shadow_queue(candidates, pd.DataFrame(), pd.DataFrame(), limit=20)
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["opportunity_id"], "lang")

    def test_closed_candidate_does_not_consume_new_semantic_review(self) -> None:
        candidates = pd.DataFrame([
            {"candidate_id": "c1", "job_id": "open", "company": "A", "title": "Treasury", "status": "Open", "country_bucket": "Austria"},
            {"candidate_id": "c2", "job_id": "closed", "company": "B", "title": "Treasury", "status": "Closed", "country_bucket": "Austria"},
        ])
        result = build_shadow_queue(candidates, pd.DataFrame(), pd.DataFrame(), limit=20)
        self.assertEqual(list(result["opportunity_id"]), ["open"])

    def test_job_id_is_preserved_for_migration_compatibility(self) -> None:
        candidates = pd.DataFrame([
            {"candidate_id": "shadow-hash", "job_id": "legacy-job-id", "company": "A", "title": "Treasury", "status": "Open", "country_bucket": "Sweden"},
        ])
        result = build_shadow_queue(candidates, pd.DataFrame(), pd.DataFrame(), limit=20)
        self.assertEqual(result.iloc[0]["opportunity_id"], "legacy-job-id")
        self.assertEqual(result.iloc[0]["candidate_id"], "shadow-hash")

    def test_zero_limit_emits_full_unresolved_backlog(self) -> None:
        candidates = pd.DataFrame([
            {"candidate_id": f"c{i}", "job_id": f"job-{i}", "company": "A", "title": f"Role {i}", "status": "Open", "country_bucket": "Germany"}
            for i in range(250)
        ])
        result = build_shadow_queue(candidates, pd.DataFrame(), pd.DataFrame(), limit=0)
        self.assertEqual(len(result), 250)
        self.assertEqual(set(result["opportunity_id"]), {f"job-{i}" for i in range(250)})

    def test_description_for_fit_is_not_truncated(self) -> None:
        description = "x" * 7000 + " CORE RESPONSIBILITIES AT THE END"
        candidates = pd.DataFrame([
            {
                "candidate_id": "c-long",
                "job_id": "long",
                "company": "Example",
                "title": "Finance Role",
                "status": "Open",
                "country_bucket": "Germany",
                "description_en": description,
            }
        ])
        result = build_shadow_queue(candidates, pd.DataFrame(), pd.DataFrame(), limit=0)
        self.assertEqual(result.iloc[0]["description_for_fit"], description)
        self.assertTrue(result.iloc[0]["description_for_fit"].endswith("CORE RESPONSIBILITIES AT THE END"))


if __name__ == "__main__":
    unittest.main()
