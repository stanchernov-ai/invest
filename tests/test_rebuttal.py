"""Tests for Round 2 rebuttal prompt helpers."""
import unittest

from src.core.rebuttal import (
    build_round2_user_prompt,
    extract_round_overview,
    is_verbatim_r1_copy,
)


class TestRebuttalHelpers(unittest.TestCase):
    def test_extract_round1_overview(self):
        messages = [
            {
                "content": (
                    "**[ROUND 1] Warren Buffett**:\n"
                    "* **Portfolio Overview**: Tech concentration is reckless.\n"
                    "* **NVDA**: Hold. Analysis: Too expensive.\n"
                )
            }
        ]
        text = extract_round_overview(messages, "buffett", "1")
        self.assertIn("Tech concentration", text)

    def test_extract_round2_rebuttal_summary(self):
        messages = [
            {
                "content": (
                    "**[ROUND 2 REBUTTAL] Warren Buffett**:\n"
                    "* **Rebuttal Summary**: Lynch is wrong about NVDA — cash flow supports it.\n"
                    "* **NVDA**: Buy (8/10). Margin of safety emerging.\n"
                )
            }
        ]
        text = extract_round_overview(messages, "buffett", "2")
        self.assertIn("Lynch is wrong", text)

    def test_verbatim_copy_detected(self):
        prose = "Tech concentration is reckless given current multiples."
        self.assertTrue(is_verbatim_r1_copy(prose, prose))
        self.assertTrue(is_verbatim_r1_copy(prose, prose + " "))

    def test_distinct_rebuttal_not_flagged(self):
        r1 = "Tech concentration is reckless given current multiples."
        r2 = "Peter Lynch argues growth justifies NVDA, but I still see no margin of safety."
        self.assertFalse(is_verbatim_r1_copy(r1, r2))

    def test_build_round2_prompt_names_peers_and_forbids_copy(self):
        messages = [
            {
                "content": (
                    "**[ROUND 1] Warren Buffett**:\n"
                    "* **Portfolio Overview**: Concentration risk is elevated.\n"
                )
            },
            {
                "content": (
                    "**[ROUND 1] Peter Lynch**:\n"
                    "* **Portfolio Overview**: Growth names still have runway.\n"
                )
            },
        ]
        prompt = build_round2_user_prompt("buffett", messages)
        self.assertIn("Peter Lynch", prompt)
        self.assertIn("do not copy", prompt.lower())
        self.assertIn("Concentration risk", prompt)
        self.assertIn("Growth names", prompt)


if __name__ == "__main__":
    unittest.main()
