"""Tests for Invest AI briefing visual style SSOT."""
import unittest
from unittest.mock import MagicMock, patch

from src.core.board_roster import PANELIST_ROLES
from src.output import briefing_style, reporting


class BriefingStyleTests(unittest.TestCase):
    def test_chart_magnitude_colors_rank_by_return(self):
        colors = briefing_style.chart_magnitude_colors([9.0, 18.0, 40.0])
        self.assertEqual(len(colors), 3)
        # Higher return → darker green (lower channel sum on mint→emerald ramp).
        self.assertGreater(sum(int(colors[0][i:i + 2], 16) for i in (1, 3, 5)),
                           sum(int(colors[2][i:i + 2], 16) for i in (1, 3, 5)))

    def test_chart_magnitude_colors_sign_semantics(self):
        colors = briefing_style.chart_magnitude_colors([12.0, -8.0, 0.02])
        self.assertTrue(colors[0].startswith("#"))
        self.assertTrue(colors[1].startswith("#"))
        self.assertEqual(colors[2], briefing_style.CHART_NEUTRAL)

    def test_portrait_clip_circular_on_img(self):
        styles = briefing_style.portrait_clip_styles("hypatia", size=48)
        self.assertIn("border-radius:50%", styles["img"])
        self.assertIn("width:48px;height:48px", styles["img"])

    def test_sotu_portrait_uses_circular_clip(self):
        styles = briefing_style.portrait_clip_styles("hypatia")
        self.assertIn("width:128px;height:128px", styles["img"])
        self.assertIn("border-radius:50%", styles["img"])

    def test_executive_briefing_css_omits_qa_box(self):
        css = briefing_style.executive_briefing_css()
        self.assertNotIn(".qa-box", css)

    def test_chart_charge_colors_sign_semantics(self):
        colors = briefing_style.chart_charge_colors([12.0, -8.0, 0.02, 5.0])
        self.assertEqual(colors[0], briefing_style.CHART_GAIN)
        self.assertEqual(colors[1], briefing_style.CHART_LOSS)
        self.assertEqual(colors[2], briefing_style.CHART_NEUTRAL)
        self.assertIn(colors[3], briefing_style.CHART_GAIN_VARIANTS)

    def test_css_variables_present(self):
        css = briefing_style.executive_briefing_css()
        self.assertIn("--bg-canvas: #121212", css)
        self.assertIn("--brand-sage: #95b8a2", css)
        self.assertIn(".chart-img", css)
        self.assertNotIn("filter:", css)

    def test_inline_styles_cover_stealth_wealth_palette(self):
        styles = briefing_style.executive_briefing_inline_styles()
        self.assertIn(briefing_style.BG_CANVAS, styles["body"])
        self.assertIn(briefing_style.BG_CONTAINER, styles["container_td"])
        self.assertIn(briefing_style.BG_SURFACE, styles["metric_box"])
        self.assertIn(briefing_style.BRAND_SAGE, styles["h1"])
        self.assertIn(briefing_style.TEXT_PRIMARY, styles["p"])
        self.assertIn(briefing_style.TEXT_HIGHLIGHT, styles["strong"])

    def test_verdict_pills_use_semantic_colors(self):
        pills = briefing_style.verdict_pill_styles()
        self.assertIn(briefing_style.BULL_BG, pills["ACCUMULATE CANDIDATE"])
        self.assertIn(briefing_style.BEAR_BG, pills["BEARISH (LIQUIDATE)"])
        self.assertIn(briefing_style.WARN_BG, pills["REDUCE EXPOSURE"])

    def test_chart_typography_tokens(self):
        self.assertEqual(briefing_style.CHART_DATALABEL_ON_DARK, briefing_style.TEXT_HIGHLIGHT)
        self.assertEqual(briefing_style.CHART_DATALABEL_WEIGHT, 700)
        self.assertEqual(briefing_style.CHART_LEGEND_FONT_SIZE, 14)
        self.assertEqual(briefing_style.CHART_CANVAS_DARK, briefing_style.BG_CANVAS)
        self.assertEqual(briefing_style.QUICKCHART_DEVICE_PIXEL_RATIO, 3)

    def test_quickchart_short_url_requests_retina_device_pixel_ratio(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"url": "https://quickchart.io/chart/render/abc"}
        mock_resp.raise_for_status = MagicMock()
        with patch("src.output.reporting.requests.post", return_value=mock_resp) as post:
            url = reporting.get_quickchart_short_url({"type": "bar"}, width=388, height=300)
        self.assertEqual(url, "https://quickchart.io/chart/render/abc")
        payload = post.call_args.kwargs.get("json") or post.call_args[1].get("json")
        self.assertEqual(payload["devicePixelRatio"], briefing_style.QUICKCHART_DEVICE_PIXEL_RATIO)

        bull = briefing_style.sotu_quote_style(f"{PANELIST_ROLES['hypatia']} (⭐⭐⭐⭐ Bullish)")
        self.assertEqual(bull[0], briefing_style.SOTU_BULL_BG)
        self.assertEqual(bull[1], briefing_style.BULL_TEXT)
        self.assertNotIn("box-shadow", bull[2])
        self.assertIn(briefing_style.SOTU_BULL_EDGE, bull[2])

        three_bull = briefing_style.sotu_quote_style(f"{PANELIST_ROLES['davinci']} (⭐⭐⭐ Bullish)")
        self.assertEqual(three_bull[0], briefing_style.SOTU_BULL_BG)
        self.assertEqual(three_bull[1], briefing_style.BULL_TEXT)

        neutral = briefing_style.sotu_quote_style(f"{PANELIST_ROLES['suntzu']} (⭐⭐ Neutral)")
        self.assertEqual(neutral[0], briefing_style.SOTU_NEUTRAL_BG)
        self.assertEqual(neutral[1], briefing_style.SOTU_NEUTRAL_TEXT)
        self.assertNotIn("box-shadow", neutral[2])

        bear = briefing_style.sotu_quote_style(f"{PANELIST_ROLES['aurelius']} (⭐ Bearish)")
        self.assertEqual(bear[0], briefing_style.SOTU_BEAR_BG)
        self.assertEqual(bear[1], briefing_style.BEAR_TEXT)
        self.assertNotIn("box-shadow", bear[2])

    def test_alpha_pick_logo_spotlight_chip(self):
        lg = briefing_style.ticker_logo_inline_style(size=72, spotlight=True)
        self.assertIn("#ffffff", lg)
        self.assertIn("padding:10px", lg)

    def test_investor_qa_summary_uses_advisory_not_emoji(self):
        html = briefing_style.format_investor_qa_summary([
            {"agent_role": "Post Mortem QA Auditor", "is_compliant": True},
            {"agent_role": "Prompt Engineer QA", "is_compliant": False},
        ])
        self.assertIn("ADVISORY", html)
        self.assertIn("PASS", html)
        self.assertNotIn("&#10060;", html)
        self.assertNotIn("&#9989;", html)

    def test_crucible_palette_is_cold_iron_not_bear_red(self):
        styles = briefing_style.executive_briefing_inline_styles()
        box = styles["crucible_box"]
        heading = styles["crucible_heading"]
        self.assertIn(briefing_style.CRUCIBLE_BG, box)
        self.assertIn(briefing_style.CRUCIBLE_BORDER, box)
        self.assertIn(briefing_style.CRUCIBLE_TEXT, box)
        self.assertNotIn(briefing_style.BEAR_BG, box)
        self.assertNotIn(briefing_style.BEAR_TEXT, box)
        self.assertIn(briefing_style.CRUCIBLE_HEADER, heading)
        self.assertNotIn(briefing_style.BEAR_TEXT, heading)

    def test_briefing_html_includes_inline_dark_theme(self):
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
        self.assertIn('background-color:#121212', html.replace(" ", ""))
        self.assertIn('background-color:#1e1e1e', html.replace(" ", ""))
        self.assertIn(briefing_style.BRAND_SAGE, html)
        self.assertIn('bgcolor="#121212"', html)
        self.assertIn("chart-img", html)
        self.assertNotIn("chart-img-pie", html)


if __name__ == "__main__":
    unittest.main()
