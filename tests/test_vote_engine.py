"""Tests for deterministic vote_engine (Phase A SSOT)."""
import unittest

from src.core.compliance_audit import audit_chairman_vote_alignment
from src.core.vote_engine import (
    build_chairman_skeleton,
    build_matrix_from_raw_verdicts,
    build_vote_summaries,
    can_bypass_chairman,
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
        self.assertTrue(can_bypass_chairman(summaries))

        raw = _raw_unanimous_buy("META")
        summaries = build_vote_summaries(raw, ["META"])
        self.assertTrue(summaries["META"].is_actionable_unanimous())
        unicorns = detect_unicorn_trades(summaries)
        self.assertEqual(len(unicorns), 1)
        self.assertEqual(unicorns[0]["symbol"], "META")

    def test_majority_buy_not_bypass(self):
        raw = {}
        for i, agent in enumerate(("buffett", "lynch", "livermore", "huang", "simons")):
            raw[agent] = {
                "portfolio_verdicts": [],
                "watchlist_verdicts": [
                    {"symbol": "META", "verdict": "Buy" if i < 3 else "Pass", "conviction_score": 7},
                ],
            }
        summaries = build_vote_summaries(raw, ["META"])
        self.assertFalse(summaries["META"].is_actionable_unanimous())
        self.assertTrue(summaries["META"].needs_chairman_judgment())
        self.assertFalse(can_bypass_chairman(summaries))

    def test_all_hold_day_bypass(self):
        raw = _raw_all_hold(["NVDA", "AVGO", "META", "MNDY"])
        summaries = build_vote_summaries(
            raw, ["NVDA", "AVGO", "META", "MNDY"], portfolio_symbols={"NVDA", "AVGO"},
        )
        self.assertTrue(can_bypass_chairman(summaries))
        self.assertEqual(mandate_verdict(summaries["NVDA"]), "Hold")
        self.assertEqual(mandate_verdict(summaries["META"]), "Pass")

    def test_build_matrix_from_json(self):
        raw = _raw_unanimous_buy("META")
        matrix = build_matrix_from_raw_verdicts(raw, ["META"])
        self.assertEqual(matrix["META"]["buffett"], "Buy")
        self.assertEqual(matrix["META"]["simons"], "Buy")

    def test_chairman_skeleton_includes_hedge(self):
        raw = _raw_all_hold(["NVDA", "META"])
        skel = build_chairman_skeleton(
            raw, ["NVDA", "META"], portfolio_symbols={"NVDA"}, watchlist_symbols={"META"},
        )
        self.assertIn("TLT", skel["capital_flow_audit"]["target_tickers"])
        self.assertIn("VOTE ENGINE", skel["chain_of_thought_scratchpad"])

    def test_vote_digest_contains_bypass_flag(self):
        raw = _raw_all_hold(["NVDA", "META"])
        summaries = build_vote_summaries(raw, ["NVDA", "META"], portfolio_symbols={"NVDA"})
        digest = format_vote_digest(summaries, portfolio_symbols={"NVDA"})
        self.assertIn("DETERMINISTIC VOTE DIGEST", digest)
        self.assertIn("BYPASS CHAIRMAN ARBITRATION: YES", digest)

    def test_compliance_majority_alignment_fail(self):
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
