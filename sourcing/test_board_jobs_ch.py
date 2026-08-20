import unittest

from sourcing.board_jobs_ch import extract_jobs_ch_links


class JobsChAdapterTest(unittest.TestCase):
    def test_extracts_vacancy_detail(self):
        html = '''
        <a href="/en/vacancies/?term=treasury">search</a>
        <a href="/en/vacancies/detail/99d727ae-7aa9-432a-8a65-10e6bf95284a/">Treasury Analyst</a>
        '''
        self.assertEqual(
            extract_jobs_ch_links(html, 10),
            ["https://www.jobs.ch/en/vacancies/detail/99d727ae-7aa9-432a-8a65-10e6bf95284a/"],
        )


if __name__ == "__main__":
    unittest.main()
