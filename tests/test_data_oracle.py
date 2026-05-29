import unittest
from unittest.mock import AsyncMock, patch

from src.core.data_oracle import build_price_feed, validate_price_feed
from src.core.schemas import BoardroomState
from src.core.engine import StateMachineOrchestrator


def _minimal_state(**overrides) -> BoardroomState:
    base = {
        "base_data_prompt": "=== CURRENT PORTFOLIO ===\n* AAPL: Price: $100",
        "live_mandate": "test mandate",
        "heavy_tickers": [],
    }
    base.update(overrides)
    return BoardroomState(**base)


class TestValidatePriceFeed(unittest.TestCase):
    def test_passes_when_all_prices_positive(self):
        result = validate_price_feed({"AAPL": 150.0, "MSFT": 400.0})
        self.assertTrue(result["is_valid"])
        self.assertIn("2", result["reason"])

    def test_fails_on_zero_price(self):
        result = validate_price_feed({"AAPL": 150.0, "BAD": 0.0})
        self.assertFalse(result["is_valid"])
        self.assertIn("BAD", result["reason"])

    def test_fails_on_empty_feed(self):
        result = validate_price_feed({})
        self.assertFalse(result["is_valid"])


class TestBuildPriceFeed(unittest.TestCase):
    def test_uses_advanced_price_when_available(self):
        feed = build_price_feed(
            master_ledger={"AAPL": {"Total": 1000.0, "Shares": 10.0}},
            watchlist_data={},
            advanced_data={"AAPL": {"current_price": 175.5}},
        )
        self.assertEqual(feed["AAPL"], 175.5)

    def test_falls_back_to_ledger_math(self):
        feed = build_price_feed(
            master_ledger={"AAPL": {"Total": 1000.0, "Shares": 10.0}},
            watchlist_data={},
            advanced_data={},
        )
        self.assertEqual(feed["AAPL"], 100.0)

    def test_includes_watchlist_prices(self):
        feed = build_price_feed(
            master_ledger={},
            watchlist_data={"NVDA": {"price": 900.0}},
            advanced_data={},
        )
        self.assertEqual(feed["NVDA"], 900.0)


class TestDataOracleDedup(unittest.IsolatedAsyncioTestCase):
    async def test_skips_check_when_prepare_validated(self):
        state = _minimal_state(oracle_valid=True, oracle_reason="All prices > $0.")
        orch = StateMachineOrchestrator(state)

        with patch.object(orch, "execute_data_oracle", new_callable=AsyncMock) as mock_oracle:
            await orch._ensure_oracle_cleared()

        mock_oracle.assert_not_called()
        self.assertTrue(orch.oracle_valid)

    async def test_runs_deterministic_oracle_when_no_prepare_result(self):
        state = _minimal_state(oracle_prices={"AAPL": 100.0})
        orch = StateMachineOrchestrator(state)

        await orch._ensure_oracle_cleared()

        self.assertTrue(orch.oracle_valid)

    async def test_aborts_without_rerun_when_prepare_rejected(self):
        state = _minimal_state(oracle_valid=False, oracle_reason="Zero price on XYZ.")
        orch = StateMachineOrchestrator(state)

        with patch.object(orch, "execute_data_oracle", new_callable=AsyncMock) as mock_oracle:
            await orch._ensure_oracle_cleared()

        mock_oracle.assert_not_called()
        self.assertFalse(orch.oracle_valid)

    async def test_legacy_path_fails_on_zero_prices(self):
        state = _minimal_state(oracle_prices={"AAPL": 0.0})
        orch = StateMachineOrchestrator(state)

        await orch.execute_data_oracle()

        self.assertFalse(orch.oracle_valid)
        self.assertIn("AAPL", orch.oracle_reason)


if __name__ == "__main__":
    unittest.main()
