"""Tests for deterministic compliance audit (in-loop chairman gate)."""
import unittest

from src.core.compliance_audit import (
    audit_chairman_compliance,
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
            {"content": "**[ROUND 2 REBUTTAL] Warren Buffett**:\nBuy META (8/10)"},
        ]
        text = format_debate_for_compliance(messages)
        self.assertIn("ROUND 2", text)
        self.assertNotIn("noise", text)

    def test_fails_plurality_buy_without_majority(self):
        raw = {
            "lynch": {
                "portfolio_verdicts": [],
                "watchlist_verdicts": [
                    {"symbol": "AMZN", "verdict": "Buy", "conviction_score": 8, "analysis": "growth"},
                ],
            },
            "livermore": {
                "portfolio_verdicts": [],
                "watchlist_verdicts": [
                    {"symbol": "AMZN", "verdict": "Buy", "conviction_score": 7, "analysis": "tape"},
                ],
            },
            "buffett": {
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

    def test_failure_summary_includes_violations(self):
        summary = format_compliance_failure_summary(
            violations=["HEDGE MANDATE: TLT missing"],
            feedback="Add TLT to target_tickers.",
            attempts=3,
        )
        self.assertIn("HEDGE MANDATE", summary)
        self.assertIn("Add TLT", summary)
        self.assertIn("3", summary)


if __name__ == "__main__":
    unittest.main()
