from __future__ import annotations

import unittest

import pandas as pd

from sourcing.aggregate_candidates_shadow import OUTPUT_COLUMNS, aggregate_frames


class ShadowAggregatorTests(unittest.TestCase):
    def test_empty_inputs_return_stable_schema(self) -> None:
        result = aggregate_frames([])
        self.assertTrue(result.empty)
        self.assertEqual(list(result.columns), OUTPUT_COLUMNS)

    def test_same_url_across_streams_is_merged(self) -> None:
        board = pd.DataFrame([
            {
                "job_id": "board-1",
                "company": "Example AG",
                "title": "Treasury Analyst",
                "location": "Zurich",
                "job_url": "https://example.com/jobs/123?utm_source=board",
                "description_en": "Short description",
                "source_id": "board-x",
                "last_seen_at": "2026-08-23T10:00:00+00:00",
                "status": "Open",
            }
        ])
        company = pd.DataFrame([
            {
                "job_id": "company-9",
                "canonical_company_id": "example-ag",
                "company": "Example AG",
                "title": "Treasury Analyst",
                "location": "Zurich",
                "job_url": "https://example.com/jobs/123",
                "description_en": "A much richer description of the treasury analyst vacancy.",
                "source_id": "example-careers",
                "last_seen_at": "2026-08-24T10:00:00+00:00",
                "status": "Open",
            }
        ])

        result = aggregate_frames([("board", board), ("company", company)])

        self.assertEqual(len(result), 1)
        row = result.iloc[0]
        self.assertEqual(row["source_count"], 2)
        self.assertEqual(row["duplicate_count"], 1)
        self.assertIn("board", row["source_streams"])
        self.assertIn("company", row["source_streams"])
        self.assertEqual(row["description_en"], "A much richer description of the treasury analyst vacancy.")
        self.assertEqual(row["last_seen_at"], "2026-08-24T10:00:00+00:00")

    def test_different_urls_are_not_aggressively_merged(self) -> None:
        left = pd.DataFrame([
            {
                "job_id": "a",
                "company": "Example AG",
                "title": "Treasury Analyst",
                "location": "Zurich",
                "job_url": "https://board.example/jobs/a",
            }
        ])
        right = pd.DataFrame([
            {
                "job_id": "b",
                "company": "Example AG",
                "title": "Treasury Analyst",
                "location": "Zurich",
                "job_url": "https://careers.example/jobs/b",
            }
        ])

        result = aggregate_frames([("board", left), ("company", right)])
        self.assertEqual(len(result), 2)

    def test_rows_without_company_or_title_are_not_candidates(self) -> None:
        frame = pd.DataFrame([
            {"job_id": "good", "company": "Example", "title": "Risk Analyst"},
            {"job_id": "missing-company", "company": "", "title": "Risk Analyst"},
            {"job_id": "missing-title", "company": "Example", "title": ""},
        ])
        result = aggregate_frames([("test", frame)])
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["job_id"], "good")


if __name__ == "__main__":
    unittest.main()
