"""Tests for Round 2 debate log parsing helpers."""
import unittest

from src.core.board_roster import PANELIST_ROLES
from src.core.rebuttal import parse_ticker_verdict_from_line
from src.qa_pipeline import parse_board_matrix


class TestDebateParse(unittest.TestCase):
    def test_strong_sell_not_misread_as_strong_buy(self):
        parsed = parse_ticker_verdict_from_line("* **ANET**: Strong Sell (7/10).")
        self.assertEqual(parsed, ("ANET", "Strong Sell"))

    def test_pass_with_rationale_containing_sell_word(self):
        parsed = parse_ticker_verdict_from_line(
            "* **AMD**: Pass (4/10). They sell chips, but lack CUDA moat."
        )
        self.assertEqual(parsed, ("AMD", "Pass"))

    def test_cumulative_round2_matrix_uses_latest_panelist_block(self):
        hypatia = PANELIST_ROLES["hypatia"]
        davinci = PANELIST_ROLES["davinci"]
        cumulative = {
            "content": (
                f"**[ROUND 1] {hypatia}**:\n"
                "* **ANET**: Strong Buy (8/10).\n\n"
                f"**[ROUND 2 REBUTTAL] {hypatia}**:\n"
                "* **ANET**: Strong Sell (7/10).\n\n"
                f"**[ROUND 2 REBUTTAL] {davinci}**:\n"
                "* **ANET**: Sell (6/10).\n"
            )
        }
        matrix = parse_board_matrix([cumulative], ["ANET"])
        self.assertEqual(matrix["ANET"]["hypatia"], "Strong Sell")
        self.assertEqual(matrix["ANET"]["davinci"], "Sell")


if __name__ == "__main__":
    unittest.main()
