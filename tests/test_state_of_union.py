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
            "franklin": {
                "overall_portfolio_critique": (
                    "I disagree with Charles Darwin on NVDA — his growth thesis ignores moat erosion."
                ),
                "portfolio_verdicts": [{"verdict": "Trim", "conviction_score": 8}],
            },
            "darwin": {
                "overall_portfolio_critique": "I agree with Franklin that we hold too much mega-cap tech.",
                "portfolio_verdicts": [{"verdict": "Hold", "conviction_score": 6}],
            },
        }
        round1 = {
            "franklin": (
                "The portfolio is dangerously concentrated in high-multiple tech. "
                "Sector risk outweighs individual stock quality."
            ),
            "darwin": (
                "Strong growth names but you are light on consumer staples diversification."
            ),
        }
        quotes = build_state_of_union_quotes(raw, round1_critiques=round1)
        self.assertEqual(len(quotes), 5)
        franklin = quotes[0]
        self.assertIn(PANELIST_ROLES["franklin"], franklin["board_member"])
        self.assertIn("concentrated", franklin["quote"])
        self.assertNotIn("NVDA:", franklin["quote"])
        self.assertNotIn(PANELIST_ROLES["darwin"], franklin["quote"])

    def test_rejects_rebuttal_only_round2_when_round1_missing(self):
        raw = {
            "franklin": {
                "overall_portfolio_critique": (
                    "I fundamentally disagree with Charles Darwin on NVDA and TSM while conceding on GOOGL."
                ),
                "portfolio_verdicts": [],
            },
        }
        quotes = build_state_of_union_quotes(raw)
        franklin = quotes[0]
        self.assertIn("peer rebuttal only", franklin["quote"])

    def test_fallback_when_critique_missing(self):
        quotes = build_state_of_union_quotes({"pythagoras": {"portfolio_verdicts": []}})
        pythagoras = quotes[4]
        self.assertIn(PANELIST_ROLES["pythagoras"], pythagoras["board_member"])
        self.assertIn("No overall portfolio critique", pythagoras["quote"])


if __name__ == "__main__":
    unittest.main()
