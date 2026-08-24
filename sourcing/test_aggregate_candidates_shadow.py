from __future__ import annotations

import unittest

import pandas as pd

from sourcing.aggregate_candidates_shadow import OUTPUT_COLUMNS, aggregate_frames, build_diagnostics


class ShadowAggregatorTests(unittest.TestCase):
    def test_empty_inputs_return_stable_schema(self) -> None:
        result = aggregate_frames([])
        self.assertTrue(result.empty)
        self.assertEqual(list(result.columns), OUTPUT_COLUMNS)

    def test_same_url_across_streams_is_merged_after_tracking_cleanup(self) -> None:
        board = pd.DataFrame([
            {
                "job_id": "board-1",
                "company": "Example AG",
                "title": "Treasury Analyst",
                "location": "Zurich, Switzerland",
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
                "location": "Zurich, Switzerland",
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
        self.assertEqual(row["country_bucket"], "Switzerland")

    def test_job_identifying_query_parameter_is_not_dropped(self) -> None:
        left = pd.DataFrame([
            {
                "job_id": "a",
                "company": "Example AG",
                "title": "Treasury Analyst",
                "location": "Zurich",
                "job_url": "https://example.com/job?jobId=111&utm_source=feed",
            }
        ])
        right = pd.DataFrame([
            {
                "job_id": "b",
                "company": "Example AG",
                "title": "Treasury Analyst",
                "location": "Zurich",
                "job_url": "https://example.com/job?jobId=222&utm_source=feed",
            }
        ])
        result = aggregate_frames([("left", left), ("right", right)])
        self.assertEqual(len(result), 2)

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

    def test_iso_country_tokens_do_not_cross_match(self) -> None:
        frame = pd.DataFrame([
            {"job_id": "dk", "company": "D", "title": "Treasury", "market": "Multi-region", "location": "Copenhagen, Europe, DK"},
            {"job_id": "de", "company": "G", "title": "Risk", "market": "Multi-region", "location": "Frankfurt am Main, Europe, DE"},
        ])
        result = aggregate_frames([("test", frame)]).set_index("job_id")
        self.assertEqual(result.loc["dk", "country_bucket"], "Denmark")
        self.assertEqual(result.loc["de", "country_bucket"], "Germany")

    def test_rows_without_company_or_title_are_not_candidates(self) -> None:
        frame = pd.DataFrame([
            {"job_id": "good", "company": "Example", "title": "Risk Analyst"},
            {"job_id": "missing-company", "company": "", "title": "Risk Analyst"},
            {"job_id": "missing-title", "company": "Example", "title": ""},
        ])
        result = aggregate_frames([("test", frame)])
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["job_id"], "good")

    def test_diagnostics_report_raw_source_and_country_coverage(self) -> None:
        de = pd.DataFrame([
            {"job_id": "de1", "company": "A", "title": "Treasury Analyst", "location": "Frankfurt, Germany"},
            {"job_id": "de2", "company": "B", "title": "Risk Analyst", "location": "Munich, Germany"},
        ])
        uk = pd.DataFrame([
            {"job_id": "uk1", "company": "C", "title": "Investment Analyst", "location": "London, United Kingdom"},
        ])
        frames = [("corporate", de), ("board", uk)]
        candidates = aggregate_frames(frames)
        diagnostics = build_diagnostics(frames, candidates)

        source = diagnostics[diagnostics["dimension"].eq("source")].set_index("value")
        country = diagnostics[diagnostics["dimension"].eq("country")].set_index("value")
        self.assertEqual(int(source.loc["corporate", "raw_rows"]), 2)
        self.assertEqual(int(source.loc["board", "candidate_count"]), 1)
        self.assertEqual(int(country.loc["Germany", "candidate_count"]), 2)
        self.assertEqual(int(country.loc["United Kingdom", "candidate_count"]), 1)


if __name__ == "__main__":
    unittest.main()
