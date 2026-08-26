import unittest

from sourcing.board_html_adapters import _fallback_detail, extract_html_search_links


class BoardHtmlAdaptersTest(unittest.TestCase):
    def test_jobs_cz_extracts_canonical_rpd_detail(self):
        html = '''
        <a href="/prace/?q=treasury">filter</a>
        <a class="job-card" href="/rpd/2000999999/?searchId=abc&rps=228">Treasury Analyst</a>
        '''
        self.assertEqual(
            extract_html_search_links("jobs-cz", html, 10),
            ["https://www.jobs.cz/rpd/2000999999/"],
        )

    def test_jobs_cz_fallback_does_not_treat_navigation_as_company(self):
        html = '''
        <html><body>
          <h1>Treasury manažer/ka</h1>
          <div class="company-actions">Poslat nabídku na e-mail</div>
          <h2>Práce v oboru</h2>
          <h3>Navštivte naše sociální sítě a poznejte Trinity Bank ještě blíž</h3>
        </body></html>
        '''
        item = _fallback_detail(html)
        self.assertIsNotNone(item)
        self.assertEqual(item["hiringOrganization"]["name"], "Employer not stated")

    def test_fallback_still_keeps_credible_company(self):
        html = '''
        <html><body>
          <h1>Treasury Analyst</h1>
          <div class="company-name">Example Energy AG</div>
        </body></html>
        '''
        item = _fallback_detail(html)
        self.assertEqual(item["hiringOrganization"]["name"], "Example Energy AG")

    def test_prace_cz_extracts_canonical_offer_detail(self):
        html = '''
        <a href="/nabidky/praha/finance-a-ekonomika/">filter</a>
        <a href="/firma/example/nabidka/0005884f-5d38-41a9-b84e-45f2bba8b393/?rps=2077">Group Finance Project Lead</a>
        '''
        self.assertEqual(
            extract_html_search_links("prace-cz", html, 10),
            ["https://www.prace.cz/firma/example/nabidka/0005884f-5d38-41a9-b84e-45f2bba8b393/"],
        )

    def test_stepstone_at_extracts_vacancy_detail(self):
        html = '<a href="/stellenangebote--Treasury-Expert-Wien-Example--992643-inline.html">role</a>'
        self.assertEqual(extract_html_search_links("stepstone-at", html, 10), ["https://www.stepstone.at/stellenangebote--Treasury-Expert-Wien-Example--992643-inline.html"])

    def test_stepstone_de_extracts_vacancy_detail(self):
        html = '<a href="/stellenangebote--Treasury-Manager-Frankfurt-Example--123456-inline.html">role</a>'
        self.assertEqual(extract_html_search_links("stepstone-de", html, 10), ["https://www.stepstone.de/stellenangebote--Treasury-Manager-Frankfurt-Example--123456-inline.html"])

    def test_stellenanzeigen_extracts_job_detail(self):
        html = '<a href="/job/senior-treasury-manager-hamburg-16413766/">Senior Treasury Manager</a>'
        self.assertEqual(extract_html_search_links("stellenanzeigen-de", html, 10), ["https://www.stellenanzeigen.de/job/senior-treasury-manager-hamburg-16413766/"])

    def test_karriere_at_extracts_numeric_job_detail(self):
        html = '<a href="/jobs/10028350">Finance, Treasury and Insurance Manager</a>'
        self.assertEqual(extract_html_search_links("karriere-at", html, 10), ["https://www.karriere.at/jobs/10028350"])

    def test_willhaben_extracts_job_detail(self):
        html = '<a href="/jobs/job/treasury-financial-markets-trader/13177276">Treasury Trader</a>'
        self.assertEqual(extract_html_search_links("willhaben-at", html, 10), ["https://www.willhaben.at/jobs/job/treasury-financial-markets-trader/13177276"])

    def test_jobbsafari_extracts_job_detail(self):
        html = '<a href="/jobb/treasury-analyst-sasrb-20169129">Treasury Analyst</a>'
        self.assertEqual(extract_html_search_links("jobbsafari-se", html, 10), ["https://jobbsafari.se/jobb/treasury-analyst-sasrb-20169129"])


if __name__ == "__main__":
    unittest.main()