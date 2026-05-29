"""Smoke tests for FMP field mapping (requires FMP_API_KEY in .env)."""
import asyncio
import os
import unittest

from dotenv import load_dotenv

load_dotenv()


@unittest.skipUnless(os.getenv("FMP_API_KEY"), "FMP_API_KEY not set")
class TestFmpAdvancedMetrics(unittest.TestCase):
    def test_aapl_consensus_and_earnings_populated(self):
        import aiohttp
        from src.data.fmp_client import get_fmp_advanced_metrics

        async def _run():
            async with aiohttp.ClientSession() as session:
                return await get_fmp_advanced_metrics(
                    "AAPL", os.environ["FMP_API_KEY"], session, {}
                )

        m = asyncio.run(_run())
        self.assertNotEqual(m["consensus"], "N/A")
        self.assertNotEqual(m["next_earnings"], "Unknown")
        self.assertNotEqual(m["fwd_pe"], "N/A")
        self.assertIn("Buy", str(m["consensus"]))

    def test_spy_etf_path(self):
        import aiohttp
        from src.data.fmp_client import get_fmp_advanced_metrics

        async def _run():
            async with aiohttp.ClientSession() as session:
                return await get_fmp_advanced_metrics(
                    "SPY", os.environ["FMP_API_KEY"], session, {}
                )

        m = asyncio.run(_run())
        self.assertGreater(float(m["current_price"]), 0)
        self.assertEqual(m["consensus"], "N/A")


if __name__ == "__main__":
    unittest.main()
