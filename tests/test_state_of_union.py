import unittest

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
            "buffett": {
                "overall_portfolio_critique": (
                    "I disagree with Peter Lynch on NVDA — his growth thesis ignores moat erosion."
                ),
                "portfolio_verdicts": [{"verdict": "Trim", "conviction_score": 8}],
            },
            "lynch": {
                "overall_portfolio_critique": "I agree with Buffett that we hold too much mega-cap tech.",
                "portfolio_verdicts": [{"verdict": "Hold", "conviction_score": 6}],
            },
        }
        round1 = {
            "buffett": (
                "The portfolio is dangerously concentrated in high-multiple tech. "
                "Sector risk outweighs individual stock quality."
            ),
            "lynch": (
                "Strong growth names but you are light on consumer staples diversification."
            ),
        }
        quotes = build_state_of_union_quotes(raw, round1_critiques=round1)
        self.assertEqual(len(quotes), 5)
        buffett = quotes[0]
        self.assertIn("Warren Buffett", buffett["board_member"])
        self.assertIn("concentrated", buffett["quote"])
        self.assertNotIn("NVDA:", buffett["quote"])
        self.assertNotIn("Peter Lynch", buffett["quote"])

    def test_rejects_rebuttal_only_round2_when_round1_missing(self):
        raw = {
            "buffett": {
                "overall_portfolio_critique": (
                    "I fundamentally disagree with Peter Lynch on NVDA and TSM while conceding on GOOGL."
                ),
                "portfolio_verdicts": [],
            },
        }
        quotes = build_state_of_union_quotes(raw)
        buffett = quotes[0]
        self.assertIn("peer rebuttal only", buffett["quote"])

    def test_fallback_when_critique_missing(self):
        quotes = build_state_of_union_quotes({"simons": {"portfolio_verdicts": []}})
        simons = quotes[4]
        self.assertIn("Jim Simons", simons["board_member"])
        self.assertIn("No overall portfolio critique", simons["quote"])


if __name__ == "__main__":
    unittest.main()
