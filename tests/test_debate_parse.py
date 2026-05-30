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
        franklin = PANELIST_ROLES["franklin"]
        darwin = PANELIST_ROLES["darwin"]
        cumulative = {
            "content": (
                f"**[ROUND 1] {franklin}**:\n"
                "* **ANET**: Strong Buy (8/10).\n\n"
                f"**[ROUND 2 REBUTTAL] {franklin}**:\n"
                "* **ANET**: Strong Sell (7/10).\n\n"
                f"**[ROUND 2 REBUTTAL] {darwin}**:\n"
                "* **ANET**: Sell (6/10).\n"
            )
        }
        matrix = parse_board_matrix([cumulative], ["ANET"])
        self.assertEqual(matrix["ANET"]["franklin"], "Strong Sell")
        self.assertEqual(matrix["ANET"]["darwin"], "Sell")


if __name__ == "__main__":
    unittest.main()
