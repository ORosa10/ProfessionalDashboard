from __future__ import annotations

import unittest

import pandas as pd

from sourcing.build_j_shortlist_shadow import build_j_shadow


def _universe() -> pd.DataFrame:
    return pd.DataFrame([
        {"canonical_company_id": "a", "company": "A Co", "aliases_entities": "", "rating": "A"},
        {"canonical_company_id": "b", "company": "B Co", "aliases_entities": "", "rating": "B"},
        {"canonical_company_id": "c", "company": "C Co", "aliases_entities": "", "rating": "C"},
        {"canonical_company_id": "x", "company": "X Co", "aliases_entities": "", "rating": "Exclude"},
    ])


def _candidate(job_id: str, company: str, country: str, posted: str = "2026-08-20") -> dict:
    return {
        "candidate_id": f"cand-{job_id}",
        "job_id": job_id,
        "company": company,
        "title": f"Role {job_id}",
        "country_bucket": country,
        "market": country,
        "location": country,
        "date_posted": posted,
        "last_seen_at": "2026-08-24",
        "source_streams": "test",
        "job_url": f"https://example.com/{job_id}",
    }


def _semantic(items: list[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame([{"opportunity_id": oid, "fit": fit} for oid, fit in items])


def _actionability(items: list[tuple[str, bool]]) -> pd.DataFrame:
    return pd.DataFrame([
        {"opportunity_id": oid, "actionable": value, "warnings": ""}
        for oid, value in items
    ])


class JShadowTests(unittest.TestCase):
    def test_only_strong_and_actionable_roles_are_eligible(self) -> None:
        candidates = pd.DataFrame([
            _candidate("strong", "A Co", "Germany"),
            _candidate("moderate", "B Co", "Germany"),
            _candidate("blocked", "C Co", "Germany"),
        ])
        semantic = _semantic([("strong", "Strong"), ("moderate", "Moderate"), ("blocked", "Strong")])
        actionability = _actionability([("strong", True), ("moderate", True), ("blocked", False)])
        shortlist, _ = build_j_shadow(
            candidates, semantic, actionability, pd.DataFrame(), {"Germany": 3},
            limit=3, company_universe=_universe(),
        )
        self.assertEqual(list(shortlist["opportunity_id"]), ["strong"])

    def test_quota_deficit_is_redistributed_without_using_moderate(self) -> None:
        candidates = pd.DataFrame([
            _candidate("de1", "A Co", "Germany", "2026-08-22"),
            _candidate("de2", "B Co", "Germany", "2026-08-21"),
            _candidate("uk-moderate", "C Co", "United Kingdom", "2026-08-23"),
        ])
        semantic = _semantic([("de1", "Strong"), ("de2", "Strong"), ("uk-moderate", "Moderate")])
        actionability = _actionability([("de1", True), ("de2", True), ("uk-moderate", True)])
        shortlist, quotas = build_j_shadow(
            candidates, semantic, actionability, pd.DataFrame(),
            {"Germany": 1, "United Kingdom": 1},
            limit=2, company_universe=_universe(),
        )
        self.assertEqual(set(shortlist["opportunity_id"]), {"de1", "de2"})
        uk = quotas.set_index("country").loc["United Kingdom"]
        self.assertEqual(int(uk["quota_deficit"]), 1)
        self.assertEqual(int(uk["final_selected_after_redistribution"]), 0)

    def test_apply_skip_and_excluded_company_do_not_return_to_j(self) -> None:
        candidates = pd.DataFrame([
            _candidate("applied", "A Co", "Germany"),
            _candidate("skipped", "B Co", "Germany"),
            _candidate("excluded", "X Co", "Germany"),
            _candidate("keep", "C Co", "Germany"),
        ])
        semantic = _semantic([(oid, "Strong") for oid in ["applied", "skipped", "excluded", "keep"]])
        actionability = _actionability([(oid, True) for oid in ["applied", "skipped", "excluded", "keep"]])
        history = pd.DataFrame([
            {"opportunity_id": "applied", "action": "Apply"},
            {"opportunity_id": "skipped", "action": "Skip"},
        ])
        shortlist, _ = build_j_shadow(
            candidates, semantic, actionability, history, {"Germany": 4},
            limit=4, company_universe=_universe(),
        )
        self.assertEqual(list(shortlist["opportunity_id"]), ["keep"])

    def test_company_cap_is_preserved(self) -> None:
        candidates = pd.DataFrame([
            _candidate("a1", "A Co", "Germany", "2026-08-24"),
            _candidate("a2", "A Co", "Germany", "2026-08-23"),
            _candidate("a3", "A Co", "Germany", "2026-08-22"),
            _candidate("b1", "B Co", "Germany", "2026-08-21"),
        ])
        semantic = _semantic([(oid, "Strong") for oid in ["a1", "a2", "a3", "b1"]])
        actionability = _actionability([(oid, True) for oid in ["a1", "a2", "a3", "b1"]])
        shortlist, _ = build_j_shadow(
            candidates, semantic, actionability, pd.DataFrame(), {"Germany": 4},
            limit=4, company_universe=_universe(), max_per_company=2,
        )
        self.assertEqual(int(shortlist["company"].eq("A Co").sum()), 2)
        self.assertIn("b1", set(shortlist["opportunity_id"]))

    def test_company_preference_orders_selected_roles_but_does_not_change_eligibility(self) -> None:
        candidates = pd.DataFrame([
            _candidate("b", "B Co", "Germany", "2026-08-24"),
            _candidate("a", "A Co", "Germany", "2026-08-20"),
        ])
        semantic = _semantic([("a", "Strong"), ("b", "Strong")])
        actionability = _actionability([("a", True), ("b", True)])
        shortlist, _ = build_j_shadow(
            candidates, semantic, actionability, pd.DataFrame(), {"Germany": 2},
            limit=2, company_universe=_universe(),
        )
        self.assertEqual(set(shortlist["opportunity_id"]), {"a", "b"})
        self.assertEqual(shortlist.iloc[0]["company_rating"], "A")


if __name__ == "__main__":
    unittest.main()
