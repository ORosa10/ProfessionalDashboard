from __future__ import annotations

import unittest

from sourcing.czech_board_identity import recover_czech_board_company


class CzechBoardIdentityTests(unittest.TestCase):
    def test_existing_valid_company_wins(self) -> None:
        html = '<html><title>Detail pozice | Wrong Brand</title></html>'
        self.assertEqual(
            recover_czech_board_company("jobs-cz", html, "Existing Employer s.r.o."),
            "Existing Employer s.r.o.",
        )

    def test_standard_jobs_detail_extracts_company_label(self) -> None:
        html = '''
        <html><body>
        <h1>Financial Controller</h1>
        <div>Informace o pozici Společnost Plasman CZ s.r.o. Required education University</div>
        </body></html>
        '''
        self.assertEqual(
            recover_czech_board_company("jobs-cz", html, "Poslat nabídku na e-mail"),
            "Plasman CZ s.r.o.",
        )

    def test_mail_dialog_extracts_actual_company(self) -> None:
        html = '''
        <html><body>
        Kam vám můžeme nabídku Treasury manažer/ka u KBP Back Office s.r.o. poslat?
        </body></html>
        '''
        self.assertEqual(
            recover_czech_board_company("jobs-cz", html, "Employer not stated"),
            "KBP Back Office s.r.o.",
        )

    def test_branded_microsite_extracts_company(self) -> None:
        html = '<html><head><title>Detail pozice | KPMG Česká republika</title></head><body></body></html>'
        self.assertEqual(
            recover_czech_board_company("jobs-cz", html, "Employer not stated"),
            "KPMG Česká republika",
        )

    def test_recruiter_brand_is_not_promoted_as_employer(self) -> None:
        html = '<html><head><title>Detail pozice | Manpower</title></head><body>Anonymous client role</body></html>'
        self.assertEqual(recover_czech_board_company("jobs-cz", html, "Employer not stated"), "")

    def test_cez_microsite_is_recognised(self) -> None:
        html = '''
        <html><head><title>Detail pozice | ...kde jinde.</title></head>
        <body>O Skupině ČEZ Proč pracovat v ČEZ Členové Skupiny ČEZ</body></html>
        '''
        self.assertEqual(
            recover_czech_board_company("jobs-cz", html, "Employer not stated"),
            "ČEZ Group",
        )

    def test_other_sources_are_not_guessed(self) -> None:
        html = '<html><head><title>Detail pozice | Example AG</title></head></html>'
        self.assertEqual(recover_czech_board_company("stepstone-de", html, "Employer not stated"), "")


if __name__ == "__main__":
    unittest.main()
