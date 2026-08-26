import unittest

from sourcing.board_catalog_adapters import _relevant, extract_catalog_links, extract_detail_fields


class CatalogAdapterTest(unittest.TestCase):
    def test_startupjobs(self):
        html = '<a href="/nabidka/105017/finance-controller-part-time">Finance Controller</a>'
        self.assertEqual(
            extract_catalog_links("startupjobs-cz", html, 5),
            ["https://www.startupjobs.cz/nabidka/105017/finance-controller-part-time"],
        )

    def test_jobwinner(self):
        html = '<a href="/job/14645177">Konzern-Treasury</a>'
        self.assertEqual(
            extract_catalog_links("jobwinner-ch", html, 5),
            ["https://www.jobwinner.ch/job/14645177"],
        )

    def test_nzz_only_extracts_real_vacancy_details(self):
        html = '''
        <a href="/job/alle-jobs">all jobs</a>
        <a href="/job/alle-jobs-berufsgruppe-finanz-treuhand-controlling-risk-steuern">finance category</a>
        <a href="/job/treasury-manager-zuerich/496136">Treasury Manager</a>
        '''
        self.assertEqual(
            extract_catalog_links("nzz-jobs-ch", html, 5),
            ["https://jobs.nzz.ch/job/treasury-manager-zuerich/496136"],
        )

    def test_jobserve_requires_finance_signal_in_title(self):
        self.assertFalse(
            _relevant(
                "Senior Data Architect",
                "Banking client with financial risk and investment systems.",
                "jobserve-uk",
            )
        )
        self.assertTrue(
            _relevant(
                "Corporate Treasury Analyst",
                "Technology-enabled treasury team.",
                "jobserve-uk",
            )
        )
        self.assertTrue(
            _relevant(
                "Product Owner - Lease Finance",
                "Product ownership role.",
                "jobserve-uk",
            )
        )

    def test_non_jobserve_can_use_description_context(self):
        self.assertTrue(
            _relevant(
                "Analyst",
                "Corporate finance and valuation responsibilities.",
                "jobwinner-ch",
            )
        )

    def test_jobbank(self):
        html = '<a href="/job/3067629/">Treasury Analyst</a>'
        self.assertEqual(
            extract_catalog_links("jobbank-dk", html, 5),
            ["https://jobbank.dk/job/3067629/"],
        )

    def test_jobunivers(self):
        html = '<a href="/job/finans-oekonomi-og-regnskab/?job=7746&offset=0">Finance Manager</a>'
        self.assertEqual(
            extract_catalog_links("jobunivers-dk", html, 5),
            ["https://www.jobunivers.dk/job/finans-oekonomi-og-regnskab/?job=7746&offset=0"],
        )

    def test_ledigajobb(self):
        html = '<a href="/jobb/c348d8/example">Treasury Analyst</a>'
        self.assertEqual(
            extract_catalog_links("ledigajobb-se", html, 5),
            ["https://ledigajobb.se/jobb/c348d8/example"],
        )

    def test_jobbland_visible_h1_overrides_misleading_structured_title(self):
        html = '''
        <html><body>
          <script type="application/ld+json">
          {"@type":"JobPosting","title":"sales specialist",
           "hiringOrganization":{"name":"Danske Bank SWE"},
           "jobLocation":{"address":{"addressLocality":"Helsingfors","addressCountry":"Finland"}},
           "description":"Wholesale Credit Risk Management and credit analyst work.",
           "datePosted":"2026-08-18"}
          </script>
          <h1>Credit Analyst - Wholesale Credit Management</h1>
          <a>sales specialist</a>
        </body></html>
        '''
        title, company, location, description, date_posted = extract_detail_fields("jobbland-se", html)
        self.assertEqual(title, "Credit Analyst - Wholesale Credit Management")
        self.assertEqual(company, "Danske Bank SWE")
        self.assertIn("Helsingfors", location)
        self.assertIn("Credit Risk", description)
        self.assertEqual(date_posted, "2026-08-18")

    def test_non_jobbland_keeps_structured_title(self):
        html = '''
        <script type="application/ld+json">
        {"@type":"JobPosting","title":"Treasury Analyst","hiringOrganization":{"name":"Example"}}
        </script>
        <h1>Other page heading</h1>
        '''
        title, *_ = extract_detail_fields("jobwinner-ch", html)
        self.assertEqual(title, "Treasury Analyst")


if __name__ == "__main__":
    unittest.main()
