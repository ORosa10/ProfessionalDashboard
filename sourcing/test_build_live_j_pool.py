from __future__ import annotations

import unittest

import pandas as pd

from sourcing.build_live_j_pool import build_live_pool


class LiveJPoolTests(unittest.TestCase):
    def _base(self, title: str = "Treasury Manager", company: str = "Example GmbH") -> pd.DataFrame:
        return pd.DataFrame([{
            "candidate_id": "c1", "job_id": "j1", "source_id": "src", "company": company,
            "title": title, "market": "Germany", "country_bucket": "Germany",
            "location": "Berlin", "job_url": "https://example.com/job", "date_posted": "2026-08-25",
        }])

    def _run(self, candidates: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        return build_live_pool(
            candidates,
            pd.DataFrame([{"opportunity_id": "j1", "fit": "Strong", "reasoning": "core treasury"}]),
            pd.DataFrame([{"opportunity_id": "j1", "actionable": True, "warnings": ""}]),
        )

    def test_strong_actionable_survives(self) -> None:
        pool, excluded = self._run(self._base())
        self.assertEqual(len(pool), 1)
        self.assertEqual(len(excluded), 0)

    def test_non_strong_is_removed(self) -> None:
        pool, excluded = build_live_pool(
            self._base(),
            pd.DataFrame([{"opportunity_id": "j1", "fit": "Moderate"}]),
            pd.DataFrame([{"opportunity_id": "j1", "actionable": True}]),
        )
        self.assertTrue(pool.empty)
        self.assertEqual(excluded.iloc[0]["excluded_reason"], "not_strong")

    def test_extreme_seniority_is_removed_without_blocking_manager(self) -> None:
        for title in ["Off-cycle M&A Intern", "Vice President, Investments", "M&A Director", "Senior Manager Treasury"]:
            pool, excluded = build_live_pool(
                self._base(title=title),
                pd.DataFrame([{"opportunity_id": "j1", "fit": "Strong"}]),
                pd.DataFrame([{"opportunity_id": "j1", "actionable": True}]),
            )
            self.assertTrue(pool.empty, title)
            self.assertTrue(excluded.iloc[0]["excluded_reason"].startswith("seniority:"), title)

        pool, _ = build_live_pool(
            self._base(title="M&A Manager"),
            pd.DataFrame([{"opportunity_id": "j1", "fit": "Strong"}]),
            pd.DataFrame([{"opportunity_id": "j1", "actionable": True}]),
        )
        self.assertEqual(len(pool), 1)

    def test_parser_placeholders_are_removed(self) -> None:
        pool, excluded = build_live_pool(
            self._base(company="Poslat nabídku na e-mail"),
            pd.DataFrame([{"opportunity_id": "j1", "fit": "Strong"}]),
            pd.DataFrame([{"opportunity_id": "j1", "actionable": True}]),
        )
        self.assertTrue(pool.empty)
        self.assertEqual(excluded.iloc[0]["excluded_reason"], "data_quality:invalid_company")

    def test_existing_actionability_blocker_is_respected(self) -> None:
        pool, excluded = build_live_pool(
            self._base(),
            pd.DataFrame([{"opportunity_id": "j1", "fit": "Strong"}]),
            pd.DataFrame([{"opportunity_id": "j1", "actionable": False, "blockers": "language:German fluent"}]),
        )
        self.assertTrue(pool.empty)
        self.assertIn("language:German fluent", excluded.iloc[0]["excluded_reason"])

    def test_explicit_non_target_location_is_removed_even_when_bucket_unresolved(self) -> None:
        candidates = self._base()
        candidates.loc[0, "market"] = "Multi-region"
        candidates.loc[0, "country_bucket"] = "Other / Unresolved"
        candidates.loc[0, "location"] = "Singapore"
        pool, excluded = self._run(candidates)
        self.assertTrue(pool.empty)
        self.assertEqual(excluded.iloc[0]["excluded_reason"], "geography:outside_target:Singapore")

    def test_unresolved_location_is_not_guessed(self) -> None:
        candidates = self._base()
        candidates.loc[0, "market"] = "Multi-region"
        candidates.loc[0, "country_bucket"] = "Other / Unresolved"
        candidates.loc[0, "location"] = "Global / flexible"
        pool, excluded = self._run(candidates)
        self.assertEqual(len(pool), 1)
        self.assertTrue(excluded.empty)

    def test_multi_location_with_target_option_is_kept(self) -> None:
        candidates = self._base()
        candidates.loc[0, "market"] = "Multi-region"
        candidates.loc[0, "country_bucket"] = "Other / Unresolved"
        candidates.loc[0, "location"] = "London / Singapore"
        pool, excluded = self._run(candidates)
        self.assertEqual(len(pool), 1)
        self.assertTrue(excluded.empty)


if __name__ == "__main__":
    unittest.main()
