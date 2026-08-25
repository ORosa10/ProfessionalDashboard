from __future__ import annotations

import unittest

import pandas as pd

from sourcing.build_holdings_deterministic_shadow import build_shadow_sources


class HoldingsDeterministicShadowTests(unittest.TestCase):
    def test_known_llm_sources_are_overridden_without_touching_unresolved_rows(self) -> None:
        frame = pd.DataFrame([
            {"source_id": "investor-ab-global", "company": "Investor AB", "seed_url": "old", "adapter": "llm", "enabled": True},
            {"source_id": "ap-moller-holding-global", "company": "A.P. Moller Holding", "seed_url": "old-apm", "adapter": "llm", "enabled": True},
        ])
        out = build_shadow_sources(frame)
        investor = out[out["source_id"].eq("investor-ab-global")].iloc[0]
        self.assertEqual(investor["adapter"], "generic")
        self.assertEqual(investor["seed_url"], "https://career.investorab.com/jobs")
        self.assertEqual(investor["shadow_override"], "deterministic")

        apm = out[out["source_id"].eq("ap-moller-holding-global")].iloc[0]
        self.assertEqual(apm["adapter"], "llm")
        self.assertEqual(apm["seed_url"], "old-apm")
        self.assertEqual(apm["shadow_override"], "")

    def test_jobs_cz_company_portals_allow_canonical_detail_host(self) -> None:
        frame = pd.DataFrame([
            {"source_id": "csg-global", "company": "CSG", "seed_url": "old", "adapter": "llm"},
            {"source_id": "cpi-property-group-global", "company": "CPI", "seed_url": "old", "adapter": "llm"},
        ])
        out = build_shadow_sources(frame).set_index("source_id")
        for source_id in ("csg-global", "cpi-property-group-global"):
            self.assertEqual(out.loc[source_id, "adapter"], "generic")
            self.assertIn("www.jobs.cz", out.loc[source_id, "allowed_domains"])

    def test_porsche_stale_path_is_replaced(self) -> None:
        frame = pd.DataFrame([
            {"source_id": "porsche-se-global", "company": "Porsche SE", "seed_url": "https://www.porsche-se.com/en/company/career", "adapter": "llm"},
        ])
        out = build_shadow_sources(frame)
        self.assertEqual(out.iloc[0]["seed_url"], "https://www.porsche-se.com/en/career")
        self.assertEqual(out.iloc[0]["adapter"], "generic")


if __name__ == "__main__":
    unittest.main()
