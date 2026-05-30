"""Tests for deterministic Post Mortem vote verification."""
import json
import unittest

from src.core.compliance_audit import audit_chairman_compliance
from src.qa.post_mortem_audit import (
    audit_post_mortem_deterministic,
    format_post_mortem_digest,
    merge_post_mortem_reports,
)


def _raw_verdicts_amzn_buy_votes(buy_count: int) -> dict:
    agents = ["buffett", "lynch", "livermore", "huang", "simons"]
    buy_agents = agents[:buy_count]
    raw = {}
    for agent in agents:
        verdict = "Buy" if agent in buy_agents else "Pass"
        raw[agent] = {
            "overall_portfolio_critique": f"{agent} round 2 view.",
            "portfolio_verdicts": [],
            "watchlist_verdicts": [
                {"symbol": "AMZN", "verdict": verdict, "conviction_score": 7, "analysis": "test"},
            ],
        }
    return raw


def _chairman_amzn_buy() -> dict:
    return {
        "chain_of_thought_scratchpad": "Buy AMZN.",
        "capital_allocation_narrative": "Hedge with TLT.",
        "capital_flow_audit": {
            "liquidated_tickers": ["AVGO"],
            "target_tickers": ["AMZN", "TLT"],
        },
        "portfolio_positions": [],
        "watchlist_positions": [
            {"symbol": "AMZN", "final_verdict": "Buy", "synthesis": "Majority buy."},
        ],
        "alpha_pick": {"symbol": "NVDA", "champion_quote": "test"},
    }


class TestPostMortemAudit(unittest.TestCase):
    def test_plurality_buy_fails_compliance(self):
        violations = audit_chairman_compliance(
            _chairman_amzn_buy(),
            _raw_verdicts_amzn_buy_votes(2),
            all_symbols=["AMZN"],
            portfolio_symbols=set(),
        )
        self.assertTrue(any("MAJORITY BUY MANDATE" in v and "AMZN" in v for v in violations))

    def test_majority_buy_passes_compliance(self):
        violations = audit_chairman_compliance(
            _chairman_amzn_buy(),
            _raw_verdicts_amzn_buy_votes(3),
            all_symbols=["AMZN"],
            portfolio_symbols=set(),
        )
        majority_violations = [v for v in violations if "MAJORITY BUY MANDATE" in v and "AMZN" in v]
        self.assertEqual(majority_violations, [])

    def test_missing_raw_verdicts_fails_post_mortem(self):
        violations = audit_post_mortem_deterministic(
            _chairman_amzn_buy(),
            None,
            all_symbols=["AMZN"],
            portfolio_symbols=set(),
        )
        self.assertTrue(any("raw_verdicts missing" in v for v in violations))

    def test_merge_forces_fail_when_llm_passes(self):
        violations = audit_post_mortem_deterministic(
            _chairman_amzn_buy(),
            _raw_verdicts_amzn_buy_votes(2),
            all_symbols=["AMZN"],
            portfolio_symbols=set(),
        )
        merged = merge_post_mortem_reports(
            violations,
            {"is_compliant": True, "findings": [], "summary": "All good.", "agent_role": "Post Mortem QA Auditor"},
        )
        self.assertFalse(merged["is_compliant"])
        self.assertTrue(any("MAJORITY BUY MANDATE" in f["description"] for f in merged["findings"]))

    def test_digest_includes_vote_counts(self):
        digest = format_post_mortem_digest(
            [],
            _raw_verdicts_amzn_buy_votes(3),
            all_symbols=["AMZN"],
            portfolio_symbols=set(),
        )
        self.assertIn("AMZN", digest)
        self.assertIn("buy_side=3", digest)


if __name__ == "__main__":
    unittest.main()
