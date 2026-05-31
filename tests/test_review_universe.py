"""Tests for review universe (Mag7 + manual + Yahoo merge)."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from src.data.review_universe import (
    MAGNIFICENT_SEVEN,
    build_review_universe,
    is_owned,
    load_manual_watchlist,
)


class ReviewUniverseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = os.path.join(self.tmp.name, "data")
        os.makedirs(self.data_dir, exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_mag7_included_when_not_owned(self):
        with patch("src.data.review_universe.scout.build_yahoo_discovery", return_value={}):
            universe = build_review_universe(set(), data_dir=self.data_dir)
        for sym in MAGNIFICENT_SEVEN:
            self.assertIn(sym, universe)
            self.assertEqual(universe[sym]["source"], "mag7")

    def test_mag7_excluded_when_owned(self):
        with patch("src.data.review_universe.scout.build_yahoo_discovery", return_value={}):
            universe = build_review_universe({"NVDA", "AAPL"}, data_dir=self.data_dir)
        self.assertNotIn("NVDA", universe)
        self.assertNotIn("AAPL", universe)
        self.assertIn("MSFT", universe)

    def test_goog_ownership_excludes_googl_mag7(self):
        self.assertTrue(is_owned("GOOGL", {"GOOG"}))
        with patch("src.data.review_universe.scout.build_yahoo_discovery", return_value={}):
            universe = build_review_universe({"GOOG"}, data_dir=self.data_dir)
        self.assertNotIn("GOOGL", universe)

    def test_manual_watchlist_merged(self):
        manual_path = os.path.join(self.data_dir, "manual_watchlist.json")
        with open(manual_path, "w", encoding="utf-8") as f:
            json.dump({"PLTR": {"source": "manual", "price": 0.0}}, f)
        with patch("src.data.review_universe.scout.build_yahoo_discovery", return_value={}):
            universe = build_review_universe(set(), data_dir=self.data_dir)
        self.assertIn("PLTR", universe)
        self.assertEqual(universe["PLTR"]["source"], "manual")

    def test_yahoo_merged_when_enabled(self):
        with patch(
            "src.data.review_universe.scout.build_yahoo_discovery",
            return_value={"PLTR": {"source": "yahoo", "price": 0.0}},
        ):
            universe = build_review_universe(set(), data_dir=self.data_dir)
        self.assertIn("PLTR", universe)
        self.assertEqual(universe["PLTR"]["source"], "yahoo")

    def test_pass_cooldown_suppresses_yahoo_not_mag7(self):
        verdicts = {
            "META": [{"verdict": "Pass", "date": "20990101", "unanimous_pass": False}],
        }
        with patch(
            "src.data.review_universe.scout.build_yahoo_discovery",
            return_value={"PLTR": {"source": "yahoo", "price": 0.0}},
        ) as mock_yahoo:
            universe = build_review_universe(
                set(),
                verdicts_history=verdicts,
                data_dir=self.data_dir,
            )
            mock_yahoo.assert_called_once()
            cooldown_passed = mock_yahoo.call_args[0][1]
            self.assertIn("META", cooldown_passed)
        self.assertIn("META", universe)
        self.assertEqual(universe["META"]["source"], "mag7")
        self.assertIn("PLTR", universe)

    def test_include_yahoo_false_skips_discovery(self):
        with patch("src.data.review_universe.scout.build_yahoo_discovery") as mock_yahoo:
            universe = build_review_universe(
                set(),
                include_yahoo=False,
                data_dir=self.data_dir,
            )
            mock_yahoo.assert_not_called()
        self.assertEqual(len(universe), len(MAGNIFICENT_SEVEN))

    def test_load_manual_watchlist_empty_when_missing(self):
        self.assertEqual(load_manual_watchlist(self.data_dir), {})


if __name__ == "__main__":
    unittest.main()
