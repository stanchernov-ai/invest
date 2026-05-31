"""INT-1 — vote digest as ground truth for integrity / post-mortem cross-checks."""
import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from src.core.compliance_audit import audit_chairman_compliance_limits
from src.qa.integrity_audit import (
    audit_post_mortem_report_accuracy,
    build_vote_ground_truth_context,
    format_vote_ground_truth_digest,
    sanitize_llm_integrity_findings,
)
from src.qa.post_mortem_audit import audit_post_mortem_deterministic

DEBATE_PATH = Path(".cache/state/debate.json")
PREP_PATH = Path(".cache/state/prepare.json")


class TestVoteGroundTruthContext(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not DEBATE_PATH.exists():
            cls.debate = cls.prep = None
            return
        cls.debate = json.loads(DEBATE_PATH.read_text(encoding="utf-8"))
        cls.prep = json.loads(PREP_PATH.read_text(encoding="utf-8"))

    def test_run_181651_prose_matches_json(self):
        if not self.debate:
            self.skipTest("cached debate.json not available")
        ctx = build_vote_ground_truth_context(
            self.debate["chairman_data"],
            self.debate.get("raw_verdicts"),
            all_symbols=self.prep.get("all_symbols") or [],
            portfolio_symbols=set(self.prep.get("portfolio_holdings") or {}),
            raw_board_messages=self.debate.get("raw_board_messages"),
        )
        self.assertEqual(ctx["prose_drift"], [])
        self.assertEqual(ctx["deterministic_violations"], [])
        self.assertEqual(ctx["equity_buy_count"], 3)
        digest = format_vote_ground_truth_digest(ctx)
        self.assertIn("DETERMINISTIC VOTE DIGEST", digest)
        self.assertIn("MAX EQUITY BUYS: 3/3", digest)
        self.assertIn("DETERMINISTIC POST MORTEM RE-CHECK: PASS", digest)

    def test_asml_avgo_tsm_mandates_in_digest(self):
        if not self.debate:
            self.skipTest("cached debate.json not available")
        ctx = build_vote_ground_truth_context(
            self.debate["chairman_data"],
            self.debate.get("raw_verdicts"),
            all_symbols=self.prep.get("all_symbols") or [],
            portfolio_symbols=set(self.prep.get("portfolio_holdings") or {}),
        )
        digest = ctx["vote_digest_text"]
        for sym in ("ASML", "AVGO", "TSM"):
            self.assertIn(f"{sym}:", digest)
        # Sell-side majority for ASML/TSM (exact 4/5 vs 5/5 varies by run — mandate=Sell is stable).
        self.assertRegex(digest, r"ASML:.*sell_side=[34]/5.*mandate=Sell")
        self.assertRegex(digest, r"TSM:.*sell_side=[34]/5.*mandate=Sell")


class TestPostMortemReportAccuracy(unittest.TestCase):
    def test_flags_rubber_stamped_pass(self):
        vote_ctx = {
            "deterministic_violations": ["MAJORITY BUY MANDATE: AMZN 2/5"],
        }
        qa_reports = [{
            "agent_role": "Post Mortem QA Auditor",
            "is_compliant": True,
            "findings": [],
        }]
        findings = audit_post_mortem_report_accuracy(qa_reports, vote_ctx)
        self.assertEqual(len(findings), 1)
        self.assertIn("reported PASS", findings[0]["description"])

    def test_pass_when_aligned(self):
        vote_ctx = {"deterministic_violations": []}
        qa_reports = [{
            "agent_role": "Post Mortem QA Auditor",
            "is_compliant": True,
            "findings": [],
        }]
        self.assertEqual(audit_post_mortem_report_accuracy(qa_reports, vote_ctx), [])


class TestIntegritySanitizerMaxBuy(unittest.TestCase):
    def test_drops_false_target_tickers_max_buy(self):
        vote_ctx = {"equity_buy_count": 3, "max_equity_buys": 3, "deterministic_violations": []}
        findings = sanitize_llm_integrity_findings([{
            "severity": "CRITICAL",
            "category": "Verdict Accuracy - Post Mortem QA",
            "description": (
                "Post Mortem failed to identify max 3 buy violation — target_tickers lists "
                "TLT, AMZN, NVDA, VRT (4 items)."
            ),
            "recommendation": "Fix post mortem.",
        }], {}, vote_ctx=vote_ctx)
        self.assertEqual(findings, [])

    def test_keeps_real_max_buy_violation(self):
        vote_ctx = {"equity_buy_count": 4, "max_equity_buys": 3, "deterministic_violations": []}
        findings = sanitize_llm_integrity_findings([{
            "severity": "CRITICAL",
            "category": "Verdict Accuracy",
            "description": "Chairman JSON lists 4 equity Buy verdicts exceeding max 3.",
            "recommendation": "Fail post mortem.",
        }], {}, vote_ctx=vote_ctx)
        self.assertEqual(len(findings), 1)


class TestComplianceEquityBuyCap(unittest.TestCase):
    def test_hedge_excluded_from_max_buy_count(self):
        chairman = {
            "portfolio_positions": [
                {"symbol": "AMZN", "final_verdict": "Buy"},
                {"symbol": "NVDA", "final_verdict": "Strong Buy"},
                {"symbol": "VRT", "final_verdict": "Buy"},
                {"symbol": "TLT", "final_verdict": "Buy"},
            ],
            "watchlist_positions": [],
            "capital_flow_audit": {
                "target_tickers": ["TLT", "AMZN", "NVDA", "VRT"],
            },
        }
        violations = audit_chairman_compliance_limits(chairman)
        max_buy = [v for v in violations if "MAX 3 BUYS" in v]
        self.assertEqual(max_buy, [])


class TestIntegrityPromptIncludesVoteDigest(unittest.IsolatedAsyncioTestCase):
    async def test_integrity_prompt_has_vote_ground_truth(self):
        from src.qa_pipeline import run_qa_integrity_audit

        with patch("src.qa_pipeline.call_gemini_async", new_callable=AsyncMock) as mock_llm:
            await run_qa_integrity_audit(
                [{"agent_role": "Post Mortem QA Auditor", "is_compliant": True, "findings": []}],
                "debate log",
                "{}",
                "<html></html>",
                raw_verdicts={},
                all_symbols=[],
            )
        prompt = mock_llm.call_args[0][1][0].parts[0].text
        self.assertIn("VOTE GROUND TRUTH", prompt)
        self.assertIn("vote counts come from VOTE GROUND TRUTH", prompt)


if __name__ == "__main__":
    unittest.main()
