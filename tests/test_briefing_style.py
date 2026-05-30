"""Tests for Invest AI briefing visual style SSOT."""
import unittest

from src.output import briefing_style, reporting


class BriefingStyleTests(unittest.TestCase):
    def test_css_variables_present(self):
        css = briefing_style.executive_briefing_css()
        self.assertIn("--bg-canvas: #121212", css)
        self.assertIn("--brand-sage: #95b8a2", css)
        self.assertIn(briefing_style.CHART_IMG_FILTER, css)

    def test_verdict_pills_use_semantic_colors(self):
        pills = briefing_style.verdict_pill_styles()
        self.assertIn(briefing_style.BULL_BG, pills["BUY"])
        self.assertIn(briefing_style.BEAR_BG, pills["SELL"])
        self.assertIn(briefing_style.WARN_BG, pills["TRIM"])

    def test_sotu_star_mapping(self):
        bull = briefing_style.sotu_quote_colors("Warren Buffett ⭐⭐⭐⭐")
        self.assertEqual(bull[0], briefing_style.BULL_BG)
        sage = briefing_style.sotu_quote_colors("Peter Lynch ⭐⭐⭐")
        self.assertEqual(sage[1], briefing_style.BRAND_SAGE)
        bear = briefing_style.sotu_quote_colors("Jim Simons ⭐")
        self.assertEqual(bear[0], briefing_style.BEAR_BG)

    def test_briefing_html_includes_dark_theme(self):
        html = reporting.generate_html_briefing(
            total_val=150_000,
            qqq_trend=5.0,
            portfolio_3m_trend=3.0,
            mandate="CAGR of 12.00 percent projected balance at age 65 is $1,000,000.00",
            chairman_data={
                "portfolio_positions": [],
                "watchlist_positions": [],
                "alpha_pick": {"symbol": "NONE", "champion_quote": "N/A"},
                "upcoming_events": [],
            },
            cos_data={"state_of_the_union_quotes": [], "boardroom_brawl": "x" * 100},
            matrix_md="",
            unicorn_trades=[],
            sorted_ledger=[],
            chart_urls={},
        )
        self.assertIn("#121212", html)
        self.assertIn("#95b8a2", html)
        self.assertIn(briefing_style.CHART_IMG_FILTER, html)
        self.assertIn("chart-img", html)


if __name__ == "__main__":
    unittest.main()
