from __future__ import annotations

import unittest

import pandas as pd

from sourcing.queue_selection import select_country_balanced_indices


class QueueSelectionTests(unittest.TestCase):
    def test_country_targets_are_not_starved_by_global_family_cap(self) -> None:
        jobs = pd.DataFrame([
            {"market": "Germany", "role_family": "Treasury / Markets", "title": "DE1"},
            {"market": "Germany", "role_family": "Treasury / Markets", "title": "DE2"},
            {"market": "Denmark", "role_family": "Treasury / Markets", "title": "DK1"},
            {"market": "Denmark", "role_family": "Treasury / Markets", "title": "DK2"},
            {"market": "Finland", "role_family": "Treasury / Markets", "title": "FI1"},
        ])
        targets = {"Germany": 2, "Denmark": 2, "Finland": 1}
        chosen = select_country_balanced_indices(jobs, 5, targets, family_cap=2)
        selected = jobs.loc[chosen]
        self.assertEqual(selected.groupby("market").size().to_dict(), {"Denmark": 2, "Finland": 1, "Germany": 2})

    def test_remaining_capacity_uses_quality_order(self) -> None:
        jobs = pd.DataFrame([
            {"market": "Germany", "role_family": "Treasury / Markets", "title": "best"},
            {"market": "Sweden", "role_family": "Risk", "title": "second"},
            {"market": "Austria", "role_family": "Corporate Finance / M&A", "title": "third"},
        ])
        chosen = select_country_balanced_indices(jobs, 3, {"Germany": 1}, family_cap=18)
        self.assertEqual(jobs.loc[chosen, "title"].tolist(), ["best", "second", "third"])

    def test_sparse_country_does_not_leave_capacity_unused(self) -> None:
        jobs = pd.DataFrame([
            {"market": "United Kingdom", "role_family": "Treasury / Markets", "title": "UK1"},
            {"market": "Germany", "role_family": "Treasury / Markets", "title": "DE1"},
            {"market": "Germany", "role_family": "Treasury / Markets", "title": "DE2"},
        ])
        chosen = select_country_balanced_indices(jobs, 3, {"United Kingdom": 3}, family_cap=1)
        self.assertEqual(len(chosen), 3)
        self.assertEqual(set(jobs.loc[chosen, "title"]), {"UK1", "DE1", "DE2"})


if __name__ == "__main__":
    unittest.main()
