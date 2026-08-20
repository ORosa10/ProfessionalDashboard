import unittest

from sourcing.board_catalog_adapters import extract_catalog_links


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

    def test_jobbank(self):
        html = '<a href="/job/3067629/">Treasury Analyst</a>'
        self.assertEqual(
            extract_catalog_links("jobbank-dk", html, 5),
            ["https://jobbank.dk/job/3067629/"],
        )

    def test_ledigajobb(self):
        html = '<a href="/jobb/c348d8/example">Treasury Analyst</a>'
        self.assertEqual(
            extract_catalog_links("ledigajobb-se", html, 5),
            ["https://ledigajobb.se/jobb/c348d8/example"],
        )


if __name__ == "__main__":
    unittest.main()
