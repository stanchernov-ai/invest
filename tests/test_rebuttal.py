"""Tests for Round 2 rebuttal prompt helpers."""
import unittest

from src.core.board_roster import PANELIST_ROLES
from src.core.rebuttal import (
    build_round2_user_prompt,
    extract_round_overview,
    is_verbatim_r1_copy,
)


class TestRebuttalHelpers(unittest.TestCase):
    def test_extract_round1_overview(self):
        hypatia = PANELIST_ROLES["hypatia"]
        messages = [
            {
                "content": (
                    f"**[ROUND 1] {hypatia}**:\n"
                    "* **Portfolio Overview**: Tech concentration is reckless.\n"
                    "* **NVDA**: Hold. Analysis: Too expensive.\n"
                )
            }
        ]
        text = extract_round_overview(messages, "hypatia", "1")
        self.assertIn("Tech concentration", text)

    def test_extract_round2_rebuttal_summary(self):
        hypatia = PANELIST_ROLES["hypatia"]
        messages = [
            {
                "content": (
                    f"**[ROUND 2 REBUTTAL] {hypatia}**:\n"
                    "* **Rebuttal Summary**: davinci is wrong about NVDA — cash flow supports it.\n"
                    "* **NVDA**: Accumulate Candidate (8/10). Margin of safety emerging.\n"
                )
            }
        ]
        text = extract_round_overview(messages, "hypatia", "2")
        self.assertIn("davinci is wrong", text)

    def test_verbatim_copy_detected(self):
        prose = "Tech concentration is reckless given current multiples."
        self.assertTrue(is_verbatim_r1_copy(prose, prose))
        self.assertTrue(is_verbatim_r1_copy(prose, prose + " "))

    def test_distinct_rebuttal_not_flagged(self):
        r1 = "Tech concentration is reckless given current multiples."
        r2 = "Charles davinci argues growth justifies NVDA, but I still see no margin of safety."
        self.assertFalse(is_verbatim_r1_copy(r1, r2))

    def test_build_round2_prompt_names_peers_and_forbids_copy(self):
        hypatia = PANELIST_ROLES["hypatia"]
        davinci = PANELIST_ROLES["davinci"]
        messages = [
            {
                "content": (
                    f"**[ROUND 1] {hypatia}**:\n"
                    "* **Portfolio Overview**: Concentration risk is elevated.\n"
                )
            },
            {
                "content": (
                    f"**[ROUND 1] {davinci}**:\n"
                    "* **Portfolio Overview**: Growth names still have runway.\n"
                )
            },
        ]
        prompt = build_round2_user_prompt("hypatia", messages)
        self.assertIn(davinci, prompt)
        self.assertIn("do not copy", prompt.lower())
        self.assertIn("first sentence", prompt.lower())
        self.assertIn("50%", prompt)
        self.assertIn("Concentration risk", prompt)
        self.assertIn("Growth names", prompt)


if __name__ == "__main__":
    unittest.main()
