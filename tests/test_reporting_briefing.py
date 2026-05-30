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

    def test_line_chart_uses_compact_month_labels(self):
        history = {
            f"2025{m:02d}01": {
                "portfolio_index": 100.0 + m,
                "spy": 500 + m,
                "qqq": 400 + m,
            }
            for m in range(1, 13)
        }
        with patch.object(reporting, "get_quickchart_short_url", return_value="https://example.com/chart.png") as mock_url:
            reporting.build_benchmark_line_chart(history)
        labels = mock_url.call_args[0][0]["data"]["labels"]
        self.assertLessEqual(len(labels), reporting.LINE_CHART_MAX_POINTS)
        self.assertRegex(labels[0], r"^[A-Z][a-z]{2} '\d{2}$")
        self.assertNotRegex(labels[0], r"^\d{8}$")
        self.assertEqual(mock_url.call_args[1]["background_color"], reporting.CHART_BG)


class BriefingCopyTests(unittest.TestCase):
    def test_sanitize_qa_amendment_jargon(self):
        raw = "As per the QA Amendment protocol, no alpha pick today. The board remains cautious."
        cleaned = reporting._sanitize_briefing_text(raw)
        self.assertNotIn("QA Amendment", cleaned)
        self.assertIn("no alpha pick", cleaned.lower())

    def test_sanitize_vote_engine_and_system_override_jargon(self):
        raw = (
            "[SYSTEM OVERRIDE: 10% Liquidation Cap Reached. Hold enforced.] "
            "[VOTE ENGINE] Deterministic mandate from Round 2 panel votes "
            "(buy_side=0/5, sell_side=5/5)."
        )
        cleaned = reporting._sanitize_briefing_text(raw)
        self.assertNotIn("VOTE ENGINE", cleaned)
        self.assertNotIn("SYSTEM OVERRIDE", cleaned)
        self.assertNotIn("buy_side", cleaned)
        self.assertIn("liquidation limit", cleaned.lower())

    def test_sanitize_position_replaces_boilerplate_champion(self):
        pos = reporting._sanitize_position_for_briefing({
            "symbol": "NVDA",
            "final_verdict": "Buy",
            "synthesis": "[VOTE ENGINE] Deterministic mandate from Round 2 panel votes (buy_side=3/5, sell_side=2/5).",
            "narrative": {
                "champion": "Peter Lynch",
                "champion_quote": "Vote-engine mandate from unanimous / deterministic Round 2 panel votes.",
                "dissenter": "None",
                "dissenter_quote": "N/A",
            },
        })
        self.assertNotIn("VOTE ENGINE", pos["synthesis"])
        self.assertIn("Peter Lynch", pos["narrative"]["champion_quote"])
        self.assertNotIn("Vote-engine", pos["narrative"]["champion_quote"])

    def test_briefing_html_hides_internal_jargon(self):
        html = reporting.generate_html_briefing(
            total_val=150_000,
            qqq_trend=5.0,
            portfolio_3m_trend=3.0,
            mandate="CAGR of 12.00 percent projected balance at age 65 is $1,000,000.00",
            chairman_data={
                "portfolio_positions": [
                    {
                        "symbol": "TSM",
                        "final_verdict": "Hold",
                        "synthesis": (
                            "[SYSTEM OVERRIDE: 10% Liquidation Cap Reached. Hold enforced.] "
                            "[VOTE ENGINE] Deterministic mandate from Round 2 panel votes "
                            "(buy_side=0/5, sell_side=5/5)."
                        ),
                        "narrative": {
                            "champion": "Warren Buffett",
                            "champion_quote": "Vote-engine mandate from unanimous / deterministic Round 2 panel votes.",
                            "dissenter": "None",
                            "dissenter_quote": "N/A",
                        },
                    }
                ],
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
        self.assertNotIn("VOTE ENGINE", html)
        self.assertNotIn("SYSTEM OVERRIDE", html)
        self.assertNotIn("buy_side", html)

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

    def test_positive_palette_spreads_with_readable_light_tints(self):
        colors = reporting.colors_for_metric([5.0, 12.0, 28.0, 41.0])
        for c in colors:
            h = c.lstrip("#")
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            self.assertGreater(g, r)
            self.assertGreaterEqual(max(r, g, b), 0x80)
        self.assertNotEqual(colors[0], colors[-1])

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

    def test_pie_charts_hide_legend_and_use_taller_canvas(self):
        ledger = [
            ("A", {"Total": 5000, "Personal_Return_Pct": 8.0}),
            ("B", {"Total": 6000, "Personal_Return_Pct": 22.0}),
        ]
        with patch.object(reporting, "get_quickchart_short_url", return_value="https://example.com/pie.png") as mock_url:
            reporting.build_portfolio_pie_chart(ledger)
        opts = mock_url.call_args[0][0]["options"]
        self.assertIs(opts["plugins"]["legend"], False)
        self.assertFalse(opts["legend"]["display"])
        self.assertFalse(opts["plugins"]["datalabels"]["display"])
        self.assertEqual(mock_url.call_args[1]["width"], reporting.PIE_CHART_WIDTH)
        self.assertEqual(mock_url.call_args[1]["height"], reporting.PIE_CHART_HEIGHT)

    def test_bar_chart_hides_legend_and_labels_y_axis(self):
        ledger = [
            ("AAPL", {"Personal_Return_Pct": 10.0}),
            ("MSFT", {"Personal_Return_Pct": -5.0}),
        ]
        with patch.object(reporting, "get_quickchart_short_url", return_value="https://example.com/bar.png") as mock_url:
            reporting.build_returns_bar_chart(ledger)
        opts = mock_url.call_args[0][0]["options"]
        datalabels = opts["plugins"]["datalabels"]
        self.assertIs(opts["plugins"]["legend"], False)
        self.assertEqual(opts["scales"]["y"]["title"]["text"], "Return (%)")
        self.assertEqual(datalabels["color"], reporting.CHART_LABEL_COLOR)
        self.assertIn("formatter", datalabels)
        self.assertEqual(mock_url.call_args[1]["background_color"], reporting.CHART_BG)


class BriefingHtmlTests(unittest.TestCase):
    def test_section_order_and_footer(self):
        html = reporting.generate_html_briefing(
            total_val=150_000,
            qqq_trend=5.0,
            portfolio_3m_trend=3.0,
            mandate="CAGR of 12.00 percent projected balance at age 65 is $1,000,000.00",
            chairman_data={
                "portfolio_positions": [
                    {
                        "symbol": "NVDA",
                        "final_verdict": "Buy",
                        "synthesis": "Strong momentum.",
                        "narrative": {"champion": "Buffett", "champion_quote": "Buy.", "dissenter": "NONE", "dissenter_quote": "N/A"},
                    }
                ],
                "watchlist_positions": [],
                "alpha_pick": {"symbol": "NONE", "champion_quote": "As per the QA Amendment protocol, none."},
                "upcoming_events": [],
            },
            cos_data={
                "state_of_the_union_quotes": [
                    {"board_member": "Warren Buffett", "quote": "Markets remain rational long term."},
                ],
                "boardroom_brawl": "x" * 100,
            },
            matrix_md="",
            unicorn_trades=[],
            sorted_ledger=[],
            account_returns={
                "updated": "2026-05-29",
                "returns": {"Total": {"ytd": 1.0, "12m": 2.0}},
            },
            chart_urls={
                "line_chart_url": "https://example.com/line.png",
                "bar_chart_url": "https://example.com/bar.png",
            },
        )
        perf_pos = html.find("Performance vs. Benchmark")
        action_pos = html.find("The Action Plan")
        twr_pos = html.find("Time-Weighted Returns")
        sotu_pos = html.find("The State of the Union")
        self.assertLess(perf_pos, action_pos)
        self.assertLess(action_pos, twr_pos)
        self.assertLess(twr_pos, sotu_pos)
        self.assertIn("Symbol", html)
        self.assertIn("NVDA", html)
        self.assertIn("Invest AI Daily Briefing", html)
        self.assertNotIn("Generated autonomously", html)
        self.assertNotIn("The Alpha Pick", html)
        self.assertIn("12.00%", html)
        self.assertNotIn("12.00 percent", html)


if __name__ == "__main__":
    unittest.main()
