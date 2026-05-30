"""Tests for deterministic Post Mortem vote verification."""
import json
import unittest

from src.core.board_roster import PANELIST_KEYS, PANELIST_ROLES
from src.core.compliance_audit import audit_chairman_compliance
from src.qa.post_mortem_audit import (
    audit_debate_prose_vs_raw_verdicts,
    audit_post_mortem_deterministic,
    audit_scratchpad_digest_consistency,
    format_post_mortem_digest,
    merge_post_mortem_reports,
)


def _raw_verdicts_amzn_buy_votes(buy_count: int) -> dict:
    agents = list(PANELIST_KEYS)
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

    def test_merge_pass_without_llm(self):
        merged = merge_post_mortem_reports([], None)
        self.assertTrue(merged["is_compliant"])

    def test_scratchpad_digest_must_match_raw_verdicts(self):
        raw = _raw_verdicts_amzn_buy_votes(3)
        chairman = _chairman_amzn_buy()
        chairman["chain_of_thought_scratchpad"] = (
            "PYTHON VOTE ENGINE ALLOCATION\n\n"
            "DETERMINISTIC VOTE DIGEST (Round 2 JSON — authoritative; do not re-count from prose):\n"
            "  AMZN: buy_side=2/5 sell_side=0/5 pass=3/5 → mandate=Pass\n"
        )
        violations = audit_scratchpad_digest_consistency(
            chairman, raw, all_symbols=["AMZN"], portfolio_symbols=set()
        )
        self.assertTrue(any("SCRATCHPAD DIGEST MISMATCH" in v and "AMZN" in v for v in violations))

    def test_debate_prose_drift_detected(self):
        raw = _raw_verdicts_amzn_buy_votes(3)
        messages = [{
            "content": (
                f"**[ROUND 2 REBUTTAL] {PANELIST_ROLES['hypatia']}**:\n"
                "* **AMZN**: Pass (2/10).\n"
                f"**[ROUND 2 REBUTTAL] {PANELIST_ROLES['davinci']}**:\n"
                "* **AMZN**: Buy (8/10).\n"
            )
        }]
        # hypatia Pass in prose but Buy in raw for first agent — fix raw to create drift
        raw["hypatia"]["watchlist_verdicts"][0]["verdict"] = "Buy"
        violations = audit_debate_prose_vs_raw_verdicts(
            messages, raw, all_symbols=["AMZN"]
        )
        self.assertTrue(any("VOTE JSON/PROSE DRIFT" in v and PANELIST_ROLES["hypatia"] in v for v in violations))

    def test_cumulative_debate_messages_align_with_json(self):
        import json
        from pathlib import Path

        debate_path = Path(".cache/state/debate.json")
        if not debate_path.exists():
            self.skipTest("cached debate.json not available")
        debate = json.loads(debate_path.read_text(encoding="utf-8"))
        prep = json.loads(Path(".cache/state/prepare.json").read_text(encoding="utf-8"))
        violations = audit_debate_prose_vs_raw_verdicts(
            debate.get("raw_board_messages") or [],
            debate.get("raw_verdicts") or {},
            all_symbols=prep.get("all_symbols") or [],
        )
        self.assertEqual(violations, [], violations[:3] if violations else None)


if __name__ == "__main__":
    unittest.main()
