import unittest

from src.core.board_roster import PANELIST_ROLES
from src.core.state_of_union import build_state_of_union_quotes, _stance_label


class TestStateOfUnion(unittest.TestCase):
    def test_stance_bullish_on_net_buys(self):
        verdicts = [
            {"verdict": "Strong Buy", "conviction_score": 9},
            {"verdict": "Buy", "conviction_score": 8},
        ]
        self.assertIn("Bullish", _stance_label(verdicts))

    def test_stance_bearish_on_net_sells(self):
        verdicts = [
            {"verdict": "Sell", "conviction_score": 9},
            {"verdict": "Trim", "conviction_score": 8},
        ]
        self.assertIn("Bearish", _stance_label(verdicts))

    def test_builds_from_round1_portfolio_overview(self):
        raw = {
            "hypatia": {
                "overall_portfolio_critique": (
                    "I disagree with Charles davinci on NVDA — his growth thesis ignores moat erosion."
                ),
                "portfolio_verdicts": [{"verdict": "Trim", "conviction_score": 8}],
            },
            "davinci": {
                "overall_portfolio_critique": "I agree with hypatia that we hold too much mega-cap tech.",
                "portfolio_verdicts": [{"verdict": "Hold", "conviction_score": 6}],
            },
        }
        round1 = {
            "hypatia": (
                "The portfolio is dangerously concentrated in high-multiple tech. "
                "Sector risk outweighs individual stock quality."
            ),
            "davinci": (
                "Strong growth names but you are light on consumer staples diversification."
            ),
        }
        quotes = build_state_of_union_quotes(raw, round1_critiques=round1)
        self.assertEqual(len(quotes), 5)
        hypatia = quotes[0]
        self.assertIn(PANELIST_ROLES["hypatia"], hypatia["board_member"])
        self.assertIn("concentrated", hypatia["quote"])
        self.assertNotIn("NVDA:", hypatia["quote"])
        self.assertNotIn(PANELIST_ROLES["davinci"], hypatia["quote"])

    def test_rejects_rebuttal_only_round2_when_round1_missing(self):
        raw = {
            "hypatia": {
                "overall_portfolio_critique": (
                    "I fundamentally disagree with Charles davinci on NVDA and TSM while conceding on GOOGL."
                ),
                "portfolio_verdicts": [],
            },
        }
        quotes = build_state_of_union_quotes(raw)
        hypatia = quotes[0]
        self.assertIn("peer rebuttal only", hypatia["quote"])

    def test_fallback_when_critique_missing(self):
        quotes = build_state_of_union_quotes({"aurelius": {"portfolio_verdicts": []}})
        aurelius = quotes[4]
        self.assertIn(PANELIST_ROLES["aurelius"], aurelius["board_member"])
        self.assertIn("No overall portfolio critique", aurelius["quote"])


if __name__ == "__main__":
    unittest.main()
