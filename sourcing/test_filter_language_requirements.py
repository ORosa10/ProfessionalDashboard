from __future__ import annotations

import unittest

from sourcing.filter_language_requirements import blocking_language_requirement


class LanguageRequirementFilterTests(unittest.TestCase):
    def test_german_b2_is_allowed(self) -> None:
        text = "Fluent English required. German B2 is desirable for stakeholder communication."
        self.assertEqual(blocking_language_requirement(text), "")

    def test_good_german_is_allowed(self) -> None:
        text = "Good German and English language skills are required."
        self.assertEqual(blocking_language_requirement(text), "")

    def test_german_c1_is_blocked(self) -> None:
        text = "German language skills at C1 level are required."
        self.assertIn("German", blocking_language_requirement(text))

    def test_fluent_german_is_blocked(self) -> None:
        text = "Fluent German and English are required for the role."
        self.assertIn("German", blocking_language_requirement(text))

    def test_norwegian_prerequisite_is_blocked(self) -> None:
        text = "Fluency in a Nordic language is a prerequisite."
        self.assertIn("Nordic", blocking_language_requirement(text))

    def test_norwegian_preferred_is_allowed(self) -> None:
        text = "English is required; Norwegian is preferred but not mandatory."
        self.assertEqual(blocking_language_requirement(text), "")

    def test_language_mention_is_not_enough(self) -> None:
        text = "You will work with Norwegian and Swedish colleagues across the Nordics."
        self.assertEqual(blocking_language_requirement(text), "")


if __name__ == "__main__":
    unittest.main()
