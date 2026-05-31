"""Tests for deterministic vote_engine (Phase A–C mandate voting)."""
import unittest

from src.core.board_roster import PANELIST_KEYS
from src.core.compliance_audit import audit_chairman_compliance, audit_chairman_vote_alignment
from src.core.vote_engine import (
    apply_max_three_buys,
    build_chairman_allocation,
    build_chairman_skeleton,
    build_matrix_from_raw_verdicts,
    build_vote_summaries,
    can_bypass_chairman,
    can_determine_allocation,
    count_board_portfolio_sell_mandates,
    detect_unicorn_trades,
    ensure_funding_sell,
    format_vote_digest,
    is_funding_sell_override,
    mandate_verdict,
)


def _raw_portfolio_symbol(symbol: str, verdicts: list[tuple[str, int]]) -> dict:
    agents = PANELIST_KEYS
    raw = {a: {"portfolio_verdicts": [], "watchlist_verdicts": []} for a in agents}
    for agent, (verdict, conviction) in zip(agents, verdicts):
        raw[agent]["portfolio_verdicts"] = [
            {"symbol": symbol, "verdict": verdict, "conviction_score": conviction},
        ]
    return raw


def _raw_watchlist_symbol(symbol: str, verdicts: list[tuple[str, int]]) -> dict:
    agents = PANELIST_KEYS
    raw = {a: {"portfolio_verdicts": [], "watchlist_verdicts": []} for a in agents}
    for agent, (verdict, conviction) in zip(agents, verdicts):
        raw[agent]["watchlist_verdicts"] = [
            {"symbol": symbol, "verdict": verdict, "conviction_score": conviction},
        ]
    return raw


def _merge_raw(*parts: dict) -> dict:
    merged: dict = {}
    for part in parts:
        for agent, data in part.items():
            merged.setdefault(agent, {"portfolio_verdicts": [], "watchlist_verdicts": []})
            merged[agent]["portfolio_verdicts"].extend(data.get("portfolio_verdicts") or [])
            merged[agent]["watchlist_verdicts"].extend(data.get("watchlist_verdicts") or [])
    return merged


def _majority_buy_raw(symbol: str, buy_conviction: int = 7) -> dict:
    return _raw_watchlist_symbol(
        symbol,
        [
            ("Accumulate Candidate", buy_conviction),
            ("Accumulate Candidate", buy_conviction),
            ("Accumulate Candidate", buy_conviction),
            ("Pass", 3),
            ("Pass", 3),
        ],
    )


class TestVoteEnginePhaseC(unittest.TestCase):
    def test_three_buy_two_sell_mandate_buy(self):
        raw = _raw_portfolio_symbol(
            "NVDA",
            [
                ("High Conviction (Overweight)", 9),
                ("High Conviction (Overweight)", 8),
                ("High Conviction (Overweight)", 7),
                ("Bearish (Liquidate)", 4),
                ("Extreme Bearish (Liquidate)", 3),
            ],
        )
        summaries = build_vote_summaries(raw, ["NVDA"], portfolio_symbols={"NVDA"})
        self.assertEqual(mandate_verdict(summaries["NVDA"]), "High Conviction (Overweight)")

    def test_three_regular_buys_mandate_buy(self):
        raw = _raw_portfolio_symbol(
            "NVDA",
            [
                ("Accumulate Candidate", 9),
                ("Accumulate Candidate", 8),
                ("Accumulate Candidate", 7),
                ("Bearish (Liquidate)", 4),
                ("Extreme Bearish (Liquidate)", 3),
            ],
        )
        summaries = build_vote_summaries(raw, ["NVDA"], portfolio_symbols={"NVDA"})
        self.assertEqual(mandate_verdict(summaries["NVDA"]), "Accumulate Candidate")

    def test_three_sell_two_buy_mandate_strong_sell(self):
        raw = _raw_portfolio_symbol(
            "ASML",
            [
                ("Extreme Bearish (Liquidate)", 8),
                ("Extreme Bearish (Liquidate)", 7),
                ("Extreme Bearish (Liquidate)", 6),
                ("Accumulate Candidate", 5),
                ("Accumulate Candidate", 4),
            ],
        )
        summaries = build_vote_summaries(raw, ["ASML"], portfolio_symbols={"ASML"})
        self.assertEqual(mandate_verdict(summaries["ASML"]), "Extreme Bearish (Liquidate)")

    def test_two_two_split_hold(self):
        raw = _raw_portfolio_symbol(
            "AVGO",
            [
                ("Accumulate Candidate", 7),
                ("Accumulate Candidate", 6),
                ("Bearish (Liquidate)", 5),
                ("Extreme Bearish (Liquidate)", 4),
                ("Hold", 3),
            ],
        )
        summaries = build_vote_summaries(raw, ["AVGO"], portfolio_symbols={"AVGO"})
        self.assertEqual(mandate_verdict(summaries["AVGO"]), "Hold")
        self.assertTrue(can_determine_allocation(summaries))

    def test_watchlist_pass_without_majority_buy(self):
        raw = _raw_watchlist_symbol(
            "ARM",
            [
                ("Accumulate Candidate", 5),
                ("Pass", 4),
                ("Pass", 4),
                ("Pass", 4),
                ("Pass", 3),
            ],
        )
        summaries = build_vote_summaries(raw, ["ARM"])
        self.assertEqual(mandate_verdict(summaries["ARM"]), "Pass")

    def test_watchlist_strong_buy_unanimous(self):
        raw = _raw_watchlist_symbol(
            "META",
            [("High Conviction (Overweight)", 9)] * 5,
        )
        summaries = build_vote_summaries(raw, ["META"])
        self.assertEqual(mandate_verdict(summaries["META"]), "High Conviction (Overweight)")

    def test_five_majority_buys_max_three(self):
        symbols = ["META", "PLTR", "NVDA", "AMZN", "GOOG"]
        raw_parts = [_majority_buy_raw(s, buy_conviction=10 - i) for i, s in enumerate(symbols)]
        raw = _merge_raw(*raw_parts)
        allocation = build_chairman_allocation(
            raw, symbols, portfolio_symbols=set(), watchlist_symbols=set(symbols),
        )
        buys = {
            p["symbol"]
            for p in allocation["watchlist_positions"]
            if p["final_verdict"] in ("Accumulate Candidate", "High Conviction (Overweight)")
        }
        self.assertEqual(len(buys), 3)

    def test_compliance_surplus_buy_demotion(self):
        raw = _merge_raw(
            _majority_buy_raw("META", 9),
            _majority_buy_raw("PLTR", 8),
            _majority_buy_raw("NVDA", 7),
            _majority_buy_raw("MNDY", 6),
        )
        allocation = build_chairman_allocation(
            raw, ["META", "PLTR", "NVDA", "MNDY"],
            portfolio_symbols=set(), watchlist_symbols={"META", "PLTR", "NVDA", "MNDY"},
        )
        violations = audit_chairman_compliance(
            allocation, raw, all_symbols=["META", "PLTR", "NVDA", "MNDY"], portfolio_symbols=set(),
        )
        self.assertEqual(violations, [], violations)

    def test_vote_digest_phase_c_labels(self):
        raw = _majority_buy_raw("META")
        summaries = build_vote_summaries(raw, ["META"])
        digest = format_vote_digest(summaries)
        self.assertIn("buy_side=", digest)
        self.assertIn("Phase C mandate", digest)

    def test_chairman_skeleton_alias(self):
        raw = _majority_buy_raw("META")
        a = build_chairman_allocation(
            raw, ["META"], portfolio_symbols=set(), watchlist_symbols={"META"},
        )
        b = build_chairman_skeleton(
            raw, ["META"], portfolio_symbols=set(), watchlist_symbols={"META"},
        )
        self.assertEqual(a["watchlist_positions"][0]["final_verdict"], b["watchlist_positions"][0]["final_verdict"])

    def test_compliance_majority_alignment_fail(self):
        raw = _majority_buy_raw("META")
        chairman = {
            "alpha_pick": {"symbol": "META", "champion_quote": "test"},
            "portfolio_positions": [],
            "watchlist_positions": [{
                "symbol": "META",
                "final_verdict": "Pass",
                "synthesis": "Wrong.",
            }],
        }
        violations = audit_chairman_vote_alignment(
            chairman, raw, all_symbols=["META"], portfolio_symbols=set(),
        )
        self.assertTrue(any("MAJORITY VOTE ALIGNMENT" in v for v in violations))

    def test_unanimous_actionable_buy_bypass(self):
        raw = _raw_watchlist_symbol("META", [("High Conviction (Overweight)", 9)] * 5)
        summaries = build_vote_summaries(raw, ["META"])
        self.assertTrue(can_bypass_chairman(summaries))
        unicorns = detect_unicorn_trades(summaries)
        self.assertEqual(len(unicorns), 1)

    def test_unanimous_hold_not_unicorn(self):
        raw = _raw_watchlist_symbol("GOOGL", [("Hold", 5)] * 5)
        summaries = build_vote_summaries(raw, ["GOOGL"])
        self.assertFalse(any(s.is_actionable_unanimous() for s in summaries.values()))
        self.assertEqual(detect_unicorn_trades(summaries), [])

    def test_build_matrix_from_json(self):
        raw = _majority_buy_raw("META")
        matrix = build_matrix_from_raw_verdicts(raw, ["META"])
        self.assertEqual(matrix["META"]["hypatia"], "Accumulate Candidate")

    def test_apply_max_three_buys_standalone(self):
        chairman = {
            "capital_flow_audit": {"liquidated_tickers": [], "target_tickers": ["TLT"]},
            "portfolio_positions": [],
            "watchlist_positions": [
                {"symbol": "A", "final_verdict": "High Conviction (Overweight)", "aggregate_conviction_score": 10, "synthesis": ""},
                {"symbol": "B", "final_verdict": "Accumulate Candidate", "aggregate_conviction_score": 8, "synthesis": ""},
                {"symbol": "C", "final_verdict": "Accumulate Candidate", "aggregate_conviction_score": 6, "synthesis": ""},
                {"symbol": "D", "final_verdict": "Accumulate Candidate", "aggregate_conviction_score": 4, "synthesis": ""},
            ],
        }
        apply_max_three_buys(chairman)
        verdicts = {p["symbol"]: p["final_verdict"] for p in chairman["watchlist_positions"]}
        self.assertEqual(verdicts["D"], "Pass")


def _majority_sell_portfolio(symbol: str) -> dict:
    return _raw_portfolio_symbol(
        symbol,
        [
            ("Bearish (Liquidate)", 8),
            ("Bearish (Liquidate)", 7),
            ("Reduce Exposure", 6),
            ("Hold", 5),
            ("Hold", 4),
        ],
    )


class TestFundingSell(unittest.TestCase):
    def test_buy_triggers_lowest_conviction_sell(self):
        raw = _merge_raw(
            _majority_buy_raw("META"),
            _raw_portfolio_symbol(
                "AAPL",
                [("Hold", 3)] * 5,
            ),
            _raw_portfolio_symbol(
                "MSFT",
                [("Hold", 2)] * 5,
            ),
        )
        allocation = build_chairman_allocation(
            raw,
            ["META", "AAPL", "MSFT"],
            portfolio_symbols={"AAPL", "MSFT"},
            watchlist_symbols={"META"},
        )
        by_sym = {p["symbol"]: p for p in allocation["portfolio_positions"]}
        self.assertEqual(by_sym["MSFT"]["final_verdict"], "Bearish (Liquidate)")
        self.assertTrue(is_funding_sell_override(by_sym["MSFT"]))
        self.assertEqual(by_sym["AAPL"]["final_verdict"], "Hold")
        self.assertIn("MSFT", allocation["capital_flow_audit"]["liquidated_tickers"])

    def test_skipped_when_board_votes_more_than_one_sell(self):
        raw = _merge_raw(
            _majority_buy_raw("META"),
            _majority_sell_portfolio("AAPL"),
            _majority_sell_portfolio("MSFT"),
        )
        allocation = build_chairman_allocation(
            raw,
            ["META", "AAPL", "MSFT"],
            portfolio_symbols={"AAPL", "MSFT"},
            watchlist_symbols={"META"},
        )
        by_sym = {p["symbol"]: p for p in allocation["portfolio_positions"]}
        self.assertEqual(by_sym["AAPL"]["final_verdict"], "Bearish (Liquidate)")
        self.assertEqual(by_sym["MSFT"]["final_verdict"], "Bearish (Liquidate)")
        self.assertFalse(is_funding_sell_override(by_sym["AAPL"]))
        self.assertFalse(is_funding_sell_override(by_sym["MSFT"]))

    def test_single_board_sell_sufficient_no_funding_sell(self):
        raw = _merge_raw(
            _majority_buy_raw("META"),
            _majority_sell_portfolio("AAPL"),
            _raw_portfolio_symbol("MSFT", [("Hold", 1)] * 5),
        )
        allocation = build_chairman_allocation(
            raw,
            ["META", "AAPL", "MSFT"],
            portfolio_symbols={"AAPL", "MSFT"},
            watchlist_symbols={"META"},
        )
        by_sym = {p["symbol"]: p for p in allocation["portfolio_positions"]}
        self.assertEqual(by_sym["AAPL"]["final_verdict"], "Bearish (Liquidate)")
        self.assertEqual(by_sym["MSFT"]["final_verdict"], "Hold")
        self.assertFalse(is_funding_sell_override(by_sym["MSFT"]))

    def test_compliance_passes_funding_sell_on_hold_mandate(self):
        raw = _merge_raw(
            _majority_buy_raw("META"),
            _raw_portfolio_symbol("MSFT", [("Hold", 2)] * 5),
        )
        allocation = build_chairman_allocation(
            raw,
            ["META", "MSFT"],
            portfolio_symbols={"MSFT"},
            watchlist_symbols={"META"},
        )
        violations = audit_chairman_compliance(
            allocation,
            raw,
            all_symbols=["META", "MSFT"],
            portfolio_symbols={"MSFT"},
        )
        self.assertEqual(violations, [], violations)

    def test_count_board_portfolio_sell_mandates(self):
        raw = _merge_raw(_majority_sell_portfolio("A"), _majority_sell_portfolio("B"))
        summaries = build_vote_summaries(raw, ["A", "B"], portfolio_symbols={"A", "B"})
        self.assertEqual(count_board_portfolio_sell_mandates(summaries, {"A", "B"}), 2)

    def test_no_sell_when_all_portfolio_positions_are_buy(self):
        raw = _merge_raw(
            _majority_buy_raw("META"),
            _raw_portfolio_symbol(
                "NVDA",
                [("Accumulate Candidate", 9), ("Accumulate Candidate", 8), ("Accumulate Candidate", 7), ("Hold", 4), ("Hold", 3)],
            ),
            _raw_portfolio_symbol(
                "AAPL",
                [("Accumulate Candidate", 8), ("Accumulate Candidate", 7), ("Accumulate Candidate", 6), ("Hold", 4), ("Hold", 3)],
            ),
        )
        allocation = build_chairman_allocation(
            raw,
            ["META", "NVDA", "AAPL"],
            portfolio_symbols={"NVDA", "AAPL"},
            watchlist_symbols={"META"},
        )
        by_sym = {p["symbol"]: p for p in allocation["portfolio_positions"]}
        self.assertIn(by_sym["NVDA"]["final_verdict"], ("Accumulate Candidate", "High Conviction (Overweight)"))
        self.assertIn(by_sym["AAPL"]["final_verdict"], ("Accumulate Candidate", "High Conviction (Overweight)"))
        funding_liquidations = [
            sym for sym in allocation["capital_flow_audit"]["liquidated_tickers"]
            if sym in {"NVDA", "AAPL"}
        ]
        self.assertEqual(funding_liquidations, [])
        self.assertFalse(any(is_funding_sell_override(p) for p in allocation["portfolio_positions"]))

    def test_existing_trim_satisfies_sell_requirement(self):
        """Reduce Exposure/Bearish (Liquidate) on portfolio counts as sell-side — no funding-sell override."""
        chairman = {
            "capital_flow_audit": {"liquidated_tickers": [], "target_tickers": ["TLT", "META"]},
            "portfolio_positions": [
                {"symbol": "MSFT", "final_verdict": "Reduce Exposure", "aggregate_conviction_score": 6, "synthesis": ""},
                {"symbol": "AAPL", "final_verdict": "Hold", "aggregate_conviction_score": 20, "synthesis": ""},
            ],
            "watchlist_positions": [
                {"symbol": "META", "final_verdict": "Accumulate Candidate", "aggregate_conviction_score": 21, "synthesis": ""},
            ],
        }
        result = ensure_funding_sell(chairman)
        by_sym = {p["symbol"]: p for p in result["portfolio_positions"]}
        self.assertEqual(by_sym["MSFT"]["final_verdict"], "Reduce Exposure")
        self.assertFalse(is_funding_sell_override(by_sym["MSFT"]))
        self.assertEqual(by_sym["AAPL"]["final_verdict"], "Hold")


if __name__ == "__main__":
    unittest.main()
