import re
import unittest
from unittest.mock import patch

from src.core.board_roster import PANELIST_AVATAR_URLS, PANELIST_ROLES
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
            "final_verdict": "Accumulate Candidate",
            "synthesis": "[VOTE ENGINE] Deterministic mandate from Round 2 panel votes (buy_side=3/5, sell_side=2/5).",
            "narrative": {
                "champion": PANELIST_ROLES["davinci"],
                "champion_quote": "Vote-engine mandate from unanimous / deterministic Round 2 panel votes.",
                "dissenter": "None",
                "dissenter_quote": "N/A",
            },
        })
        self.assertNotIn("VOTE ENGINE", pos["synthesis"])
        self.assertIn(PANELIST_ROLES["davinci"], pos["narrative"]["champion"])
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
                            "champion": PANELIST_ROLES["hypatia"],
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

    def test_alpha_pick_shows_three_tier_spotlight(self):
        html = reporting.generate_html_briefing(
            total_val=150_000,
            qqq_trend=5.0,
            portfolio_3m_trend=3.0,
            mandate="Test mandate.",
            chairman_data={
                "portfolio_positions": [],
                "watchlist_positions": [{
                    "symbol": "VRT",
                    "final_verdict": "Accumulate Candidate",
                    "synthesis": "The board sees AI infrastructure as the cycle winner.",
                    "supporting_members": [PANELIST_ROLES["tesla"]],
                    "narrative": {
                        "champion": PANELIST_ROLES["tesla"],
                        "champion_quote": "Critical infrastructure with explosive EPS growth.",
                        "dissenter": "None",
                        "dissenter_quote": "N/A",
                    },
                }],
                "alpha_pick": {
                    "symbol": "VRT",
                    "champion": PANELIST_ROLES["tesla"],
                    "champion_quote": "Critical infrastructure with explosive EPS growth.",
                },
                "upcoming_events": [],
            },
            cos_data={"state_of_the_union_quotes": [], "boardroom_brawl": ""},
            matrix_md="",
            unicorn_trades=[],
            sorted_ledger=[],
            chart_urls={},
            advanced_data={"VRT": {"image": "https://example.com/vrt.png"}},
            red_team_data={"bear_case_narrative": "Valuation stretched."},
        )
        self.assertIn("The Alpha Pick", html)
        self.assertIn("The Board", html)
        self.assertIn("AI infrastructure", html)
        self.assertIn("The Champion (Nikola Tesla)", html)
        self.assertIn(PANELIST_AVATAR_URLS["tesla"], html)
        self.assertIn("width:72px", html)
        self.assertIn("https://example.com/vrt.png", html)
        self.assertIn("The Crucible", html)
        self.assertIn("Valuation stretched", html)

    def test_upcoming_catalysts_from_advanced_data_when_chairman_empty(self):
        advanced = {
            "NVDA": {
                "next_earnings": "2026-06-05",
                "fcs_score": 3,
                "fcs_rationale": "Imminent Earnings Catalyst (+1)",
                "eps_estimated": 1.25,
            },
        }
        html = reporting.generate_html_briefing(
            total_val=100_000,
            qqq_trend=1.0,
            portfolio_3m_trend=1.0,
            mandate="Test mandate.",
            chairman_data={
                "portfolio_positions": [{"symbol": "NVDA", "final_verdict": "HOLD"}],
                "watchlist_positions": [],
                "upcoming_events": [],
            },
            cos_data={"state_of_the_union_quotes": [], "boardroom_brawl": ""},
            matrix_md="",
            unicorn_trades=[],
            sorted_ledger=[],
            chart_urls={},
            advanced_data=advanced,
        )
        self.assertIn("Upcoming Catalysts", html)
        self.assertIn("NVDA", html)
        self.assertIn("2026-06-05", html)
        self.assertNotIn("No major immediate catalysts flagged", html)

        self.assertFalse(reporting._debate_has_content("Short."))

    def test_debate_hidden_for_truncated_mid_sentence(self):
        truncated = "hypatia initiated by dismissing the entire portfolio as"
        self.assertFalse(reporting._debate_has_content(truncated))

    def test_debate_bubbles_hide_round_numbers(self):
        hypatia = PANELIST_ROLES["hypatia"]
        suntzu = PANELIST_ROLES["suntzu"]
        messages = [
            {
                "content": (
                    f"**[ROUND 1] {hypatia}**:\n"
                    "* **Portfolio Overview**: Moats matter more than momentum.\n"
                    "* **NVDA**: Bearish (Liquidate) (6/10). Premium multiple with no FCF support.\n"
                ),
            },
            {
                "content": (
                    f"**[ROUND 2 REBUTTAL] {suntzu}**:\n"
                    "* **Rebuttal Summary**: hypatia ignores the tape.\n"
                    "* **NVDA**: High Conviction (Overweight) (9/10). Relative strength confirms leadership.\n"
                ),
            },
        ]
        html = reporting.generate_html_briefing(
            total_val=100_000,
            qqq_trend=1.0,
            portfolio_3m_trend=1.0,
            mandate="Test mandate.",
            chairman_data={
                "portfolio_positions": [],
                "watchlist_positions": [],
                "alpha_pick": {"symbol": "NONE", "champion_quote": "N/A"},
                "upcoming_events": [],
            },
            cos_data={"state_of_the_union_quotes": [], "boardroom_brawl": "x" * 200},
            matrix_md="",
            unicorn_trades=[],
            sorted_ledger=[],
            chart_urls={},
            raw_board_messages=messages,
        )
        debate_start = html.index("The Debate")
        debate_section = html[debate_start:debate_start + 4000]
        self.assertIn("Initial Positions", debate_section)
        self.assertIn("Rebuttal", debate_section)
        self.assertIn("NVDA", debate_section)
        self.assertIn("Moats matter more than momentum", debate_section)
        self.assertIn("hypatia ignores the tape", debate_section)
        self.assertNotRegex(debate_section, r"ROUND\s+[12]", re.I)
        self.assertIn("border-radius:50%", debate_section.replace(" ", ""))
        self.assertNotIn("overflow:hidden", debate_section)


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

    def test_pie_similar_positive_returns_spread_by_rank(self):
        similar = [18.0, 18.5, 19.0, 19.5, 20.0]
        colors = reporting.pie_chart_colors(similar)
        self.assertEqual(len(colors), 5)
        self.assertEqual(len(set(colors)), 5)

    def test_pie_uses_magnitude_colors_by_return(self):
        ledger = [
            ("A", {"Total": 5000, "Personal_Return_Pct": 8.0}),
            ("B", {"Total": 6000, "Personal_Return_Pct": -3.0}),
            ("C", {"Total": 7000, "Personal_Return_Pct": 35.0}),
        ]
        with patch.object(reporting, "get_quickchart_short_url", return_value="https://example.com/pie.png") as mock_url:
            reporting.build_portfolio_pie_chart(ledger)
        colors = mock_url.call_args[0][0]["data"]["datasets"][0]["backgroundColor"]
        self.assertEqual(len(colors), 3)
        self.assertEqual(colors, reporting.pie_chart_colors([8.0, -3.0, 35.0]))
        self.assertNotEqual(colors[0], colors[2])

    def test_bar_chart_uses_magnitude_colors(self):
        ledger = [
            ("AAPL", {"Personal_Return_Pct": 10.0}),
            ("MSFT", {"Personal_Return_Pct": -5.0}),
            ("NVDA", {"Personal_Return_Pct": 35.0}),
        ]
        with patch.object(reporting, "get_quickchart_short_url", return_value="https://example.com/bar.png") as mock_url:
            reporting.build_returns_bar_chart(ledger)
        colors = mock_url.call_args[0][0]["data"]["datasets"][0]["backgroundColor"]
        self.assertEqual(colors, reporting.chart_magnitude_colors([10.0, -5.0, 35.0]))
        self.assertNotEqual(colors[0], colors[2])

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

    def test_pie_outlabels_use_heavy_type(self):
        ledger = [
            ("A", {"Total": 5000, "Personal_Return_Pct": 8.0}),
            ("B", {"Total": 6000, "Personal_Return_Pct": 22.0}),
        ]
        with patch.object(reporting, "get_quickchart_short_url", return_value="https://example.com/pie.png") as mock_url:
            reporting.build_portfolio_pie_chart(ledger)
        outlabels = mock_url.call_args[0][0]["options"]["plugins"]["outlabels"]
        self.assertEqual(outlabels["color"], reporting.PIE_OUTLABEL_COLOR)
        expected_bg = reporting.pie_chart_colors([8.0, 22.0])
        self.assertEqual(outlabels["backgroundColor"], expected_bg)
        self.assertEqual(outlabels["stretch"], reporting.PIE_OUTLABEL_STRETCH)
        self.assertEqual(outlabels["font"]["weight"], str(reporting.CHART_OUTLABEL_WEIGHT))
        self.assertEqual(outlabels["font"]["minSize"], reporting.PIE_OUTLABEL_MIN_SIZE)
        self.assertEqual(outlabels["font"]["maxSize"], reporting.PIE_OUTLABEL_MAX_SIZE)
        self.assertEqual(mock_url.call_args[1]["width"], reporting.PIE_CHART_WIDTH)
        self.assertEqual(mock_url.call_args[1]["height"], reporting.PIE_CHART_HEIGHT)
        self.assertEqual(mock_url.call_args[1]["background_color"], reporting.CHART_CANVAS_DARK)

    def test_bar_chart_dark_canvas_and_sign_aware_datalabels(self):
        ledger = [
            ("AAPL", {"Personal_Return_Pct": 10.0}),
            ("MSFT", {"Personal_Return_Pct": -5.0}),
        ]
        with patch.object(reporting, "get_quickchart_short_url", return_value="https://example.com/bar.png") as mock_url:
            reporting.build_returns_bar_chart(ledger)
        opts = mock_url.call_args[0][0]["options"]
        datalabels = opts["plugins"]["datalabels"]
        self.assertIs(opts["plugins"]["legend"], False)
        self.assertEqual(opts["scales"]["y"]["title"]["text"], "Unrealized Gain (%)")
        self.assertEqual(opts["scales"]["y"]["grace"], reporting.BAR_Y_SCALE_GRACE)
        self.assertEqual(opts["plugins"]["tickFormat"], reporting.BAR_TICK_FORMAT)
        self.assertEqual(datalabels["anchor"], reporting.BAR_DATALABEL_ANCHOR)
        self.assertEqual(datalabels["align"], reporting.BAR_DATALABEL_ALIGN)
        self.assertEqual(datalabels["offset"], reporting.BAR_DATALABEL_OFFSET)
        self.assertNotIn("backgroundColor", datalabels)
        dataset = mock_url.call_args[0][0]["data"]["datasets"][0]
        self.assertEqual(dataset["minBarLength"], reporting.BAR_MIN_BAR_LENGTH)
        self.assertEqual(datalabels["color"], reporting.BAR_DATALABEL_COLOR)
        self.assertFalse(datalabels["clip"])
        self.assertEqual(datalabels["font"]["weight"], reporting.CHART_DATALABEL_WEIGHT)
        self.assertEqual(datalabels["font"]["size"], reporting.BAR_DATALABEL_SIZE)
        self.assertNotIn("formatter", datalabels)
        self.assertEqual(mock_url.call_args[0][0]["options"]["layout"]["padding"], reporting.BAR_CHART_LAYOUT_PADDING)
        self.assertEqual(mock_url.call_args[1]["width"], reporting.LINE_CHART_WIDTH)
        self.assertEqual(mock_url.call_args[1]["height"], reporting.LINE_CHART_HEIGHT)
        self.assertEqual(reporting.LINE_CHART_WIDTH, reporting.BAR_CHART_WIDTH)
        self.assertEqual(reporting.LINE_CHART_HEIGHT, reporting.BAR_CHART_HEIGHT)
        self.assertEqual(mock_url.call_args[1]["background_color"], reporting.CHART_CANVAS_DARK)

    def test_line_chart_legend_font_size_and_dark_canvas(self):
        history = {
            "20250101": {"portfolio_index": 100, "spy": 100, "qqq": 100},
            "20250201": {"portfolio_index": 105, "spy": 102, "qqq": 103},
        }
        with patch.object(reporting, "get_quickchart_short_url", return_value="https://example.com/line.png") as mock_url:
            reporting.build_benchmark_line_chart(history)
        opts = mock_url.call_args[0][0]["options"]
        datasets = mock_url.call_args[0][0]["data"]["datasets"]
        legend_font = opts["plugins"]["legend"]["labels"]["font"]
        self.assertNotIn("title", opts["plugins"])
        self.assertEqual(datasets[0]["borderColor"], reporting.CHART_LINE_PORTFOLIO)
        self.assertEqual(datasets[1]["borderColor"], reporting.CHART_LINE_BENCHMARK)
        self.assertEqual(legend_font["size"], reporting.CHART_LEGEND_FONT_SIZE)
        self.assertEqual(mock_url.call_args[1]["width"], reporting.LINE_CHART_WIDTH)
        self.assertEqual(mock_url.call_args[1]["height"], reporting.LINE_CHART_HEIGHT)
        self.assertEqual(legend_font["weight"], reporting.CHART_LEGEND_WEIGHT)
        self.assertEqual(mock_url.call_args[1]["background_color"], reporting.CHART_CANVAS_DARK)


class BriefingHtmlTests(unittest.TestCase):
    def test_action_plan_integrated_blocks_without_summary_table(self):
        html = reporting.generate_html_briefing(
            total_val=500_000,
            qqq_trend=2.0,
            portfolio_3m_trend=1.0,
            mandate="CAGR of 12.00 percent projected balance at age 65 is $1,000,000.00",
            chairman_data={
                "portfolio_positions": [
                    {
                        "symbol": "TSM",
                        "final_verdict": "Bearish (Liquidate)",
                        "synthesis": "Unanimous sell mandate.",
                        "narrative": {
                            "champion": PANELIST_ROLES["aurelius"],
                            "champion_quote": "Mathematically suboptimal.",
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
        action_pos = html.find("The Action Plan")
        after_action = html[action_pos:]
        self.assertNotRegex(
            after_action[:1500],
            r"<th[^>]*>Symbol</th>\s*<th[^>]*>Action</th>",
        )
        self.assertIn("Strategic Context:", after_action)
        self.assertIn("The Champion (", after_action)
        self.assertIn("The Dissent (None):", after_action)
        self.assertIn("BEARISH (LIQUIDATE) : TSM", after_action)
        self.assertIn(PANELIST_AVATAR_URLS["aurelius"], after_action)

    def test_action_plan_shows_champion_and_dissenter_avatars(self):
        html = reporting.generate_html_briefing(
            total_val=500_000,
            qqq_trend=2.0,
            portfolio_3m_trend=1.0,
            mandate="CAGR of 12.00 percent projected balance at age 65 is $1,000,000.00",
            chairman_data={
                "portfolio_positions": [
                    {
                        "symbol": "NVDA",
                        "final_verdict": "Accumulate Candidate",
                        "synthesis": "Strong AI momentum.",
                        "narrative": {
                            "champion": PANELIST_ROLES["tesla"],
                            "champion_quote": "Platform moat widening.",
                            "dissenter": PANELIST_ROLES["hypatia"],
                            "dissenter_quote": "Rich multiples.",
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
        action_pos = html.find("The Action Plan")
        section = html[action_pos:]
        self.assertIn(PANELIST_AVATAR_URLS["tesla"], section)
        self.assertIn(PANELIST_AVATAR_URLS["hypatia"], section)
        self.assertIn("width:40px;height:40px", section.replace(" ", ""))

    def test_sotu_quotes_shorten_peer_names_in_body_only(self):
        hypatia = PANELIST_ROLES["hypatia"]
        davinci = PANELIST_ROLES["davinci"]
        html = reporting.generate_html_briefing(
            total_val=100_000,
            qqq_trend=1.0,
            portfolio_3m_trend=1.0,
            mandate="Test mandate.",
            chairman_data={
                "portfolio_positions": [],
                "watchlist_positions": [],
                "alpha_pick": {"symbol": "NONE", "champion_quote": "N/A"},
                "upcoming_events": [],
            },
            cos_data={
                "state_of_the_union_quotes": [{
                    "board_member": f"{hypatia} (⭐ Bearish)",
                    "quote": f"{davinci} describes NVIDIA as a masterwork.",
                }],
                "boardroom_brawl": "x" * 200,
            },
            matrix_md="",
            unicorn_trades=[],
            sorted_ledger=[],
            chart_urls={},
        )
        sotu_pos = html.find("The State of the Union")
        section = html[sotu_pos:]
        self.assertIn(f"{hypatia} (", section)
        self.assertIn("Leonardo describes", section)
        self.assertNotIn("da Vinci", section)

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
                        "final_verdict": "Accumulate Candidate",
                        "synthesis": "Strong momentum.",
                        "narrative": {"champion": "hypatia", "champion_quote": "Accumulate Candidate.", "dissenter": "NONE", "dissenter_quote": "N/A"},
                    }
                ],
                "watchlist_positions": [],
                "alpha_pick": {"symbol": "NONE", "champion_quote": "As per the QA Amendment protocol, none."},
                "upcoming_events": [],
            },
            cos_data={
                "state_of_the_union_quotes": [
                    {"board_member": PANELIST_ROLES["hypatia"], "quote": "Markets remain rational long term."},
                ],
                "boardroom_brawl": (
                    "Hypatia challenged the growth camp on concentration risk across the portfolio mandate. "
                    "Leonardo countered that tape weakness is a buying opportunity for platform leaders.\n\n"
                    "Sun Tzu pressed for discipline while Nikola argued the AI cycle still has runway. "
                    "Marcus closed by quantifying the expected value of today's trim mandates."
                ),
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
                "pie_chart_url": "https://example.com/pie.png",
            },
        )
        perf_pos = html.find("Performance vs. Benchmark")
        pie_pos = html.find("Unrealized Gains")
        sotu_pos = html.find("The State of the Union")
        debate_pos = html.find("The Debate")
        actions_pos = html.find("Theoretical Scenario Adjustments")
        action_pos = html.find("The Action Plan")
        self.assertLess(perf_pos, pie_pos)
        self.assertLess(pie_pos, sotu_pos)
        self.assertLess(sotu_pos, debate_pos)
        self.assertLess(debate_pos, actions_pos)
        self.assertLess(actions_pos, action_pos)
        self.assertNotIn("Time-Weighted Returns", html)
        self.assertIn("NVDA", html)
        self.assertIn("Invest AI Daily Briefing", html)
        self.assertNotIn("Generated autonomously", html)
        self.assertNotIn("The Alpha Pick", html)
        self.assertIn("12.00%", html)
        self.assertNotIn("12.00 percent", html)

    def test_investor_briefing_omits_qa_ledger_by_default(self):
        html = reporting.generate_html_briefing(
            total_val=150_000,
            qqq_trend=5.0,
            portfolio_3m_trend=3.0,
            mandate="CAGR of 12.00 percent projected balance at age 65 is $1,000,000.00",
            chairman_data={"portfolio_positions": [], "watchlist_positions": [], "upcoming_events": []},
            cos_data={"state_of_the_union_quotes": []},
            matrix_md="",
            unicorn_trades=[],
            sorted_ledger=[],
        )
        stripped = reporting.inject_qa_summary_into_briefing(html, "")
        self.assertNotIn("Internal QA Ledger", stripped)
        self.assertNotIn(reporting.QA_SUMMARY_ANCHOR, stripped)

    def test_inject_qa_review_link_adds_footer_cta(self):
        html = reporting.generate_html_briefing(
            total_val=150_000,
            qqq_trend=5.0,
            portfolio_3m_trend=3.0,
            mandate="Test mandate",
            chairman_data={"portfolio_positions": [], "watchlist_positions": [], "upcoming_events": []},
            cos_data={"state_of_the_union_quotes": []},
            matrix_md="",
            unicorn_trades=[],
            sorted_ledger=[],
        )
        url = "https://example.azurewebsites.net/api/qa-review?run_id=20260529_120000&token=abc"
        out = reporting.inject_qa_review_link_into_briefing(html, url)
        self.assertIn("Review QA &amp; provide feedback", out)
        self.assertIn("api/qa-review?run_id=20260529_120000&amp;token=abc", out)
        self.assertNotIn(reporting.QA_REVIEW_LINK_ANCHOR, out)

    def test_inject_qa_review_link_omits_when_no_url(self):
        html = reporting.generate_html_briefing(
            total_val=150_000,
            qqq_trend=5.0,
            portfolio_3m_trend=3.0,
            mandate="Test mandate",
            chairman_data={"portfolio_positions": [], "watchlist_positions": [], "upcoming_events": []},
            cos_data={"state_of_the_union_quotes": []},
            matrix_md="",
            unicorn_trades=[],
            sorted_ledger=[],
        )
        out = reporting.inject_qa_review_link_into_briefing(html, None)
        self.assertNotIn("Review QA", out)
        self.assertNotIn(reporting.QA_REVIEW_LINK_ANCHOR, out)


class DeliverPerformanceTests(unittest.TestCase):
    def test_build_briefing_charts_returns_all_urls_in_parallel(self):
        call_count = {"n": 0}

        def fake_short_url(*_args, **_kwargs):
            call_count["n"] += 1
            return f"https://example.com/chart{call_count['n']}.png"

        ledger = [("AAPL", {"Total": 50_000, "Personal_Return_Pct": 5.0})]
        holdings = {"eTrade Taxable": {"AAPL": {"value": 50_000}}}
        history = {
            "20250101": {"portfolio_index": 100.0, "spy": 500, "qqq": 400},
            "20250201": {"portfolio_index": 101.0, "spy": 505, "qqq": 402},
        }
        with patch.object(reporting, "get_quickchart_short_url", side_effect=fake_short_url):
            urls = reporting.build_briefing_charts(ledger, holdings, {"returns": {}}, history)
        self.assertEqual(
            set(urls.keys()),
            {"pie_chart_url", "account_pie_url", "bar_chart_url", "line_chart_url"},
        )
        self.assertEqual(call_count["n"], 4)

    def test_audit_chart_health_probes_all_charts(self):
        probed = []

        def fake_fetch(url):
            probed.append(url)
            if url:
                return True, "OK", b"\x89PNG", "image/png"
            return False, "empty", None, None

        with patch.object(reporting, "_fetch_image_url", side_effect=fake_fetch):
            health = reporting.audit_chart_health({
                "pie_chart_url": "https://example.com/pie",
                "bar_chart_url": "https://example.com/bar",
                "line_chart_url": "https://example.com/line",
                "account_pie_url": "https://example.com/acct",
            })
        self.assertEqual(len(health), 4)
        self.assertEqual(len(probed), 4)
        self.assertTrue(all(row.get("bytes") for row in health if row.get("url")))

    def test_chart_health_image_cache_maps_urls(self):
        health = [
            {
                "name": "Line",
                "ok": True,
                "url": "https://example.com/line",
                "bytes": b"line-bytes",
                "mime_type": "image/png",
            }
        ]
        cache = reporting.chart_health_image_cache(health)
        self.assertIn("https://example.com/line", cache)
        self.assertEqual(cache["https://example.com/line"]["bytes"], b"line-bytes")

    def test_inject_qa_summary_replaces_anchor(self):
        base = "<html><body><footer></footer><!-- QA_SUMMARY_ANCHOR --></body></html>"
        summary = "<strong>Post Mortem QA</strong> &#9989;"
        out = reporting.inject_qa_summary_into_briefing(base, summary)
        self.assertNotIn(reporting.QA_SUMMARY_ANCHOR, out)
        self.assertIn("Internal QA Ledger", out)
        self.assertIn("Post Mortem QA", out)

    def test_inject_qa_summary_matches_direct_render(self):
        kwargs = dict(
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
        summary = "<strong>Graphics Designer</strong> &#10060;"
        direct = reporting.generate_html_briefing(**kwargs, qa_summary_text=summary)
        injected = reporting.inject_qa_summary_into_briefing(
            reporting.generate_html_briefing(**kwargs, qa_summary_text=""),
            summary,
        )
        self.assertIn("Internal QA Ledger", direct)
        self.assertIn("Graphics Designer", direct)
        self.assertIn("Internal QA Ledger", injected)
        self.assertIn("Graphics Designer", injected)
        self.assertNotIn(reporting.QA_SUMMARY_ANCHOR, injected)


class TodaysActionsTests(unittest.TestCase):
    def _minimal_chairman(self, **overrides):
        base = {
            "portfolio_positions": [],
            "watchlist_positions": [],
            "alpha_pick": {"symbol": "NONE", "champion_quote": "N/A"},
            "upcoming_events": [],
        }
        base.update(overrides)
        return base

    def test_build_summary_sorts_strong_actions_first_and_dedupes_unicorn(self):
        grouped = {cat: [] for cat in ["HIGH CONVICTION (OVERWEIGHT)", "ACCUMULATE CANDIDATE", "HOLD", "REDUCE EXPOSURE", "BEARISH (LIQUIDATE)", "EXTREME BEARISH (LIQUIDATE)"]}
        grouped["ACCUMULATE CANDIDATE"].append({
            "symbol": "VRT",
            "final_verdict": "ACCUMULATE CANDIDATE",
            "synthesis": "Committee executes ACCUMULATE CANDIDATE on infrastructure play.",
        })
        grouped["BEARISH (LIQUIDATE)"].append({
            "symbol": "GOOGL",
            "final_verdict": "BEARISH (LIQUIDATE)",
            "synthesis": "Reallocate capital to higher-conviction names.",
        })
        grouped["REDUCE EXPOSURE"].append({
            "symbol": "ASML",
            "final_verdict": "REDUCE EXPOSURE",
            "synthesis": "Duplicate row should be skipped.",
        })
        unicorn = [{
            "symbol": "ASML",
            "verdict": "REDUCE EXPOSURE",
            "synthesis": "Unanimous reduce mandate after Round 2.",
        }]
        rows, overflow = reporting.build_todays_actions_summary(grouped, unicorn)
        symbols = [r["symbol"] for r in rows]
        self.assertEqual(symbols, ["GOOGL", "VRT", "ASML"])
        self.assertEqual(len([r for r in rows if r["symbol"] == "ASML"]), 1)
        self.assertTrue(rows[2]["unanimous"])
        self.assertEqual(overflow, 0)

    def test_build_summary_caps_overflow(self):
        grouped = {cat: [] for cat in ["HIGH CONVICTION (OVERWEIGHT)", "ACCUMULATE CANDIDATE", "HOLD", "REDUCE EXPOSURE", "BEARISH (LIQUIDATE)", "EXTREME BEARISH (LIQUIDATE)"]}
        grouped["ACCUMULATE CANDIDATE"] = [
            {"symbol": f"SYM{i}", "synthesis": f"Reason {i}."}
            for i in range(15)
        ]
        rows, overflow = reporting.build_todays_actions_summary(grouped, max_items=5)
        self.assertEqual(len(rows), 5)
        self.assertEqual(overflow, 10)

    def test_todays_actions_section_after_debate_before_action_plan(self):
        html = reporting.generate_html_briefing(
            total_val=150_000,
            qqq_trend=5.0,
            portfolio_3m_trend=3.0,
            mandate="CAGR of 12.00 percent projected balance at age 65 is $1,000,000.00",
            chairman_data=self._minimal_chairman(
                portfolio_positions=[
                    {
                        "symbol": "MSFT",
                        "final_verdict": "High Conviction (Overweight)",
                        "synthesis": "Round 2 split buy_side=4/5 on MSFT; committee executes HIGH CONVICTION (OVERWEIGHT).",
                        "narrative": {
                            "champion": PANELIST_ROLES["davinci"],
                            "champion_quote": "Growth at a reasonable price opportunity.",
                            "dissenter": "None",
                            "dissenter_quote": "N/A",
                        },
                    }
                ],
                capital_allocation_narrative="Mandatory TLT hedge included in target allocations.",
            ),
            cos_data={
                "state_of_the_union_quotes": [
                    {"board_member": "Hypatia (Value Anchor)", "quote": "Margin of safety first."}
                ],
                "boardroom_brawl": "",
            },
            matrix_md="",
            unicorn_trades=[],
            sorted_ledger=[],
            chart_urls={},
        )
        self.assertIn("Theoretical Scenario Adjustments", html)
        self.assertIn("HIGH CONVICTION (OVERWEIGHT)", html)
        self.assertIn("MSFT", html)
        self.assertIn("Risk hedge:", html)
        actions_idx = html.index("Theoretical Scenario Adjustments")
        action_plan_idx = html.index("The Action Plan")
        self.assertLess(actions_idx, action_plan_idx)

    def test_build_summary_includes_champion_and_dissenter(self):
        grouped = {cat: [] for cat in ["HIGH CONVICTION (OVERWEIGHT)", "ACCUMULATE CANDIDATE", "HOLD", "REDUCE EXPOSURE", "BEARISH (LIQUIDATE)", "EXTREME BEARISH (LIQUIDATE)"]}
        grouped["ACCUMULATE CANDIDATE"].append({
            "symbol": "MSFT",
            "synthesis": "Execute buy mandate.",
            "narrative": {
                "champion": PANELIST_ROLES["davinci"],
                "champion_quote": "Growth opportunity.",
                "dissenter": PANELIST_ROLES["hypatia"],
                "dissenter_quote": "Valuation stretched.",
            },
        })
        rows, _ = reporting.build_todays_actions_summary(grouped)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["champion"], "Leonardo")
        self.assertEqual(rows[0]["dissenter"], "Hypatia")

    def test_todays_actions_hidden_when_only_hold(self):
        html = reporting.generate_html_briefing(
            total_val=100_000,
            qqq_trend=1.0,
            portfolio_3m_trend=1.0,
            mandate="Test mandate.",
            chairman_data=self._minimal_chairman(
                portfolio_positions=[{"symbol": "NVDA", "final_verdict": "Hold", "synthesis": "Hold."}],
            ),
            cos_data={"state_of_the_union_quotes": [], "boardroom_brawl": ""},
            matrix_md="",
            unicorn_trades=[],
            sorted_ledger=[],
            chart_urls={},
        )
        self.assertNotIn("Theoretical Scenario Adjustments", html)


if __name__ == "__main__":
    unittest.main()
