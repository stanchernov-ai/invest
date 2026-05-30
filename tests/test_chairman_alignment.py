"""Tests for chairman ↔ board majority coherence (P0.2 / run 20260529_134042)."""
import unittest

from src.core.board_roster import PANELIST_KEYS
from src.core.vote_engine import board_majority_buy_counts
from src.core.chairman_alignment import (
    apply_board_and_cap_coherence,
    ensure_majority_symbol_rows,
    fill_majority_buys_within_cap,
    reconcile_false_max_buy_narratives,
)
from src.core.guardrails import apply_chairman_guardrails, count_equity_buys
from src.core.compliance_audit import filter_spurious_majority_violations, merge_compliance_reports


def _pos(symbol, verdict, conviction=10, synthesis="Rationale."):
    return {
        "symbol": symbol,
        "final_verdict": verdict,
        "aggregate_conviction_score": conviction,
        "synthesis": synthesis,
        "narrative": {
            "champion": "Test",
            "champion_quote": "Yes.",
            "dissenter": "None",
            "dissenter_quote": "N/A",
        },
    }


def _round2_raw_verdicts(amzn_votes: int = 3) -> dict:
    """Three panelists Buy AMZN; others Pass — majority Buy on AMZN."""
    buy_agents = ("darwin", "suntzu", "tesla")[:amzn_votes]
    raw = {}
    for agent in PANELIST_KEYS:
        verdict = "Buy" if agent in buy_agents else "Pass"
        raw[agent] = {
            "portfolio_verdicts": [],
            "watchlist_verdicts": [
                {"symbol": "META", "verdict": "Buy", "conviction_score": 8},
                {"symbol": "MNDY", "verdict": "Buy", "conviction_score": 7},
                {"symbol": "AMZN", "verdict": verdict, "conviction_score": 6},
            ],
        }
    return raw


class TestChairmanAlignment(unittest.TestCase):
    def test_board_majority_buy_counts(self):
        counts = board_majority_buy_counts(_round2_raw_verdicts(3))
        self.assertEqual(counts.get("AMZN"), 3)
        self.assertEqual(counts.get("META"), 5)

    def test_134042_scenario_promotes_amzn_when_slot_available(self):
        """Chairman Pass on AMZN citing max-3 with only META+MNDY buys — fix in Python."""
        chairman = {
            "chain_of_thought_scratchpad": "AMZN majority Buy but max 3 limit.",
            "capital_flow_audit": {
                "liquidated_tickers": [],
                "target_tickers": ["META", "MNDY"],
            },
            "portfolio_positions": [],
            "watchlist_positions": [
                _pos("META", "Buy", 30),
                _pos("MNDY", "Buy", 25),
                _pos(
                    "AMZN",
                    "Pass",
                    20,
                    "Demoted to Pass citing Maximum 3 Buys limit despite board majority.",
                ),
            ],
        }
        raw = _round2_raw_verdicts(3)
        result = apply_chairman_guardrails(
            chairman,
            total_portfolio_value=100_000.0,
            portfolio_holdings={},
            purchase_dates={},
            raw_verdicts=raw,
        )
        amzn = next(p for p in result["watchlist_positions"] if p["symbol"] == "AMZN")
        self.assertEqual(amzn["final_verdict"], "Buy")
        self.assertIn("Board majority Buy", amzn["synthesis"])
        self.assertIn("AMZN", result["capital_flow_audit"]["target_tickers"])
        self.assertEqual(count_equity_buys(result), 3)

    def test_reconcile_strips_false_max_buy_when_under_cap(self):
        chairman = {
            "capital_flow_audit": {"target_tickers": ["META"], "liquidated_tickers": []},
            "portfolio_positions": [],
            "watchlist_positions": [
                _pos("META", "Buy", 30),
                _pos("AMZN", "Pass", 10, "Pass due to Maximum 3 Buys limit."),
            ],
        }
        reconcile_false_max_buy_narratives(chairman)
        amzn = chairman["watchlist_positions"][1]
        self.assertNotIn("Maximum 3 Buys", amzn["synthesis"])
        self.assertIn("SYSTEM NOTE", amzn["synthesis"])
        self.assertEqual(amzn["final_verdict"], "Pass")

    def test_surplus_demotion_keeps_system_override(self):
        chairman = {
            "capital_flow_audit": {"target_tickers": ["A", "B", "C"], "liquidated_tickers": []},
            "portfolio_positions": [],
            "watchlist_positions": [
                _pos("A", "Buy", 40),
                _pos("B", "Buy", 35),
                _pos("C", "Buy", 30),
                _pos(
                    "D",
                    "Pass",
                    5,
                    "[SYSTEM OVERRIDE: Maximum 3 Buys limit (conviction 5). Demoted to Pass.]",
                ),
            ],
        }
        from src.core.guardrails import enforce_max_buys

        enforce_max_buys(chairman)
        fill_majority_buys_within_cap(chairman, _round2_raw_verdicts(0))
        d = next(p for p in chairman["watchlist_positions"] if p["symbol"] == "D")
        self.assertEqual(d["final_verdict"], "Pass")
        self.assertIn("SYSTEM OVERRIDE: Maximum 3 Buys", d["synthesis"])

    def test_filter_spurious_majority_after_promotion(self):
        chairman = {
            "capital_flow_audit": {"target_tickers": ["META", "MNDY", "AMZN"], "liquidated_tickers": []},
            "portfolio_positions": [],
            "watchlist_positions": [
                _pos("META", "Buy"),
                _pos("MNDY", "Buy"),
                _pos("AMZN", "Buy", synthesis="[SYSTEM OVERRIDE: Board majority Buy (3/5 panelists, conviction 20). Slot 3/3.]"),
            ],
        }
        violation = (
            "MAJORITY VOTE ALIGNMENT: The final verdict for AMZN is non-compliant. "
            "Board voted majority Buy."
        )
        filtered = filter_spurious_majority_violations([violation], chairman)
        self.assertEqual(filtered, [])

    def test_missing_amzn_row_gets_promoted(self):
        """Chairman JSON omitted AMZN entirely — still reconcile to Buy under cap."""
        chairman = {
            "capital_flow_audit": {"target_tickers": ["META", "MNDY"], "liquidated_tickers": []},
            "portfolio_positions": [],
            "watchlist_positions": [
                _pos("META", "Buy", 30),
                _pos("MNDY", "Buy", 25),
            ],
        }
        raw = _round2_raw_verdicts(3)
        apply_board_and_cap_coherence(
            chairman,
            raw,
            portfolio_symbols=set(),
            watchlist_symbols={"META", "MNDY", "AMZN"},
        )
        symbols = {p["symbol"]: p["final_verdict"] for p in chairman["watchlist_positions"]}
        self.assertEqual(symbols["AMZN"], "Buy")
        self.assertIn("AMZN", chairman["capital_flow_audit"]["target_tickers"])

    def test_merge_filters_when_chairman_passed(self):
        chairman = {
            "capital_flow_audit": {"target_tickers": ["META", "MNDY", "AMZN"], "liquidated_tickers": []},
            "portfolio_positions": [],
            "watchlist_positions": [
                _pos("META", "Buy"),
                _pos("MNDY", "Buy"),
                _pos("AMZN", "Buy"),
            ],
        }
        merged = merge_compliance_reports(
            [],
            {
                "is_compliant": False,
                "violations": [
                    "MAJORITY VOTE ALIGNMENT: The final verdict for AMZN is non-compliant."
                ],
                "feedback_to_chairman": "Fix AMZN.",
            },
            chairman=chairman,
        )
        self.assertTrue(merged["is_compliant"])


if __name__ == "__main__":
    unittest.main()
