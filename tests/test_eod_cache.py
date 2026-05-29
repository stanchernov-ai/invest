"""Tests for shared EOD cache and momentum derivation."""
import unittest

from src.data.fmp_client import (
    compute_momentum_from_series,
    eod_cache_lookup,
    slice_price_series,
)
from src.data.news_client import _format_published_date


class TestEodCache(unittest.TestCase):
    def test_momentum_from_synthetic_series(self):
        series = {
            "2023-01-01": 100.0,
            "2025-12-01": 90.0,
            "2026-02-01": 110.0,
        }
        trend, cagr = compute_momentum_from_series(series)
        self.assertNotEqual(trend, "N/A")
        self.assertNotEqual(cagr, "N/A")

    def test_slice_window(self):
        series = {"2025-01-01": 1.0, "2025-06-01": 2.0, "2026-01-01": 3.0}
        sliced = slice_price_series(series, "2025-06-01", "2026-01-01")
        self.assertEqual(list(sliced.keys()), ["2025-06-01", "2026-01-01"])

    def test_cache_lookup_aliases_dot_ticker(self):
        cache = {"BRK-B": {"2026-01-01": 100.0}}
        cache["BRK.B"] = cache["BRK-B"]
        self.assertEqual(eod_cache_lookup(cache, "BRK.B"), {"2026-01-01": 100.0})


class TestNewsDates(unittest.TestCase):
    def test_iso_datetime(self):
        self.assertEqual(_format_published_date("2026-05-28 14:30:00"), "2026-05-28")

    def test_empty(self):
        self.assertEqual(_format_published_date(None), "")


if __name__ == "__main__":
    unittest.main()
