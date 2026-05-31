"""Tests for shared debate log formatting (watchlist Pass slimming)."""
import unittest

from src.core.debate_format import (
    format_portfolio_verdict_markdown_lines,
    format_watchlist_verdict_markdown_lines,
)


class TestDebateFormat(unittest.TestCase):
    def test_watchlist_passes_aggregate_to_one_line(self):
        rows = [{"symbol": f"W{i}", "verdict": "Pass", "conviction_score": 5, "analysis": "No edge."} for i in range(15)]
        lines = format_watchlist_verdict_markdown_lines(rows)
        self.assertEqual(len(lines), 1)
        self.assertIn("no buy case (15 names)", lines[0])
        self.assertNotRegex(lines[0], r"\bPass\b")

    def test_watchlist_buys_stay_individual(self):
        rows = [
            {"symbol": "PLTR", "verdict": "High Conviction (Overweight)", "conviction_score": 9, "analysis": "Accelerating."},
            {"symbol": "META", "verdict": "Pass", "conviction_score": 3, "analysis": "Fully priced."},
        ]
        lines = format_watchlist_verdict_markdown_lines(rows)
        self.assertEqual(len(lines), 2)
        self.assertIn("PLTR", lines[0])
        self.assertIn("High Conviction (Overweight)", lines[0])
        self.assertIn("no buy case (1 names)", lines[1])

    def test_portfolio_lines_unchanged(self):
        rows = [{"symbol": "NVDA", "verdict": "Hold", "conviction_score": 6, "analysis": "Core."}]
        lines = format_portfolio_verdict_markdown_lines(rows)
        self.assertEqual(len(lines), 1)
        self.assertIn("NVDA", lines[0])


if __name__ == "__main__":
    unittest.main()
