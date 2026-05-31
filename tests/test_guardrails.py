import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from src.core.guardrails import (
    MAX_DAILY_BUYS,
    apply_chairman_guardrails,
    enforce_liquidation_cap,
    enforce_max_buys,
    enforce_wash_sale,
    _within_wash_sale_window,
)


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


class TestMaxBuys(unittest.TestCase):
    def test_keeps_top_three_by_conviction(self):
        chairman = {
            "capital_flow_audit": {"target_tickers": ["A", "B", "C", "D"], "liquidated_tickers": []},
            "portfolio_positions": [],
            "watchlist_positions": [
                _pos("A", "Accumulate Candidate", 30),
                _pos("B", "High Conviction (Overweight)", 25),
                _pos("C", "Accumulate Candidate", 20),
                _pos("D", "Accumulate Candidate", 15),
            ],
        }
        result = enforce_max_buys(chairman)
        verdicts = {p["symbol"]: p["final_verdict"] for p in result["watchlist_positions"]}
        self.assertEqual(verdicts["A"], "Accumulate Candidate")
        self.assertEqual(verdicts["B"], "High Conviction (Overweight)")
        self.assertEqual(verdicts["C"], "Accumulate Candidate")
        self.assertEqual(verdicts["D"], "Pass")
        self.assertIn("Maximum 3 Buys", result["watchlist_positions"][3]["synthesis"])
        self.assertEqual(result["capital_flow_audit"]["target_tickers"], ["A", "B", "C"])

    def test_preserves_mandatory_hedge_in_target_tickers(self):
        """TLT/VXX hedge targets must survive max-buys filtering (compliance gate)."""
        chairman = {
            "capital_flow_audit": {
                "target_tickers": ["META", "MNDY", "AMZN", "TLT"],
                "liquidated_tickers": [],
            },
            "portfolio_positions": [],
            "watchlist_positions": [
                _pos("META", "Accumulate Candidate", 30),
                _pos("MNDY", "Accumulate Candidate", 25),
                _pos("AMZN", "Accumulate Candidate", 20),
                _pos("VRT", "Accumulate Candidate", 15),
            ],
        }
        result = enforce_max_buys(chairman)
        targets = result["capital_flow_audit"]["target_tickers"]
        self.assertIn("TLT", targets)
        self.assertNotIn("VRT", targets)
        self.assertEqual(
            [p["final_verdict"] for p in result["watchlist_positions"] if p["symbol"] == "VRT"][0],
            "Pass",
        )

    def test_hedge_buy_verdict_not_demoted_by_cap(self):
        chairman = {
            "capital_flow_audit": {"target_tickers": ["A", "B", "C", "TLT"], "liquidated_tickers": []},
            "portfolio_positions": [],
            "watchlist_positions": [
                _pos("A", "Accumulate Candidate", 40),
                _pos("B", "Accumulate Candidate", 35),
                _pos("C", "Accumulate Candidate", 30),
                _pos("D", "Accumulate Candidate", 25),
                _pos("TLT", "Accumulate Candidate", 5),
            ],
        }
        result = enforce_max_buys(chairman)
        tlt = next(p for p in result["watchlist_positions"] if p["symbol"] == "TLT")
        self.assertEqual(tlt["final_verdict"], "Accumulate Candidate")
        self.assertIn("TLT", result["capital_flow_audit"]["target_tickers"])

    def test_portfolio_buys_demoted_to_hold(self):
        chairman = {
            "capital_flow_audit": {"target_tickers": [], "liquidated_tickers": []},
            "portfolio_positions": [
                _pos("NVDA", "Accumulate Candidate", 40),
                _pos("META", "Accumulate Candidate", 35),
                _pos("AMZN", "Accumulate Candidate", 30),
                _pos("GOOG", "Accumulate Candidate", 25),
            ],
            "watchlist_positions": [],
        }
        result = enforce_max_buys(chairman)
        demoted = [p for p in result["portfolio_positions"] if p["symbol"] == "GOOG"][0]
        self.assertEqual(demoted["final_verdict"], "Hold")


class TestWashSale(unittest.TestCase):
    REF = datetime(2026, 5, 29, tzinfo=ZoneInfo("America/Los_Angeles"))

    def test_blocks_recent_purchase(self):
        chairman = {
            "capital_flow_audit": {"liquidated_tickers": ["XYZ"], "target_tickers": []},
            "portfolio_positions": [_pos("XYZ", "Bearish (Liquidate)", synthesis="Exit.")],
            "watchlist_positions": [],
        }
        purchase_dates = {"XYZ": "05/20/2026"}
        result = enforce_wash_sale(chairman, purchase_dates, ref=self.REF)
        pos = result["portfolio_positions"][0]
        self.assertEqual(pos["final_verdict"], "HOLD")
        self.assertIn("Wash-Sale", pos["synthesis"])
        self.assertEqual(result["capital_flow_audit"]["liquidated_tickers"], [])

    def test_allows_old_purchase(self):
        chairman = {
            "capital_flow_audit": {"liquidated_tickers": ["XYZ"], "target_tickers": []},
            "portfolio_positions": [_pos("XYZ", "Bearish (Liquidate)")],
            "watchlist_positions": [],
        }
        purchase_dates = {"XYZ": "01/01/2026"}
        result = enforce_wash_sale(chairman, purchase_dates, ref=self.REF)
        self.assertEqual(result["portfolio_positions"][0]["final_verdict"], "Bearish (Liquidate)")
        self.assertEqual(result["capital_flow_audit"]["liquidated_tickers"], ["XYZ"])

    def test_unknown_date_not_blocked(self):
        self.assertFalse(_within_wash_sale_window("Unknown", self.REF))


class TestLiquidationCap(unittest.TestCase):
    def test_converts_oversized_sell_to_trim(self):
        chairman = {
            "capital_flow_audit": {"liquidated_tickers": ["BIG"], "target_tickers": ["NEW"]},
            "portfolio_positions": [_pos("BIG", "Bearish (Liquidate)")],
            "watchlist_positions": [],
        }
        holdings = {"BIG": 50_000.0}
        result = enforce_liquidation_cap(
            chairman,
            total_portfolio_value=100_000.0,
            portfolio_holdings=holdings,
        )
        pos = result["portfolio_positions"][0]
        self.assertEqual(pos["final_verdict"], "Reduce Exposure")
        self.assertIn("10% limit", pos["synthesis"])

    def test_deferred_trims_stay_trim_when_cap_exhausted(self):
        """CHAIR-1: board-mandated trims must not become HOLD when the 10% cap is full."""
        chairman = {
            "capital_flow_audit": {"liquidated_tickers": ["A", "B"], "target_tickers": []},
            "portfolio_positions": [_pos("A", "Bearish (Liquidate)"), _pos("B", "Reduce Exposure")],
            "watchlist_positions": [],
        }
        holdings = {"A": 12_000.0, "B": 5_000.0}
        result = enforce_liquidation_cap(
            chairman,
            total_portfolio_value=100_000.0,
            portfolio_holdings=holdings,
        )
        verdicts = {p["symbol"]: p["final_verdict"] for p in result["portfolio_positions"]}
        self.assertEqual(verdicts["A"], "Reduce Exposure")
        self.assertEqual(verdicts["B"], "Reduce Exposure")
        self.assertIn("B", result["capital_flow_audit"]["liquidated_tickers"])

    def test_chair1_prod_scenario_googl_first_then_avgo_asml(self):
        """Run 20260530_010432: GOOGL Bearish (Liquidate) + TSM Reduce Exposure consume cap; AVGO/ASML stay Reduce Exposure."""
        chairman = {
            "capital_flow_audit": {
                "liquidated_tickers": ["GOOGL", "TSM", "AVGO", "ASML"],
                "target_tickers": [],
            },
            "portfolio_positions": [
                _pos("GOOGL", "Bearish (Liquidate)"),
                _pos("TSM", "Reduce Exposure"),
                _pos("AVGO", "Reduce Exposure"),
                _pos("ASML", "Reduce Exposure"),
            ],
            "watchlist_positions": [],
        }
        holdings = {
            "GOOGL": 14_013.25,
            "TSM": 13_742.32,
            "AVGO": 32_113.83,
            "ASML": 12_500.50,
        }
        result = enforce_liquidation_cap(
            chairman,
            total_portfolio_value=149_267.96,
            portfolio_holdings=holdings,
        )
        verdicts = {p["symbol"]: p["final_verdict"] for p in result["portfolio_positions"]}
        self.assertEqual(verdicts["AVGO"], "Reduce Exposure")
        self.assertEqual(verdicts["ASML"], "Reduce Exposure")
        self.assertEqual(verdicts["TSM"], "Reduce Exposure")
        self.assertIn(verdicts["GOOGL"], ("Bearish (Liquidate)", "Reduce Exposure"))


class TestApplyChairmanGuardrails(unittest.TestCase):
    REF = datetime(2026, 5, 29, tzinfo=ZoneInfo("America/Los_Angeles"))

    def test_full_pipeline_order(self):
        chairman = {
            "capital_flow_audit": {
                "liquidated_tickers": ["RECENT", "OLD"],
                "target_tickers": ["W1", "W2", "W3", "W4"],
            },
            "portfolio_positions": [
                _pos("RECENT", "Reduce Exposure"),
                _pos("OLD", "Reduce Exposure"),
            ],
            "watchlist_positions": [
                _pos("W1", "Accumulate Candidate", 40),
                _pos("W2", "Accumulate Candidate", 30),
                _pos("W3", "Accumulate Candidate", 20),
                _pos("W4", "Accumulate Candidate", 10),
            ],
        }
        purchase_dates = {"RECENT": "05/25/2026", "OLD": "01/01/2026"}
        holdings = {"RECENT": 5_000.0, "OLD": 5_000.0}

        result = apply_chairman_guardrails(
            chairman,
            total_portfolio_value=100_000.0,
            portfolio_holdings=holdings,
            purchase_dates=purchase_dates,
            ref=self.REF,
        )

        recent = next(p for p in result["portfolio_positions"] if p["symbol"] == "RECENT")
        self.assertEqual(recent["final_verdict"], "HOLD")
        self.assertIn("Wash-Sale", recent["synthesis"])

        demoted = next(p for p in result["watchlist_positions"] if p["symbol"] == "W4")
        self.assertEqual(demoted["final_verdict"], "Pass")

        buy_count = sum(
            1 for p in result["watchlist_positions"]
            if p["final_verdict"] in ("Accumulate Candidate", "High Conviction (Overweight)")
        )
        self.assertLessEqual(buy_count, MAX_DAILY_BUYS)


if __name__ == "__main__":
    unittest.main()
