"""Tests for Invest AI briefing visual style SSOT."""
import unittest

from src.core.board_roster import PANELIST_ROLES
from src.output import briefing_style, reporting


class BriefingStyleTests(unittest.TestCase):
    def test_css_variables_present(self):
        css = briefing_style.executive_briefing_css()
        self.assertIn("--bg-canvas: #121212", css)
        self.assertIn("--brand-sage: #95b8a2", css)
        self.assertIn(".chart-img", css)
        self.assertNotIn("filter:", css)

    def test_verdict_pills_use_semantic_colors(self):
        pills = briefing_style.verdict_pill_styles()
        self.assertIn(briefing_style.BULL_BG, pills["BUY"])
        self.assertIn(briefing_style.BEAR_BG, pills["SELL"])
        self.assertIn(briefing_style.WARN_BG, pills["TRIM"])

    def test_chart_typography_tokens(self):
        self.assertEqual(briefing_style.CHART_DATALABEL_ON_DARK, briefing_style.TEXT_HIGHLIGHT)
        self.assertEqual(briefing_style.CHART_DATALABEL_WEIGHT, 700)
        self.assertEqual(briefing_style.CHART_LEGEND_FONT_SIZE, 14)
        self.assertEqual(briefing_style.CHART_CANVAS_DARK, briefing_style.BG_CANVAS)

        bull = briefing_style.sotu_quote_colors(f"{PANELIST_ROLES['hypatia']} ⭐⭐⭐⭐")
        self.assertTrue(bull[0].startswith("rgba("))
        self.assertIn(str(briefing_style.SOTU_BG_ALPHA), bull[0])
        sage = briefing_style.sotu_quote_colors(f"{PANELIST_ROLES['davinci']} ⭐⭐⭐")
        self.assertEqual(sage[1], briefing_style.BRAND_SAGE)
        bear = briefing_style.sotu_quote_colors(f"{PANELIST_ROLES['aurelius']} ⭐")
        self.assertTrue(bear[0].startswith("rgba("))

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
        self.assertIn("chart-img", html)
        self.assertNotIn("chart-img-pie", html)


if __name__ == "__main__":
    unittest.main()
