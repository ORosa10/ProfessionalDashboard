from __future__ import annotations

import unittest

import pandas as pd

from sourcing.sector_pilot import (
    consecutive_technical_failures,
    infer_adapter_from_url,
    is_technical_failure,
)


class SectorAdapterFallbackTests(unittest.TestCase):
    def test_url_fingerprints_are_conservative(self) -> None:
        self.assertEqual(
            infer_adapter_from_url("https://company.wd3.myworkdayjobs.com/Careers"),
            "workday",
        )
        self.assertEqual(
            infer_adapter_from_url("https://job-boards.greenhouse.io/example"),
            "greenhouse",
        )
        self.assertEqual(
            infer_adapter_from_url("https://jobs.personio.de/example"),
            "personio",
        )
        self.assertEqual(
            infer_adapter_from_url("https://careers.smartrecruiters.com/Example"),
            "smartrecruiters",
        )
        self.assertEqual(
            infer_adapter_from_url("https://career012.successfactors.eu/career?company=x"),
            "successfactors",
        )
        self.assertEqual(
            infer_adapter_from_url("https://www.example.com/careers"),
            "",
        )

    def test_successful_zero_job_scan_is_not_failure(self) -> None:
        self.assertFalse(is_technical_failure({"errors": "", "verified_jobs": 0}))
        self.assertFalse(
            is_technical_failure({"errors": "one detail failed", "verified_jobs": 2})
        )
        self.assertTrue(
            is_technical_failure({"errors": "career page: HTTPError", "verified_jobs": 0})
        )

    def test_only_trailing_generic_technical_failures_count(self) -> None:
        history = pd.DataFrame(
            [
                {
                    "run_at": "2026-08-01T00:00:00Z",
                    "source_id": "x",
                    "adapter_used": "generic",
                    "errors": "old failure",
                    "verified_jobs": 0,
                },
                {
                    "run_at": "2026-08-08T00:00:00Z",
                    "source_id": "x",
                    "adapter_used": "generic",
                    "errors": "",
                    "verified_jobs": 0,
                },
                {
                    "run_at": "2026-08-15T00:00:00Z",
                    "source_id": "x",
                    "adapter_used": "generic",
                    "errors": "failure 1",
                    "verified_jobs": 0,
                },
                {
                    "run_at": "2026-08-22T00:00:00Z",
                    "source_id": "x",
                    "adapter_used": "generic",
                    "errors": "failure 2",
                    "verified_jobs": 0,
                },
            ]
        )
        self.assertEqual(consecutive_technical_failures(history, "x"), 2)

        history.loc[len(history)] = {
            "run_at": "2026-08-23T00:00:00Z",
            "source_id": "x",
            "adapter_used": "workday",
            "errors": "temporary error",
            "verified_jobs": 0,
        }
        self.assertEqual(consecutive_technical_failures(history, "x"), 0)


if __name__ == "__main__":
    unittest.main()
