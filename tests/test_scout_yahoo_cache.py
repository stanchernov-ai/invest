"""Yahoo trending cache — at most one HTML scrape per calendar day."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from src import scout


class YahooTrendingCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = os.path.join(self.tmp.name, "data")
        os.makedirs(self.data_dir, exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    @patch("src.scout._cache_date_key", return_value="20260530")
    @patch("src.scout.scrape_yahoo_trending", return_value=["PLTR", "NVDA"])
    def test_fetch_scrapes_once_then_uses_cache(self, mock_scrape, _mock_date):
        first = scout._fetch_trending_symbol_list(self.data_dir)
        second = scout._fetch_trending_symbol_list(self.data_dir)
        self.assertEqual(first, ["PLTR", "NVDA"])
        self.assertEqual(second, first)
        mock_scrape.assert_called_once()

    @patch("src.scout._cache_date_key", return_value="20260530")
    @patch("src.scout.scrape_yahoo_trending", return_value=["PLTR"])
    def test_force_refresh_bypasses_cache(self, mock_scrape, _mock_date):
        scout._fetch_trending_symbol_list(self.data_dir)
        scout._fetch_trending_symbol_list(self.data_dir, force_refresh=True)
        self.assertEqual(mock_scrape.call_count, 2)

    @patch("src.scout._cache_date_key", return_value="20260531")
    @patch("src.scout.scrape_yahoo_trending", return_value=["MSFT"])
    def test_stale_cache_date_triggers_refresh(self, mock_scrape, mock_date):
        cache_path = scout._yahoo_cache_path(self.data_dir)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({"date": "20260530", "symbols": ["OLD"], "source": "yahoo"}, f)
        symbols = scout._fetch_trending_symbol_list(self.data_dir)
        self.assertEqual(symbols, ["MSFT"])
        mock_scrape.assert_called_once()

    @patch("src.scout.YAHOO_SCRAPE_ENABLED", False)
    @patch("src.scout._fetch_trending_from_fmp", return_value=["AAPL"])
    @patch("src.scout.scrape_yahoo_trending")
    def test_disabled_scrape_uses_fmp_without_yahoo(self, mock_scrape, _mock_fmp):
        symbols = scout._fetch_trending_symbol_list(self.data_dir, force_refresh=True)
        self.assertEqual(symbols, ["AAPL"])
        mock_scrape.assert_not_called()


if __name__ == "__main__":
    unittest.main()
