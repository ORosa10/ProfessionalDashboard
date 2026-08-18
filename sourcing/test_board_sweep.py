import unittest

import pandas as pd

from sourcing.board_sweep import (
    _location_text,
    _stable_id,
    deduplicate_board_jobs,
    extract_ba_search_links,
    relevant_finance_title,
)


class BoardSweepTest(unittest.TestCase):
    def test_extracts_bundesagentur_result_links(self):
        html = """
        <a id="ergebnisliste-item-0"
           href="https://www.arbeitsagentur.de/jobsuche/jobdetail/ABC-123">
          <h2><span>1: </span><span>Treasury Specialist bei Example GmbH</span></h2>
        </a>
        <a id="not-a-result" href="/jobsuche/jobdetail/ignored">Ignored</a>
        """
        self.assertEqual(
            extract_ba_search_links(html, 5),
            [(
                "https://www.arbeitsagentur.de/jobsuche/jobdetail/ABC-123",
                "Treasury Specialist bei Example GmbH",
            )],
        )

    def test_normalizes_schema_location(self):
        self.assertEqual(
            _location_text({
                "addressLocality": "Frankfurt",
                "addressRegion": "Hessen",
                "addressCountry": "DE",
            }),
            "Frankfurt, Hessen, DE",
        )

    def test_stable_id_uses_source_identity(self):
        first = _stable_id("one", "42", "https://example/a")
        self.assertEqual(first, _stable_id("one", "42", "https://example/b"))
        self.assertNotEqual(first, _stable_id("two", "42", "https://example/a"))

    def test_title_prefilter_rejects_search_description_noise(self):
        self.assertTrue(relevant_finance_title("Senior Treasury Specialist"))
        self.assertTrue(relevant_finance_title("Investment Analyst / Associate"))
        self.assertFalse(relevant_finance_title("IT-arkitekt till Stockholm"))

    def test_deduplicates_same_company_role_but_not_other_companies(self):
        rows = pd.DataFrame([
            {"job_id": "1", "company": "Example SE", "title": "Treasury Specialist (m/w/d)", "date_posted": "2026-08-17", "location": "Berlin", "job_url": "https://one", "matched_terms": "treasury"},
            {"job_id": "2", "company": "Example SE", "title": "Treasury Specialist", "date_posted": "2026-08-16", "location": "Munich", "job_url": "https://two", "matched_terms": "treasury; finance"},
            {"job_id": "3", "company": "Other AG", "title": "Treasury Specialist", "date_posted": "2026-08-16", "location": "Hamburg", "job_url": "https://three", "matched_terms": "treasury"},
        ])
        result = deduplicate_board_jobs(rows)
        self.assertEqual(len(result), 2)
        example = result[result["company"] == "Example SE"].iloc[0]
        self.assertIn("Berlin", example["location"])
        self.assertIn("Munich", example["location"])
        self.assertEqual(example["duplicate_count"], 2)


if __name__ == "__main__":
    unittest.main()
