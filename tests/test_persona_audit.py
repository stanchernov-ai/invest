"""Tests for deterministic persona audit (Prompt Engineer QA pre-check)."""
import unittest

from src.core.board_roster import PANELIST_ROLES
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
            _round2_msg(PANELIST_ROLES["hypatia"], "* **META**: Buy (8/10)."),
            _round2_msg(PANELIST_ROLES["davinci"], "* **META**: Hold (6/10)."),
        ]
        matrix = parse_board_matrix(messages, ["META"])
        self.assertEqual(matrix["META"]["hypatia"], "Buy")
        self.assertEqual(matrix["META"]["davinci"], "Hold")

    def test_fabricated_investor_quote_detected(self):
        messages = [
            _round2_msg(
                PANELIST_ROLES["hypatia"],
                '* **NVDA**: Hold. Buffett said "buy wonderful companies at fair prices."',
            ),
        ]
        violations, stats = audit_debate_persona(messages, ["NVDA"])
        self.assertIn("hypatia", stats["investor_quote_hits"])
        self.assertTrue(any("FABRICATED INVESTOR QUOTE" in v for v in violations))

    def test_mungeresque_framing_allowed(self):
        messages = [
            _round2_msg(
                PANELIST_ROLES["hypatia"],
                "* **NVDA**: Hold. In a Mungeresque read, the moat is wide but the price offers no margin of safety.",
            ),
        ]
        violations, _ = audit_debate_persona(messages, ["NVDA"])
        self.assertEqual(violations, [])

    def test_suntzu_forbidden_pe_ratio(self):
        messages = [
            _round2_msg(PANELIST_ROLES["suntzu"], "* **NVDA**: Buy. The P/E ratio supports momentum."),
        ]
        violations, _ = audit_debate_persona(messages, ["NVDA"])
        self.assertTrue(any("PERSONA DRIFT" in v and "Sun Tzu" in v for v in violations))

    def test_unanimous_collapse_detected(self):
        symbols = ["A", "B", "C", "D"]
        messages = []
        for sym in symbols:
            for agent in PANELIST_ROLES.values():
                messages.append(_round2_msg(agent, f"* **{sym}**: Buy (8/10)."))
        violations, stats = audit_debate_persona(messages, symbols)
        self.assertGreaterEqual(stats["unanimous_rate"], 0.6)
        self.assertTrue(any("SYCOPHANCY" in v for v in violations))

    def test_clean_debate_passes_deterministic(self):
        messages = [
            _round2_msg(PANELIST_ROLES["hypatia"], "* **META**: Hold. Cash flow adequate but no margin of safety."),
            _round2_msg(PANELIST_ROLES["suntzu"], "* **META**: Trim. Tape weakening vs QQQ."),
            _round2_msg(PANELIST_ROLES["aurelius"], "* **META**: Hold. Beta elevated; edge unclear."),
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

    def test_verbatim_r1_copy_detected_in_persona_audit(self):
        shared = "The portfolio is too concentrated in mega-cap tech without margin of safety."
        hypatia = PANELIST_ROLES["hypatia"]
        messages = [
            {
                "content": (
                    f"**[ROUND 1] {hypatia}**:\n* **Portfolio Overview**: {shared}\n"
                    "* **NVDA**: Hold (5/10).\n"
                )
            },
            {
                "content": (
                    f"**[ROUND 2 REBUTTAL] {hypatia}**:\n* **Rebuttal Summary**: {shared}\n"
                    "* **NVDA**: Hold (5/10).\n"
                )
            },
        ]
        violations, stats = audit_debate_persona(messages, ["NVDA"])
        self.assertIn("hypatia", stats["verbatim_r1_copies"])
        self.assertTrue(any("VERBATIM R1 COPY" in v for v in violations))

    def test_format_digest_includes_stats(self):
        text = format_persona_digest([], {"total_tickers": 5, "unanimous_tickers": 0, "unanimous_rate": 0.0})
        self.assertIn("PASS", text)
        self.assertIn("5 tickers", text)

    def test_cumulative_messages_do_not_bleed_peer_vocabulary(self):
        """Prod debate checkpoints append R2 blocks; scan only the agent's section."""
        cumulative = {
            "content": (
                f"**[ROUND 2 REBUTTAL] {PANELIST_ROLES['davinci']}**:\n"
                "* **Rebuttal Summary**: The portfolio's problem isn't high P/E ratios.\n"
                "* **NET**: Pass (2/10). This is a story stock with no earnings.\n\n"
                f"**[ROUND 2 REBUTTAL] {PANELIST_ROLES['suntzu']}**:\n"
                "* **Rebuttal Summary**: The tape is the only truth.\n"
                "* **NVDA**: Strong Sell (10/10). Lagging the QQQ.\n\n"
                f"**[ROUND 2 REBUTTAL] {PANELIST_ROLES['aurelius']}**:\n"
                "* **Rebuttal Summary**: Alpha decay requires reallocation.\n"
                "* **NVDA**: Strong Buy (10/10). PEG 0.29 supports the edge.\n"
            )
        }
        violations, _ = audit_debate_persona([cumulative], ["NVDA", "NET"])
        drift = [v for v in violations if "PERSONA DRIFT" in v]
        self.assertEqual(drift, [])


if __name__ == "__main__":
    unittest.main()
