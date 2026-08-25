from __future__ import annotations

import unittest

import pandas as pd

from sourcing.remote_pilot import (
    FINANCE_TITLE_TERMS,
    STAGING_COLUMNS,
    _DEFAULT_FINANCE_TERMS,
    is_project_role,
    merge_remote_snapshot,
    remote_scope_hint,
)


class RemotePilotTests(unittest.TestCase):
    def test_learned_terms_cannot_remove_baseline_discovery_terms(self) -> None:
        self.assertTrue(set(_DEFAULT_FINANCE_TERMS).issubset(set(FINANCE_TITLE_TERMS)))
        self.assertIn("treasury", FINANCE_TITLE_TERMS)
        self.assertIn("investment", FINANCE_TITLE_TERMS)
        self.assertIn("finance", FINANCE_TITLE_TERMS)

    def test_project_detection_requires_strong_employment_evidence(self) -> None:
        self.assertTrue(is_project_role("Interim Treasury Manager", ""))
        self.assertTrue(is_project_role("Treasury Manager", "This is a 6-month contract role."))
        self.assertTrue(is_project_role("FP&A Manager", "Employment type: fixed-term"))

        self.assertFalse(is_project_role(
            "Treasury Manager",
            "You will review customer contracts and support contract negotiations with banks.",
        ))
        self.assertFalse(is_project_role(
            "Investment Analyst",
            "The portfolio includes businesses with long-term contracted revenue.",
        ))

    def test_remote_scope_hint_preserves_explicit_scope_without_inferring(self) -> None:
        self.assertEqual(
            remote_scope_hint("FP&A Analyst", "Headquarters: Remote - US", ""),
            "Remote - US",
        )
        self.assertEqual(
            remote_scope_hint("Risk Analyst", "This role is remote within Europe.", ""),
            "Remote - Europe",
        )
        self.assertEqual(
            remote_scope_hint("Treasury Analyst", "Location: Remote - EMEA", ""),
            "Remote - EMEA",
        )
        self.assertEqual(
            remote_scope_hint("Investment Analyst", "Work from anywhere in the world.", ""),
            "Remote - Worldwide",
        )
        self.assertEqual(
            remote_scope_hint("Risk Analyst", "US customers are a major part of our business. Remote role.", ""),
            "Remote",
        )

    def test_failed_source_snapshot_is_preserved_while_healthy_source_is_replaced(self) -> None:
        previous = pd.DataFrame([
            {"job_id": "old-a", "source_id": "remoteok", "company": "A", "title": "Treasury", "job_url": "https://a"},
            {"job_id": "old-b", "source_id": "remotive", "company": "B", "title": "Risk", "job_url": "https://b"},
        ]).reindex(columns=STAGING_COLUMNS, fill_value="")
        current = pd.DataFrame([
            {"job_id": "new-a", "source_id": "remoteok", "company": "A", "title": "Treasury Manager", "job_url": "https://a2"},
        ]).reindex(columns=STAGING_COLUMNS, fill_value="")

        merged = merge_remote_snapshot(current, previous, {"remoteok"})
        self.assertEqual(set(merged["job_id"]), {"new-a", "old-b"})
        self.assertNotIn("old-a", set(merged["job_id"]))

    def test_successful_empty_source_removes_its_old_roles(self) -> None:
        previous = pd.DataFrame([
            {"job_id": "old-a", "source_id": "remoteok", "company": "A", "title": "Treasury", "job_url": "https://a"},
        ]).reindex(columns=STAGING_COLUMNS, fill_value="")
        current = pd.DataFrame(columns=STAGING_COLUMNS)
        merged = merge_remote_snapshot(current, previous, {"remoteok"})
        self.assertTrue(merged.empty)


if __name__ == "__main__":
    unittest.main()
