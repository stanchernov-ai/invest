"""Tests for deterministic persona audit (Prompt Engineer QA pre-check)."""
import unittest

from src.qa.persona_audit import (
    audit_debate_persona,
    format_persona_digest,
    merge_persona_reports,
    sanitize_rubber_stamp_pass,
)


def _round2_msg(agent_name: str, body: str) -> dict:
    return {"content": f"**[ROUND 2 REBUTTAL] {agent_name}**:\n{body}"}


class TestPersonaAudit(unittest.TestCase):
    def test_parse_board_matrix_round2_headers(self):
        from src.qa_pipeline import parse_board_matrix

        messages = [
            _round2_msg("Warren Buffett", "* **META**: Buy (8/10)."),
            _round2_msg("Peter Lynch", "* **META**: Hold (6/10)."),
        ]
        matrix = parse_board_matrix(messages, ["META"])
        self.assertEqual(matrix["META"]["buffett"], "Buy")
        self.assertEqual(matrix["META"]["lynch"], "Hold")

    def test_livermore_forbidden_pe_ratio(self):
        messages = [
            _round2_msg("Jesse Livermore", "* **NVDA**: Buy. The P/E ratio supports momentum."),
        ]
        violations, _ = audit_debate_persona(messages, ["NVDA"])
        self.assertTrue(any("PERSONA DRIFT" in v and "Livermore" in v for v in violations))

    def test_unanimous_collapse_detected(self):
        symbols = ["A", "B", "C", "D"]
        messages = []
        for sym in symbols:
            for agent in ("Warren Buffett", "Peter Lynch", "Jesse Livermore", "Jensen Huang", "Jim Simons"):
                messages.append(_round2_msg(agent, f"* **{sym}**: Buy (8/10)."))
        violations, stats = audit_debate_persona(messages, symbols)
        self.assertGreaterEqual(stats["unanimous_rate"], 0.6)
        self.assertTrue(any("SYCOPHANCY" in v for v in violations))

    def test_clean_debate_passes_deterministic(self):
        messages = [
            _round2_msg("Warren Buffett", "* **META**: Hold. Cash flow adequate but no margin of safety."),
            _round2_msg("Jesse Livermore", "* **META**: Trim. Tape weakening vs QQQ."),
            _round2_msg("Jim Simons", "* **META**: Hold. Beta elevated; edge unclear."),
        ]
        violations, _ = audit_debate_persona(messages, ["META"])
        self.assertEqual(violations, [])

    def test_merge_deterministic_overrides_llm_pass(self):
        merged = merge_persona_reports(
            ["SYCOPHANCY / DEBATE COLLAPSE: test"],
            {"is_compliant": True, "findings": [], "summary": "All good.", "agent_role": "Prompt Engineer QA"},
        )
        self.assertFalse(merged["is_compliant"])
        self.assertTrue(any("SYCOPHANCY" in f["description"] for f in merged["findings"]))

    def test_sanitize_rubber_stamp_pass(self):
        report = {
            "agent_role": "Prompt Engineer QA",
            "is_compliant": True,
            "findings": [{"severity": "INFO", "category": "Praise", "description": "Great job.", "recommendation": "None"}],
            "summary": "Healthy debate.",
        }
        out = sanitize_rubber_stamp_pass(report)
        self.assertFalse(out["is_compliant"])
        self.assertTrue(any(f["category"] == "Rubber Stamp" for f in out["findings"]))

    def test_format_digest_includes_stats(self):
        text = format_persona_digest([], {"total_tickers": 5, "unanimous_tickers": 0, "unanimous_rate": 0.0})
        self.assertIn("PASS", text)
        self.assertIn("5 tickers", text)


if __name__ == "__main__":
    unittest.main()
