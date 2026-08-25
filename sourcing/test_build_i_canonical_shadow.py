from __future__ import annotations

import unittest

import pandas as pd

from sourcing.build_i_canonical_shadow import build_canonical_i, build_event_seed


class CanonicalIShadowTests(unittest.TestCase):
    def test_b_only_row_becomes_interested(self) -> None:
        submissions = pd.DataFrame([{
            "submission_id": "b1", "submitted_at": "2026-08-20T10:00:00+00:00",
            "title": "Treasury Analyst", "company": "Example", "country": "Germany",
            "location": "Frankfurt", "job_url": "https://example.com/job",
            "user_comment": "Looks good", "source_domain": "example.com",
        }])
        out = build_canonical_i(pd.DataFrame(), submissions)
        self.assertEqual(len(out), 1)
        row = out.iloc[0]
        self.assertEqual(row["opportunity_id"], "b1")
        self.assertEqual(row["source_stream"], "B")
        self.assertEqual(row["action"], "Interested")
        self.assertEqual(row["user_comment"], "Looks good")

    def test_live_i_has_authority_over_b_for_existing_record(self) -> None:
        history = pd.DataFrame([{
            "opportunity_id": "same", "source_stream": "B", "first_seen_at": "2026-08-20",
            "decision_at": "2026-08-21", "title": "Treasury Manager", "company": "Example",
            "market": "Germany", "location": "Munich", "job_url": "https://old.example/job",
            "action": "Apply", "role_feedback": "Positive", "user_comment": "Applied",
            "application_stage": "Applied", "stage_updated_at": "2026-08-21",
        }])
        submissions = pd.DataFrame([{
            "submission_id": "same", "submitted_at": "2026-08-20", "title": "Wrong old title",
            "company": "Example", "country": "Germany", "location": "Berlin",
            "job_url": "https://new.example/job", "user_comment": "Original B comment",
        }])
        out = build_canonical_i(history, submissions)
        row = out.iloc[0]
        self.assertEqual(row["action"], "Apply")
        self.assertEqual(row["title"], "Treasury Manager")
        self.assertEqual(row["location"], "Munich")
        self.assertEqual(row["user_comment"], "Applied")
        self.assertEqual(row["application_stage"], "Applied")

    def test_b_fills_blank_metadata_without_overwriting_state(self) -> None:
        history = pd.DataFrame([{
            "opportunity_id": "same", "source_stream": "B", "first_seen_at": "2026-08-20",
            "decision_at": "2026-08-20", "title": "", "company": "", "action": "Interested",
        }])
        submissions = pd.DataFrame([{
            "submission_id": "same", "submitted_at": "2026-08-20", "title": "Treasury Analyst",
            "company": "Example", "country": "Germany", "job_url": "https://example.com/job",
        }])
        row = build_canonical_i(history, submissions).iloc[0]
        self.assertEqual(row["title"], "Treasury Analyst")
        self.assertEqual(row["company"], "Example")
        self.assertEqual(row["action"], "Interested")

    def test_event_seed_is_deterministic_and_captures_decision_stage(self) -> None:
        canonical = pd.DataFrame([{
            "opportunity_id": "x", "source_stream": "G", "first_seen_at": "2026-08-20T10:00:00+00:00",
            "decision_at": "2026-08-21T10:00:00+00:00", "action": "Apply",
            "company_feedback": "Positive", "role_feedback": "Positive", "user_comment": "Good",
            "application_stage": "Case", "stage_updated_at": "2026-08-24T10:00:00+00:00",
            "outcome_reason": "",
        }])
        first = build_event_seed(canonical)
        second = build_event_seed(canonical)
        self.assertEqual(list(first["event_id"]), list(second["event_id"]))
        self.assertEqual(set(first["event_type"]), {"opportunity_created", "decision", "application_stage"})
        stage = first[first["event_type"].eq("application_stage")].iloc[0]
        self.assertEqual(stage["application_stage"], "Case")


if __name__ == "__main__":
    unittest.main()
