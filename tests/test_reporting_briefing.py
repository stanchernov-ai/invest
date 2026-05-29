import unittest
from unittest.mock import patch

from src.output import reporting


class BenchmarkChartTests(unittest.TestCase):
    def test_uses_portfolio_twr_index_not_raw_value_spike(self):
        history = {
            "20250101": {"portfolio": 100_000, "portfolio_index": 100.0, "spy": 500, "qqq": 400},
            "20250201": {"portfolio": 100_500, "portfolio_index": 100.5, "spy": 505, "qqq": 402},
            "20250301": {"portfolio": 250_000, "portfolio_index": 101.0, "spy": 510, "qqq": 405},
        }
        with patch.object(reporting, "get_quickchart_short_url", return_value="https://example.com/chart.png") as mock_url:
            url = reporting.build_benchmark_line_chart(history)
        self.assertEqual(url, "https://example.com/chart.png")
        config = mock_url.call_args[0][0]
        port = config["data"]["datasets"][0]["data"]
        spy = config["data"]["datasets"][1]["data"]
        self.assertAlmostEqual(port[0], 100.0)
        self.assertAlmostEqual(port[-1], 101.0)
        self.assertLess(abs(port[-1] - spy[-1]), 5)

    def test_rebase_index_series(self):
        rebased = reporting._rebase_index_series([None, 50.0, 75.0])
        self.assertIsNone(rebased[0])
        self.assertAlmostEqual(rebased[1], 100.0)
        self.assertAlmostEqual(rebased[2], 150.0)


class BriefingCopyTests(unittest.TestCase):
    def test_sanitize_qa_amendment_jargon(self):
        raw = "As per the QA Amendment protocol, no alpha pick today. The board remains cautious."
        cleaned = reporting._sanitize_briefing_text(raw)
        self.assertNotIn("QA Amendment", cleaned)
        self.assertIn("no alpha pick", cleaned.lower())

    def test_alpha_pick_hidden_for_none_symbol(self):
        self.assertFalse(reporting._alpha_pick_displayable({"symbol": "NONE", "champion_quote": "wait"}))

    def test_debate_hidden_for_empty_content(self):
        self.assertFalse(reporting._debate_has_content("Short."))


class ChartColorTests(unittest.TestCase):
    def _channel_max(self, hex_color: str) -> int:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return max(r, g, b)

    def test_gradual_scale_spreads_similar_positive_returns(self):
        colors = reporting.colors_for_metric([5.0, 12.0, 28.0, 41.0])
        self.assertEqual(len(colors), 4)
        self.assertNotEqual(colors[0], colors[-1])
        self.assertNotEqual(colors[1], colors[2])

    def test_positive_palette_uses_dark_greens_only(self):
        colors = reporting.colors_for_metric([5.0, 12.0, 28.0, 41.0])
        for c in colors:
            h = c.lstrip("#")
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            self.assertGreater(g, r)
            self.assertGreater(g, b)
            self.assertLessEqual(max(r, g, b), 0x66)

    def test_negative_palette_uses_dark_reds_only(self):
        colors = reporting.colors_for_metric([-41.0, -12.0, -5.0])
        for c in colors:
            self.assertGreaterEqual(self._channel_max(c), 0x1c)

    def test_diverging_scale_crosses_zero(self):
        colors = reporting.colors_for_metric([-15.0, -3.0, 4.0, 20.0])
        self.assertEqual(len(colors), 4)
        self.assertNotEqual(colors[0], colors[-1])

    def test_pie_uses_metric_colors_not_fixed_buckets(self):
        ledger = [
            ("A", {"Total": 5000, "Personal_Return_Pct": 8.0}),
            ("B", {"Total": 6000, "Personal_Return_Pct": 22.0}),
            ("C", {"Total": 7000, "Personal_Return_Pct": 35.0}),
        ]
        with patch.object(reporting, "get_quickchart_short_url", return_value="https://example.com/pie.png") as mock_url:
            reporting.build_portfolio_pie_chart(ledger)
        colors = mock_url.call_args[0][0]["data"]["datasets"][0]["backgroundColor"]
        self.assertEqual(len(colors), 3)
        self.assertNotEqual(colors[0], colors[-1])

    def test_bar_chart_hides_legend_and_labels_y_axis(self):
        ledger = [
            ("AAPL", {"Personal_Return_Pct": 10.0}),
            ("MSFT", {"Personal_Return_Pct": -5.0}),
        ]
        with patch.object(reporting, "get_quickchart_short_url", return_value="https://example.com/bar.png") as mock_url:
            reporting.build_returns_bar_chart(ledger)
        opts = mock_url.call_args[0][0]["options"]
        self.assertFalse(opts["plugins"]["legend"]["display"])
        self.assertEqual(opts["scales"]["y"]["title"]["text"], "Return (%)")


class BriefingHtmlTests(unittest.TestCase):
    def test_section_order_and_footer(self):
        html = reporting.generate_html_briefing(
            total_val=150_000,
            qqq_trend=5.0,
            portfolio_3m_trend=3.0,
            mandate="CAGR of 12.00 percent projected balance at age 65 is $1,000,000.00",
            chairman_data={
                "portfolio_positions": [],
                "watchlist_positions": [],
                "alpha_pick": {"symbol": "NONE", "champion_quote": "As per the QA Amendment protocol, none."},
                "upcoming_events": [],
            },
            cos_data={"state_of_the_union_quotes": [], "boardroom_brawl": "x" * 100},
            matrix_md="",
            unicorn_trades=[],
            sorted_ledger=[],
            account_returns={
                "updated": "2026-05-29",
                "returns": {"Total": {"ytd": 1.0, "12m": 2.0}},
            },
            chart_urls={},
        )
        twr_pos = html.find("Time-Weighted Returns")
        action_pos = html.find("The Action Plan")
        sotu_pos = html.find("The State of the Union")
        self.assertLess(twr_pos, action_pos)
        self.assertLess(action_pos, sotu_pos)
        self.assertIn("Invest AI Daily Briefing", html)
        self.assertNotIn("Generated autonomously", html)
        self.assertNotIn("The Alpha Pick", html)


if __name__ == "__main__":
    unittest.main()
