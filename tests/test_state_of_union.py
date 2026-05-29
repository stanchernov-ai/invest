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

    def test_builds_from_overall_portfolio_critique(self):
        raw = {
            "buffett": {
                "overall_portfolio_critique": (
                    "The portfolio is dangerously concentrated in high-multiple tech. "
                    "Sector risk outweighs individual stock quality."
                ),
                "portfolio_verdicts": [{"verdict": "Trim", "conviction_score": 8}],
            },
            "lynch": {
                "overall_portfolio_critique": (
                    "Strong growth names but you are light on consumer staples diversification."
                ),
                "portfolio_verdicts": [{"verdict": "Hold", "conviction_score": 6}],
            },
        }
        quotes = build_state_of_union_quotes(raw)
        self.assertEqual(len(quotes), 5)
        buffett = quotes[0]
        self.assertIn("Warren Buffett", buffett["board_member"])
        self.assertIn("concentrated", buffett["quote"])
        self.assertNotIn("NVDA:", buffett["quote"])

    def test_fallback_when_critique_missing(self):
        quotes = build_state_of_union_quotes({"simons": {"portfolio_verdicts": []}})
        simons = quotes[4]
        self.assertIn("Jim Simons", simons["board_member"])
        self.assertIn("No overall portfolio critique", simons["quote"])


if __name__ == "__main__":
    unittest.main()
