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
                _pos("A", "Buy", 30),
                _pos("B", "Strong Buy", 25),
                _pos("C", "Buy", 20),
                _pos("D", "Buy", 15),
            ],
        }
        result = enforce_max_buys(chairman)
        verdicts = {p["symbol"]: p["final_verdict"] for p in result["watchlist_positions"]}
        self.assertEqual(verdicts["A"], "Buy")
        self.assertEqual(verdicts["B"], "Strong Buy")
        self.assertEqual(verdicts["C"], "Buy")
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
                _pos("META", "Buy", 30),
                _pos("MNDY", "Buy", 25),
                _pos("AMZN", "Buy", 20),
                _pos("VRT", "Buy", 15),
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
                _pos("A", "Buy", 40),
                _pos("B", "Buy", 35),
                _pos("C", "Buy", 30),
                _pos("D", "Buy", 25),
                _pos("TLT", "Buy", 5),
            ],
        }
        result = enforce_max_buys(chairman)
        tlt = next(p for p in result["watchlist_positions"] if p["symbol"] == "TLT")
        self.assertEqual(tlt["final_verdict"], "Buy")
        self.assertIn("TLT", result["capital_flow_audit"]["target_tickers"])

    def test_portfolio_buys_demoted_to_hold(self):
        chairman = {
            "capital_flow_audit": {"target_tickers": [], "liquidated_tickers": []},
            "portfolio_positions": [
                _pos("NVDA", "Buy", 40),
                _pos("META", "Buy", 35),
                _pos("AMZN", "Buy", 30),
                _pos("GOOG", "Buy", 25),
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
            "portfolio_positions": [_pos("XYZ", "Sell", synthesis="Exit.")],
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
            "portfolio_positions": [_pos("XYZ", "Sell")],
            "watchlist_positions": [],
        }
        purchase_dates = {"XYZ": "01/01/2026"}
        result = enforce_wash_sale(chairman, purchase_dates, ref=self.REF)
        self.assertEqual(result["portfolio_positions"][0]["final_verdict"], "Sell")
        self.assertEqual(result["capital_flow_audit"]["liquidated_tickers"], ["XYZ"])

    def test_unknown_date_not_blocked(self):
        self.assertFalse(_within_wash_sale_window("Unknown", self.REF))


class TestLiquidationCap(unittest.TestCase):
    def test_converts_oversized_sell_to_trim(self):
        chairman = {
            "capital_flow_audit": {"liquidated_tickers": ["BIG"], "target_tickers": ["NEW"]},
            "portfolio_positions": [_pos("BIG", "Sell")],
            "watchlist_positions": [],
        }
        holdings = {"BIG": 50_000.0}
        result = enforce_liquidation_cap(
            chairman,
            total_portfolio_value=100_000.0,
            portfolio_holdings=holdings,
        )
        pos = result["portfolio_positions"][0]
        self.assertEqual(pos["final_verdict"], "TRIM")
        self.assertIn("10% limit", pos["synthesis"])

    def test_cancels_excess_liquidations(self):
        chairman = {
            "capital_flow_audit": {"liquidated_tickers": ["A", "B"], "target_tickers": []},
            "portfolio_positions": [_pos("A", "Sell"), _pos("B", "Trim")],
            "watchlist_positions": [],
        }
        holdings = {"A": 12_000.0, "B": 5_000.0}
        result = enforce_liquidation_cap(
            chairman,
            total_portfolio_value=100_000.0,
            portfolio_holdings=holdings,
        )
        verdicts = {p["symbol"]: p["final_verdict"] for p in result["portfolio_positions"]}
        self.assertEqual(verdicts["A"], "TRIM")
        self.assertEqual(verdicts["B"], "HOLD")


class TestApplyChairmanGuardrails(unittest.TestCase):
    REF = datetime(2026, 5, 29, tzinfo=ZoneInfo("America/Los_Angeles"))

    def test_full_pipeline_order(self):
        chairman = {
            "capital_flow_audit": {
                "liquidated_tickers": ["RECENT", "OLD"],
                "target_tickers": ["W1", "W2", "W3", "W4"],
            },
            "portfolio_positions": [
                _pos("RECENT", "Trim"),
                _pos("OLD", "Trim"),
            ],
            "watchlist_positions": [
                _pos("W1", "Buy", 40),
                _pos("W2", "Buy", 30),
                _pos("W3", "Buy", 20),
                _pos("W4", "Buy", 10),
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
            if p["final_verdict"] in ("Buy", "Strong Buy")
        )
        self.assertLessEqual(buy_count, MAX_DAILY_BUYS)


if __name__ == "__main__":
    unittest.main()
