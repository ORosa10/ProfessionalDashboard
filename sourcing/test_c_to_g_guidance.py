from __future__ import annotations

import unittest
import pandas as pd

from sourcing.c_to_g_guidance import priority_queries_from_frame


class CToGGuidanceTests(unittest.TestCase):
    def test_only_active_prioritize_rows_add_queries(self) -> None:
        frame = pd.DataFrame([
            {"status": "Active", "direction": "prioritize", "query_term": "deal finance"},
            {"status": "Proposed", "direction": "prioritize", "query_term": "portfolio construction"},
            {"status": "Active", "direction": "deprioritize", "query_term": "AI engineer"},
            {"status": "Active", "direction": "prioritize", "query_term": "Deal Finance"},
        ])
        self.assertEqual(priority_queries_from_frame(frame), ["deal finance"])


if __name__ == "__main__":
    unittest.main()
