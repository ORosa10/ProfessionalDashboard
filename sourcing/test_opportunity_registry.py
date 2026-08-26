from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from sourcing.opportunity_registry import update_registry, validate_semantic_identity


class OpportunityRegistryTests(unittest.TestCase):
    def _jobs(self, title="Treasury Analyst", url="https://example.com/job/1"):
        return pd.DataFrame([{
            "job_id": "j1", "title": title, "company": "Example", "job_url": url,
            "description": "Treasury role", "status": "Open",
        }])

    def test_registry_preserves_metadata_after_current_snapshot_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "opportunity_registry.csv"
            first = update_registry(path, self._jobs())
            first.to_csv(path, index=False)
            second = update_registry(path, pd.DataFrame(columns=self._jobs().columns))
            self.assertEqual(second.iloc[0]["title"], "Treasury Analyst")

    def test_orphan_semantic_judgment_fails_closed(self):
        registry = update_registry(Path("/does/not/exist"), self._jobs())
        semantic = pd.DataFrame([{"opportunity_id": "missing", "fit": "Strong", "reasoning": "x"}])
        with self.assertRaises(ValueError):
            validate_semantic_identity(semantic, registry)

    def test_missing_identity_metadata_fails_closed(self):
        registry = update_registry(Path("/does/not/exist"), self._jobs(title="", url=""))
        semantic = pd.DataFrame([{"opportunity_id": "j1", "fit": "Strong", "reasoning": "x"}])
        with self.assertRaises(ValueError):
            validate_semantic_identity(semantic, registry)


if __name__ == "__main__":
    unittest.main()
