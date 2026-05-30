"""Tests for deterministic Systems Architect QA gating."""
import json
import unittest
from unittest.mock import AsyncMock, patch

from src.core.vote_engine import AGENT_KEYS
from src.qa.architect_audit import (
    audit_chairman_structure,
    audit_debate_log_bloat,
    audit_repetitive_synthesis,
    audit_system_architect_deterministic,
    audit_watchlist_pass_spam,
    merge_architect_reports,
)
from src.qa_pipeline import run_system_architect_qa


def _minimal_chairman(**overrides) -> dict:
    base = {
        "portfolio_positions": [
            {"symbol": "NVDA", "final_verdict": "Hold", "synthesis": "Hold for growth."},
        ],
        "watchlist_positions": [
            {"symbol": "AMZN", "final_verdict": "Pass", "synthesis": "Wait for entry."},
        ],
        "chain_of_thought_scratchpad": "Digest OK.",
    }
    base.update(overrides)
    return base


def _minimal_raw_verdicts() -> dict:
    return {
        agent: {
            "overall_portfolio_critique": "Round 2.",
            "portfolio_verdicts": [{"symbol": "NVDA", "verdict": "Hold", "analysis": "x"}],
            "watchlist_verdicts": [{"symbol": "AMZN", "verdict": "Pass", "analysis": "x"}],
        }
        for agent in AGENT_KEYS
    }


class TestArchitectAudit(unittest.TestCase):
    def test_chairman_structure_flags_duplicate_symbols(self):
        chairman = _minimal_chairman(
            portfolio_positions=[
                {"symbol": "NVDA", "final_verdict": "Hold", "synthesis": "a"},
                {"symbol": "NVDA", "final_verdict": "Sell", "synthesis": "b"},
            ],
            watchlist_positions=[],
        )
        violations = audit_chairman_structure(chairman)
        self.assertTrue(any("duplicate symbol 'NVDA'" in v for v in violations))

    def test_repetitive_synthesis_detected(self):
        shared = "Identical strategic context copied across many names for testing."
        chairman = _minimal_chairman(
            portfolio_positions=[
                {"symbol": sym, "final_verdict": "Hold", "synthesis": shared}
                for sym in ("A", "B", "C", "D")
            ],
            watchlist_positions=[],
        )
        violations = audit_repetitive_synthesis(chairman)
        self.assertEqual(len(violations), 1)
        self.assertIn("REPETITIVE SYNTHESIS", violations[0])

    def test_debate_log_pass_spam_detected(self):
        symbols = [f"SYM{i}" for i in range(15)]
        log = "\n".join(f"{sym}: Pass" for sym in symbols for _ in range(8))
        violations = audit_debate_log_bloat(log, all_symbols=symbols)
        self.assertTrue(any("Pass' mentions" in v for v in violations))

    def test_watchlist_pass_spam_detected(self):
        watchlist = [{"symbol": f"W{i}", "verdict": "Pass", "analysis": "x"} for i in range(12)]
        raw = {
            agent: {
                "portfolio_verdicts": [],
                "watchlist_verdicts": watchlist,
            }
            for agent in AGENT_KEYS
        }
        violations = audit_watchlist_pass_spam(raw)
        self.assertEqual(len(violations), 1)

    def test_clean_run_passes_deterministic(self):
        violations = audit_system_architect_deterministic(
            _minimal_chairman(),
            "Short debate log.",
            _minimal_raw_verdicts(),
            all_symbols=["NVDA", "AMZN"],
        )
        self.assertEqual(violations, [])

    def test_merge_architect_pass_without_llm(self):
        merged = merge_architect_reports([], None)
        self.assertTrue(merged["is_compliant"])
        self.assertIn("LLM audit skipped", merged["summary"])


class TestArchitectQaGating(unittest.IsolatedAsyncioTestCase):
    async def test_deterministic_pass_skips_gemini(self):
        chairman = _minimal_chairman()
        with patch("src.qa_pipeline.call_gemini_async", new_callable=AsyncMock) as mock_llm:
            report = await run_system_architect_qa(
                "Short log.",
                json.dumps(chairman),
                raw_verdicts=_minimal_raw_verdicts(),
                all_symbols=["NVDA", "AMZN"],
            )
        mock_llm.assert_not_called()
        self.assertTrue(report["is_compliant"])
        self.assertEqual(report["agent_role"], "Systems Architect QA")

    async def test_deterministic_fail_skips_gemini(self):
        chairman = _minimal_chairman(portfolio_positions=[])
        with patch("src.qa_pipeline.call_gemini_async", new_callable=AsyncMock) as mock_llm:
            report = await run_system_architect_qa(
                "Short log.",
                json.dumps(chairman),
                raw_verdicts=None,
                all_symbols=["NVDA"],
            )
        mock_llm.assert_not_called()
        self.assertFalse(report["is_compliant"])
        self.assertTrue(report["findings"])


if __name__ == "__main__":
    unittest.main()
