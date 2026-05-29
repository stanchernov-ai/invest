import unittest

from src.output.reporting import build_unicorn_protocol_items


CHAIRMAN = {
    "portfolio_positions": [{
        "symbol": "GOOGL",
        "final_verdict": "Hold",
        "synthesis": "Unanimous hold on quality compounder.",
        "narrative": {
            "champion": "Warren Buffett",
            "champion_quote": "Moat intact.",
            "dissenter": "None",
            "dissenter_quote": "N/A",
        },
    }],
    "watchlist_positions": [],
}

RED_TEAM = {
    "bear_case_narrative": "Alpha risk.",
    "unicorn_rebuttals": [{"symbol": "GOOGL", "rebuttal": "Antitrust overhang could compress multiples."}],
}


class TestUnicornProtocol(unittest.TestCase):
    def test_enriches_chairman_and_red_team(self):
        items, symbols = build_unicorn_protocol_items(
            [{"symbol": "GOOGL", "verdict": "Hold"}],
            CHAIRMAN,
            {"GOOGL": {"image": "https://example.com/googl.png"}},
            RED_TEAM,
        )
        self.assertEqual(symbols, {"GOOGL"})
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["synthesis"], "Unanimous hold on quality compounder.")
        self.assertIn("Antitrust", items[0]["red_team_rebuttal"])

    def test_excludes_pass_verdicts(self):
        items, symbols = build_unicorn_protocol_items(
            [{"symbol": "XYZ", "verdict": "Pass"}],
            CHAIRMAN,
        )
        self.assertEqual(items, [])
        self.assertEqual(symbols, set())


if __name__ == "__main__":
    unittest.main()
