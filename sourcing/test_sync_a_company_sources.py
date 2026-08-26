from __future__ import annotations

# Regression contract for explicit A rating -> G company-source behaviour.

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from sourcing.sync_a_company_sources import SOURCE_COLUMNS, sync_company_sources


class SyncACompanySourcesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        universe = pd.DataFrame([
            {
                "canonical_company_id": "existing-co",
                "company": "Existing Co",
                "region": "Germany",
                "locations": "Berlin; Munich",
                "career_url": "https://new.example/careers",
                "company_category": "Corporate",
            },
            {
                "canonical_company_id": "new-bank",
                "company": "New Bank",
                "region": "Switzerland",
                "locations": "Zurich",
                "career_url": "https://bank.example/jobs",
                "company_category": "Banking & Financial Services",
            },
            {
                "canonical_company_id": "new-discovered",
                "company": "New Discovered",
                "region": "Austria",
                "locations": "Vienna",
                "career_url": "https://discovered.example/careers",
                "company_category": "Unclassified / discovered",
            },
            {
                "canonical_company_id": "missing-url",
                "company": "Missing URL Co",
                "region": "Denmark",
                "locations": "Copenhagen",
                "career_url": "",
                "company_category": "Corporate",
            },
            {
                "canonical_company_id": "excluded-co",
                "company": "Excluded Co",
                "region": "Germany",
                "locations": "Frankfurt",
                "career_url": "https://excluded.example/jobs",
                "company_category": "Corporate",
            },
        ])
        universe.to_csv(self.data / "company_universe.csv", index=False)
        ratings = pd.DataFrame([
            {"canonical_company_id": "existing-co", "rating": "A"},
            {"canonical_company_id": "new-bank", "rating": "C"},
            {"canonical_company_id": "new-discovered", "rating": "B"},
            {"canonical_company_id": "missing-url", "rating": "A"},
            {"canonical_company_id": "excluded-co", "rating": "Exclude"},
        ])
        ratings.to_csv(self.data / "company_ratings.csv", index=False)

        for filename in [
            "job_sources_consulting.csv",
            "job_sources_pe.csv",
            "job_sources_corporate.csv",
            "job_sources_financial_services.csv",
            "job_sources_holdings.csv",
            "job_sources_investment_banking.csv",
            "job_sources_public_markets.csv",
            "job_sources_specialist_funds.csv",
        ]:
            pd.DataFrame(columns=SOURCE_COLUMNS).to_csv(self.data / filename, index=False)

        corporate = pd.DataFrame([
            {
                "source_id": "existing-co-global",
                "canonical_company_id": "existing-co",
                "company": "Existing Co",
                "market": "Multi-region",
                "priority_locations": "Berlin",
                "seed_url": "https://ats.example/existing",
                "adapter": "workday",
                "cadence_days": 14,
                "enabled": True,
            },
            {
                "source_id": "excluded-co-global",
                "canonical_company_id": "excluded-co",
                "company": "Excluded Co",
                "market": "Germany",
                "priority_locations": "Frankfurt",
                "seed_url": "https://ats.example/excluded",
                "adapter": "smartrecruiters",
                "cadence_days": 7,
                "enabled": True,
            },
        ], columns=SOURCE_COLUMNS)
        corporate.to_csv(self.data / "job_sources_corporate.csv", index=False)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_sync_updates_existing_adds_missing_and_disables_excluded(self) -> None:
        status = sync_company_sources(self.data)

        corporate = pd.read_csv(self.data / "job_sources_corporate.csv").fillna("")
        existing = corporate[corporate["canonical_company_id"] == "existing-co"].iloc[0]
        self.assertEqual(int(existing["cadence_days"]), 7)
        self.assertEqual(str(existing["enabled"]).lower(), "true")
        self.assertEqual(existing["adapter"], "workday")
        self.assertEqual(existing["seed_url"], "https://ats.example/existing")

        excluded = corporate[corporate["canonical_company_id"] == "excluded-co"].iloc[0]
        self.assertEqual(str(excluded["enabled"]).lower(), "false")
        self.assertEqual(excluded["adapter"], "smartrecruiters")

        # Unclassified discovered employers use the corporate registry only as
        # an operational generic bucket; their A category is not changed.
        discovered = corporate[corporate["canonical_company_id"] == "new-discovered"].iloc[0]
        self.assertEqual(int(discovered["cadence_days"]), 14)
        self.assertEqual(discovered["adapter"], "generic")
        self.assertEqual(discovered["seed_url"], "https://discovered.example/careers")

        banking = pd.read_csv(self.data / "job_sources_financial_services.csv").fillna("")
        new_bank = banking[banking["canonical_company_id"] == "new-bank"].iloc[0]
        self.assertEqual(int(new_bank["cadence_days"]), 30)
        self.assertEqual(new_bank["adapter"], "generic")

        statuses = dict(zip(status["canonical_company_id"], status["status"]))
        self.assertEqual(statuses["existing-co"], "active_existing_source")
        self.assertEqual(statuses["new-bank"], "active_new_source")
        self.assertEqual(statuses["new-discovered"], "active_new_source")
        self.assertEqual(statuses["missing-url"], "missing_career_url")
        self.assertEqual(statuses["excluded-co"], "disabled_exclude")
        self.assertFalse((corporate["canonical_company_id"] == "missing-url").any())

    def test_unrated_existing_source_is_disabled(self) -> None:
        ratings = pd.DataFrame([
            {"canonical_company_id": "existing-co", "rating": "Unrated"},
        ])
        ratings.to_csv(self.data / "company_ratings.csv", index=False)
        status = sync_company_sources(self.data)
        corporate = pd.read_csv(self.data / "job_sources_corporate.csv").fillna("")
        existing = corporate[corporate["canonical_company_id"] == "existing-co"].iloc[0]
        self.assertEqual(str(existing["enabled"]).lower(), "false")
        self.assertEqual(status.iloc[0]["status"], "disabled_unrated")


if __name__ == "__main__":
    unittest.main()
