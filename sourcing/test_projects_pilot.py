from __future__ import annotations

import unittest

from sourcing.projects_pilot import build_project_records


class ProjectsPilotTests(unittest.TestCase):
    def test_only_explicit_temporary_finance_roles_are_kept(self) -> None:
        raw = [
            ("Interim Treasury Manager", "A", "Six month assignment. Remote within Europe.", "https://example.com/a", "remoteok", "2026-08-25", ""),
            ("Treasury Manager", "B", "Permanent role with bank documentation responsibilities.", "https://example.com/b", "remoteok", "2026-08-25", ""),
            ("Freelance Software Engineer", "C", "Remote within Europe.", "https://example.com/c", "remoteok", "2026-08-25", ""),
        ]
        result = build_project_records(raw, "2026-08-25T00:00:00+00:00")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "Interim Treasury Manager")

    def test_project_channel_preserves_remote_scope(self) -> None:
        raw = [(
            "Interim FP&A Manager", "A", "Headquarters: Remote - US. This is a temporary role.",
            "https://example.com/a", "remotive", "2026-08-25", "Finance",
        )]
        result = build_project_records(raw, "2026-08-25T00:00:00+00:00")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["market"], "Remote")
        self.assertEqual(result[0]["location"], "Remote - US")


if __name__ == "__main__":
    unittest.main()
