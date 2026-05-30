"""Tests for deterministic compliance audit (in-loop chairman gate)."""
import unittest

from src.core.board_roster import PANELIST_KEYS, PANELIST_ROLES
from src.core.compliance_audit import (
    audit_chairman_compliance,
    audit_chairman_vote_alignment,
    count_buy_verdicts,
    format_compliance_failure_summary,
    format_debate_for_compliance,
    merge_compliance_reports,
)


def _chairman(**overrides) -> dict:
    base = {
        "chain_of_thought_scratchpad": "Establish hedge in TLT.",
        "capital_allocation_narrative": "Buy META and hedge with TLT.",
        "capital_flow_audit": {
            "liquidated_tickers": ["ASML"],
            "target_tickers": ["META", "TLT"],
        },
        "portfolio_positions": [
            {"symbol": "ASML", "final_verdict": "Sell"},
        ],
        "watchlist_positions": [
            {"symbol": "META", "final_verdict": "Buy"},
            {"symbol": "MNDY", "final_verdict": "Buy"},
        ],
        "alpha_pick": {"symbol": "META", "champion_quote": "test"},
    }
    base.update(overrides)
    return base


class TestComplianceAudit(unittest.TestCase):
    def test_count_buys(self):
        self.assertEqual(count_buy_verdicts(_chairman()), 2)

    def test_passes_valid_chairman(self):
        self.assertEqual(audit_chairman_compliance(_chairman()), [])

    def test_fails_four_buys(self):
        chair = _chairman(watchlist_positions=[
            {"symbol": "META", "final_verdict": "Buy"},
            {"symbol": "MNDY", "final_verdict": "Buy"},
            {"symbol": "AMZN", "final_verdict": "Strong Buy"},
            {"symbol": "VRT", "final_verdict": "Buy"},
        ])
        violations = audit_chairman_compliance(chair)
        self.assertTrue(any("MAX 3 BUYS" in v for v in violations))

    def test_fails_hedge_narrative_without_target(self):
        chair = _chairman(
            capital_flow_audit={"liquidated_tickers": ["ASML"], "target_tickers": ["META"]},
        )
        violations = audit_chairman_compliance(chair)
        self.assertTrue(any("HEDGE" in v for v in violations))

    def test_fails_missing_hedge_entirely(self):
        chair = _chairman(
            chain_of_thought_scratchpad="No hedge today.",
            capital_allocation_narrative="Buy META only.",
            capital_flow_audit={"liquidated_tickers": ["ASML"], "target_tickers": ["META"]},
        )
        violations = audit_chairman_compliance(chair)
        self.assertTrue(any("HEDGE MANDATE" in v for v in violations))

    def test_merge_deterministic_overrides_llm_pass(self):
        merged = merge_compliance_reports(
            ["MAX 3 BUYS: 4 buys"],
            {"is_compliant": True, "violations": [], "feedback_to_chairman": "Looks fine."},
        )
        self.assertFalse(merged["is_compliant"])
        self.assertIn("MAX 3 BUYS", merged["violations"][0])

    def test_format_debate_extracts_rounds(self):
        messages = [
            {"content": "noise"},
            {"content": f"**[ROUND 2 REBUTTAL] {PANELIST_ROLES['hypatia']}**:\nBuy META (8/10)"},
        ]
        text = format_debate_for_compliance(messages)
        self.assertIn("ROUND 2", text)
        self.assertNotIn("noise", text)

    def test_fails_plurality_buy_without_majority(self):
        raw = {
            "davinci": {
                "portfolio_verdicts": [],
                "watchlist_verdicts": [
                    {"symbol": "AMZN", "verdict": "Buy", "conviction_score": 8, "analysis": "growth"},
                ],
            },
            "suntzu": {
                "portfolio_verdicts": [],
                "watchlist_verdicts": [
                    {"symbol": "AMZN", "verdict": "Buy", "conviction_score": 7, "analysis": "tape"},
                ],
            },
            "hypatia": {
                "portfolio_verdicts": [],
                "watchlist_verdicts": [
                    {"symbol": "AMZN", "verdict": "Pass", "conviction_score": 5, "analysis": "val"},
                ],
            },
        }
        chair = _chairman(
            watchlist_positions=[{"symbol": "AMZN", "final_verdict": "Buy"}],
            alpha_pick={"symbol": "AMZN", "champion_quote": "test"},
        )
        violations = audit_chairman_compliance(
            chair, raw, all_symbols=["AMZN"], portfolio_symbols=set()
        )
        self.assertTrue(any("MAJORITY BUY MANDATE" in v for v in violations))

    def test_merge_python_only_passes_when_no_violations(self):
        merged = merge_compliance_reports([], None, chairman={"portfolio_positions": []})
        self.assertTrue(merged["is_compliant"])
        self.assertEqual(merged["violations"], [])

    def test_merge_python_only_fails_on_deterministic_violations(self):
        merged = merge_compliance_reports(
            ["MAJORITY VOTE ALIGNMENT: META board majority is buy but chairman final_verdict is Pass."],
            None,
            chairman={"watchlist_positions": [{"symbol": "META", "final_verdict": "Pass", "synthesis": ""}]},
        )
        self.assertFalse(merged["is_compliant"])
        self.assertEqual(len(merged["violations"]), 1)

    def test_surplus_majority_buy_demotion_not_a_violation(self):
        raw = {}
        for i, agent in enumerate(PANELIST_KEYS):
            raw[agent] = {
                "portfolio_verdicts": [],
                "watchlist_verdicts": [
                    {"symbol": "META", "verdict": "Buy", "conviction_score": 9},
                    {"symbol": "PLTR", "verdict": "Buy", "conviction_score": 8},
                    {"symbol": "NVDA", "verdict": "Buy", "conviction_score": 7},
                    {"symbol": "MNDY", "verdict": "Buy" if i < 3 else "Pass", "conviction_score": 6},
                ],
            }
        chairman = {
            "alpha_pick": {"symbol": "META", "champion_quote": "test"},
            "portfolio_positions": [],
            "watchlist_positions": [
                {"symbol": "META", "final_verdict": "Buy", "synthesis": ""},
                {"symbol": "PLTR", "final_verdict": "Buy", "synthesis": ""},
                {"symbol": "NVDA", "final_verdict": "Buy", "synthesis": ""},
                {"symbol": "MNDY", "final_verdict": "Pass", "synthesis": "Max 3 buys."},
            ],
        }
        violations = audit_chairman_vote_alignment(
            chairman, raw, all_symbols=["META", "PLTR", "NVDA", "MNDY"], portfolio_symbols=set(),
        )
        self.assertFalse(any("MNDY" in v for v in violations))

    def test_failure_summary_includes_violations(self):
        summary = format_compliance_failure_summary(
            violations=["HEDGE MANDATE: TLT missing"],
            feedback="Add TLT to target_tickers.",
            attempts=1,
        )
        self.assertIn("HEDGE MANDATE", summary)
        self.assertIn("Add TLT", summary)
        self.assertIn("no retry", summary.lower())
        self.assertIn("expert review", summary.lower())


if __name__ == "__main__":
    unittest.main()
