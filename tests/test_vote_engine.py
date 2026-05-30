"""Tests for deterministic vote_engine (Phase A SSOT + Phase B allocation)."""
import unittest

from src.core.compliance_audit import audit_chairman_compliance
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


def _raw_all_hold(symbols: list[str]) -> dict:
    raw = {}
    for agent in ("buffett", "lynch", "livermore", "huang", "simons"):
        raw[agent] = {
            "portfolio_verdicts": [{"symbol": s, "verdict": "Hold", "conviction_score": 5} for s in symbols[:2]],
            "watchlist_verdicts": [{"symbol": s, "verdict": "Pass", "conviction_score": 5} for s in symbols[2:]],
        }
    return raw


def _raw_unanimous_buy(symbol: str) -> dict:
    raw = {}
    for agent in ("buffett", "lynch", "livermore", "huang", "simons"):
        raw[agent] = {
            "portfolio_verdicts": [],
            "watchlist_verdicts": [{"symbol": symbol, "verdict": "Buy", "conviction_score": 8}],
        }
    return raw


def _raw_symbol_votes(symbol: str, verdicts: list[tuple[str, int]]) -> dict:
    """verdicts: list of (agent_key, (verdict, conviction)) in panel order."""
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


def _majority_buy_raw(symbol: str, buy_conviction: int = 7, pass_conviction: int = 3) -> dict:
    return _raw_symbol_votes(
        symbol,
        [
            ("Buy", buy_conviction),
            ("Buy", buy_conviction),
            ("Buy", buy_conviction),
            ("Pass", pass_conviction),
            ("Pass", pass_conviction),
        ],
    )


class TestVoteEngine(unittest.TestCase):
    def test_unanimous_actionable_buy_day_bypass(self):
        raw = {}
        for agent in ("buffett", "lynch", "livermore", "huang", "simons"):
            raw[agent] = {
                "portfolio_verdicts": [{"symbol": "NVDA", "verdict": "Hold", "conviction_score": 6}],
                "watchlist_verdicts": [{"symbol": "META", "verdict": "Buy", "conviction_score": 9}],
            }
        summaries = build_vote_summaries(
            raw, ["NVDA", "META"], portfolio_symbols={"NVDA"},
        )
        self.assertTrue(summaries["META"].is_actionable_unanimous())
        self.assertTrue(can_determine_allocation(summaries))
        self.assertTrue(can_bypass_chairman(summaries))

        raw = _raw_unanimous_buy("META")
        summaries = build_vote_summaries(raw, ["META"])
        self.assertTrue(summaries["META"].is_actionable_unanimous())
        unicorns = detect_unicorn_trades(summaries)
        self.assertEqual(len(unicorns), 1)
        self.assertEqual(unicorns[0]["symbol"], "META")

    def test_majority_buy_is_deterministic_allocation(self):
        raw = _majority_buy_raw("META")
        summaries = build_vote_summaries(raw, ["META"])
        self.assertFalse(summaries["META"].is_actionable_unanimous())
        self.assertFalse(summaries["META"].needs_chairman_judgment())
        self.assertTrue(can_determine_allocation(summaries))
        self.assertEqual(mandate_verdict(summaries["META"]), "Buy")

    def test_all_hold_day_bypass(self):
        raw = _raw_all_hold(["NVDA", "AVGO", "META", "MNDY"])
        summaries = build_vote_summaries(
            raw, ["NVDA", "AVGO", "META", "MNDY"], portfolio_symbols={"NVDA", "AVGO"},
        )
        self.assertTrue(can_determine_allocation(summaries))
        self.assertEqual(mandate_verdict(summaries["NVDA"]), "Hold")
        self.assertEqual(mandate_verdict(summaries["META"]), "Pass")

    def test_avgo_tie_still_allows_vote_engine_bypass(self):
        raw = _raw_symbol_votes(
            "AVGO",
            [
                ("Buy", 6),
                ("Trim", 7),
                ("Trim", 7),
                ("Hold", 5),
                ("Hold", 5),
            ],
        )
        summaries = build_vote_summaries(raw, ["AVGO"], portfolio_symbols={"AVGO"})
        self.assertTrue(summaries["AVGO"].needs_chairman_judgment())
        self.assertTrue(can_determine_allocation(summaries))
        self.assertEqual(mandate_verdict(summaries["AVGO"]), "Hold")

    def test_split_vote_still_needs_chairman(self):
        raw = _raw_symbol_votes(
            "META",
            [
                ("Buy", 8),
                ("Buy", 8),
                ("Pass", 5),
                ("Pass", 5),
                ("Hold", 4),
            ],
        )
        summaries = build_vote_summaries(raw, ["META"])
        self.assertTrue(summaries["META"].needs_chairman_judgment())
        self.assertTrue(can_determine_allocation(summaries))

    def test_build_matrix_from_json(self):
        raw = _raw_unanimous_buy("META")
        matrix = build_matrix_from_raw_verdicts(raw, ["META"])
        self.assertEqual(matrix["META"]["buffett"], "Buy")
        self.assertEqual(matrix["META"]["simons"], "Buy")

    def test_chairman_allocation_includes_hedge(self):
        raw = _raw_all_hold(["NVDA", "META"])
        skel = build_chairman_allocation(
            raw, ["NVDA", "META"], portfolio_symbols={"NVDA"}, watchlist_symbols={"META"},
        )
        self.assertIn("TLT", skel["capital_flow_audit"]["target_tickers"])
        self.assertIn("VOTE ENGINE", skel["chain_of_thought_scratchpad"])

    def test_chairman_skeleton_alias(self):
        raw = _raw_all_hold(["NVDA"])
        a = build_chairman_allocation(
            raw, ["NVDA"], portfolio_symbols={"NVDA"}, watchlist_symbols=set(),
        )
        b = build_chairman_skeleton(
            raw, ["NVDA"], portfolio_symbols={"NVDA"}, watchlist_symbols=set(),
        )
        self.assertEqual(a["portfolio_positions"][0]["final_verdict"], b["portfolio_positions"][0]["final_verdict"])

    def test_vote_digest_contains_bypass_flag(self):
        raw = _raw_all_hold(["NVDA", "META"])
        summaries = build_vote_summaries(raw, ["NVDA", "META"], portfolio_symbols={"NVDA"})
        digest = format_vote_digest(summaries, portfolio_symbols={"NVDA"})
        self.assertIn("DETERMINISTIC VOTE DIGEST", digest)
        self.assertIn("BYPASS CHAIRMAN ARBITRATION: YES", digest)

    def test_five_majority_buys_max_three(self):
        symbols = ["META", "PLTR", "NVDA", "AMZN", "GOOG"]
        raw_parts = [_majority_buy_raw(s, buy_conviction=10 - i) for i, s in enumerate(symbols)]
        raw = _merge_raw(*raw_parts)
        portfolio_symbols: set[str] = set()
        allocation = build_chairman_allocation(
            raw,
            symbols,
            portfolio_symbols=portfolio_symbols,
            watchlist_symbols=set(symbols),
        )
        buys = [
            p["symbol"]
            for p in allocation["watchlist_positions"]
            if p["final_verdict"] in ("Buy", "Strong Buy")
        ]
        self.assertEqual(len(buys), 3)
        self.assertEqual(set(buys), {"META", "PLTR", "NVDA"})
        demoted = {p["symbol"]: p["final_verdict"] for p in allocation["watchlist_positions"]}
        self.assertEqual(demoted["AMZN"], "Pass")
        self.assertEqual(demoted["GOOG"], "Pass")
        self.assertIn("[VOTE ENGINE]", allocation["watchlist_positions"][3]["synthesis"])

    def test_asml_hold_not_sell(self):
        raw = _raw_symbol_votes(
            "ASML",
            [
                ("Hold", 6),
                ("Hold", 6),
                ("Hold", 6),
                ("Pass", 4),
                ("Buy", 7),
            ],
        )
        summaries = build_vote_summaries(raw, ["ASML"], portfolio_symbols={"ASML"})
        self.assertTrue(can_determine_allocation(summaries))
        allocation = build_chairman_allocation(
            raw,
            ["ASML"],
            portfolio_symbols={"ASML"},
            watchlist_symbols=set(),
        )
        row = allocation["portfolio_positions"][0]
        self.assertEqual(row["final_verdict"], "Hold")

    def test_arm_not_alpha_with_one_buy_vote(self):
        meta_raw = _majority_buy_raw("META", buy_conviction=30)
        arm_raw = _raw_symbol_votes(
            "ARM",
            [
                ("Buy", 5),
                ("Pass", 4),
                ("Pass", 4),
                ("Pass", 4),
                ("Hold", 3),
            ],
        )
        raw = _merge_raw(meta_raw, arm_raw)
        allocation = build_chairman_allocation(
            raw,
            ["META", "ARM"],
            portfolio_symbols=set(),
            watchlist_symbols={"META", "ARM"},
        )
        self.assertEqual(allocation["alpha_pick"]["symbol"], "META")
        arm_row = next(p for p in allocation["watchlist_positions"] if p["symbol"] == "ARM")
        self.assertEqual(arm_row["final_verdict"], "Pass")

    def test_compliance_passes_vote_engine_allocation(self):
        meta_raw = _majority_buy_raw("META", buy_conviction=25)
        pltr_raw = _majority_buy_raw("PLTR", buy_conviction=20)
        asml_raw = _raw_symbol_votes(
            "ASML",
            [("Hold", 6)] * 3 + [("Pass", 4), ("Buy", 5)],
        )
        arm_raw = _raw_symbol_votes(
            "ARM",
            [("Buy", 5), ("Pass", 4), ("Pass", 4), ("Pass", 4), ("Hold", 3)],
        )
        raw = _merge_raw(meta_raw, pltr_raw, asml_raw, arm_raw)
        symbols = ["META", "PLTR", "ASML", "ARM"]
        allocation = build_chairman_allocation(
            raw,
            symbols,
            portfolio_symbols={"ASML"},
            watchlist_symbols={"META", "PLTR", "ARM"},
        )
        violations = audit_chairman_compliance(
            allocation,
            raw,
            all_symbols=symbols,
            portfolio_symbols={"ASML"},
        )
        self.assertEqual(violations, [], violations)

    def test_apply_max_three_buys_standalone(self):
        chairman = {
            "capital_flow_audit": {"liquidated_tickers": [], "target_tickers": ["TLT"]},
            "portfolio_positions": [],
            "watchlist_positions": [
                {"symbol": "A", "final_verdict": "Buy", "aggregate_conviction_score": 10, "synthesis": ""},
                {"symbol": "B", "final_verdict": "Buy", "aggregate_conviction_score": 8, "synthesis": ""},
                {"symbol": "C", "final_verdict": "Buy", "aggregate_conviction_score": 6, "synthesis": ""},
                {"symbol": "D", "final_verdict": "Buy", "aggregate_conviction_score": 4, "synthesis": ""},
            ],
        }
        apply_max_three_buys(chairman)
        verdicts = {p["symbol"]: p["final_verdict"] for p in chairman["watchlist_positions"]}
        self.assertEqual(verdicts["A"], "Buy")
        self.assertEqual(verdicts["D"], "Pass")

    def test_compliance_majority_alignment_fail(self):
        from src.core.compliance_audit import audit_chairman_vote_alignment

        raw = _raw_unanimous_buy("META")
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


if __name__ == "__main__":
    unittest.main()
