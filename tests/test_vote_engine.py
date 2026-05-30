"""Tests for deterministic vote_engine (Phase A–C mandate voting)."""
import unittest

from src.core.compliance_audit import audit_chairman_compliance, audit_chairman_vote_alignment
from src.core.vote_engine import (
    apply_max_three_buys,
    build_chairman_allocation,
    build_chairman_skeleton,
    build_matrix_from_raw_verdicts,
    build_vote_summaries,
    can_bypass_chairman,
    can_determine_allocation,
    detect_unicorn_trades,
    format_vote_digest,
    mandate_verdict,
)


def _raw_portfolio_symbol(symbol: str, verdicts: list[tuple[str, int]]) -> dict:
    agents = ("buffett", "lynch", "livermore", "huang", "simons")
    raw = {a: {"portfolio_verdicts": [], "watchlist_verdicts": []} for a in agents}
    for agent, (verdict, conviction) in zip(agents, verdicts):
        raw[agent]["portfolio_verdicts"] = [
            {"symbol": symbol, "verdict": verdict, "conviction_score": conviction},
        ]
    return raw


def _raw_watchlist_symbol(symbol: str, verdicts: list[tuple[str, int]]) -> dict:
    agents = ("buffett", "lynch", "livermore", "huang", "simons")
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
            ("Buy", buy_conviction),
            ("Buy", buy_conviction),
            ("Buy", buy_conviction),
            ("Pass", 3),
            ("Pass", 3),
        ],
    )


class TestVoteEnginePhaseC(unittest.TestCase):
    def test_three_buy_two_sell_mandate_buy(self):
        raw = _raw_portfolio_symbol(
            "NVDA",
            [
                ("Strong Buy", 9),
                ("Strong Buy", 8),
                ("Strong Buy", 7),
                ("Sell", 4),
                ("Strong Sell", 3),
            ],
        )
        summaries = build_vote_summaries(raw, ["NVDA"], portfolio_symbols={"NVDA"})
        self.assertEqual(mandate_verdict(summaries["NVDA"]), "Strong Buy")

    def test_three_regular_buys_mandate_buy(self):
        raw = _raw_portfolio_symbol(
            "NVDA",
            [
                ("Buy", 9),
                ("Buy", 8),
                ("Buy", 7),
                ("Sell", 4),
                ("Strong Sell", 3),
            ],
        )
        summaries = build_vote_summaries(raw, ["NVDA"], portfolio_symbols={"NVDA"})
        self.assertEqual(mandate_verdict(summaries["NVDA"]), "Buy")

    def test_three_sell_two_buy_mandate_strong_sell(self):
        raw = _raw_portfolio_symbol(
            "ASML",
            [
                ("Strong Sell", 8),
                ("Strong Sell", 7),
                ("Strong Sell", 6),
                ("Buy", 5),
                ("Buy", 4),
            ],
        )
        summaries = build_vote_summaries(raw, ["ASML"], portfolio_symbols={"ASML"})
        self.assertEqual(mandate_verdict(summaries["ASML"]), "Strong Sell")

    def test_two_two_split_hold(self):
        raw = _raw_portfolio_symbol(
            "AVGO",
            [
                ("Buy", 7),
                ("Buy", 6),
                ("Sell", 5),
                ("Strong Sell", 4),
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
                ("Buy", 5),
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
            [("Strong Buy", 9)] * 5,
        )
        summaries = build_vote_summaries(raw, ["META"])
        self.assertEqual(mandate_verdict(summaries["META"]), "Strong Buy")

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
            if p["final_verdict"] in ("Buy", "Strong Buy")
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
        raw = _raw_watchlist_symbol("META", [("Strong Buy", 9)] * 5)
        summaries = build_vote_summaries(raw, ["META"])
        self.assertTrue(can_bypass_chairman(summaries))
        unicorns = detect_unicorn_trades(summaries)
        self.assertEqual(len(unicorns), 1)

    def test_build_matrix_from_json(self):
        raw = _majority_buy_raw("META")
        matrix = build_matrix_from_raw_verdicts(raw, ["META"])
        self.assertEqual(matrix["META"]["buffett"], "Buy")

    def test_apply_max_three_buys_standalone(self):
        chairman = {
            "capital_flow_audit": {"liquidated_tickers": [], "target_tickers": ["TLT"]},
            "portfolio_positions": [],
            "watchlist_positions": [
                {"symbol": "A", "final_verdict": "Strong Buy", "aggregate_conviction_score": 10, "synthesis": ""},
                {"symbol": "B", "final_verdict": "Buy", "aggregate_conviction_score": 8, "synthesis": ""},
                {"symbol": "C", "final_verdict": "Buy", "aggregate_conviction_score": 6, "synthesis": ""},
                {"symbol": "D", "final_verdict": "Buy", "aggregate_conviction_score": 4, "synthesis": ""},
            ],
        }
        apply_max_three_buys(chairman)
        verdicts = {p["symbol"]: p["final_verdict"] for p in chairman["watchlist_positions"]}
        self.assertEqual(verdicts["D"], "Pass")


if __name__ == "__main__":
    unittest.main()
