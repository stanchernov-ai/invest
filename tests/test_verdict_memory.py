import json
import os
import tempfile
import unittest
from unittest.mock import patch

from src import scout
from src import verdict_memory


class VerdictMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = os.path.join(self.tmp.name, "data")
        os.makedirs(self.data_dir, exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    @patch("src.verdict_memory.save_board_verdicts")
    @patch("src.verdict_memory.load_board_verdicts")
    def test_persist_pass_only_when_approved(self, mock_load, mock_save):
        mock_load.return_value = {}
        chairman = {
            "watchlist_positions": [
                {"symbol": "PLTR", "final_verdict": "Pass"},
                {"symbol": "NVDA", "final_verdict": "Buy"},
            ]
        }

        count = verdict_memory.persist_chairman_watchlist_passes(
            chairman, "20260529_120000", is_approved=True
        )
        self.assertEqual(count, 1)
        saved = mock_save.call_args[0][0]
        self.assertEqual(saved["PLTR"][0]["verdict"], "Pass")
        self.assertEqual(saved["PLTR"][0]["date"], "20260529")
        self.assertNotIn("NVDA", saved)

    @patch("src.verdict_memory.save_board_verdicts")
    @patch("src.verdict_memory.load_board_verdicts")
    def test_skips_when_not_approved(self, mock_load, mock_save):
        chairman = {
            "watchlist_positions": [{"symbol": "PLTR", "final_verdict": "Pass"}]
        }
        count = verdict_memory.persist_chairman_watchlist_passes(
            chairman, "20260529_120000", is_approved=False
        )
        self.assertEqual(count, 0)
        mock_save.assert_not_called()
        mock_load.assert_not_called()

    @patch("src.verdict_memory.save_board_verdicts")
    @patch("src.verdict_memory.load_board_verdicts")
    def test_implicit_pass_from_watchlist_symbols(self, mock_load, mock_save):
        mock_load.return_value = {}
        chairman = {
            "watchlist_positions": [
                {"symbol": "MNDY", "final_verdict": "Buy"},
                {"symbol": "LLY", "final_verdict": "Strong Buy"},
            ]
        }
        count = verdict_memory.persist_chairman_watchlist_passes(
            chairman,
            "20260529_120049",
            is_approved=True,
            watchlist_symbols=["MNDY", "LLY", "META", "PLTR"],
        )
        self.assertEqual(count, 2)
        saved = mock_save.call_args[0][0]
        self.assertIn("META", saved)
        self.assertIn("PLTR", saved)
        self.assertNotIn("MNDY", saved)
        self.assertNotIn("LLY", saved)
        self.assertEqual(saved["META"][0]["date"], "20260529")

    @patch("src.verdict_memory.get_blob_service_client", return_value=None)
    def test_save_and_load_round_trip(self, _mock_client):
        with patch.object(verdict_memory, "DATA_DIR", self.data_dir):
            verdict_memory.save_board_verdicts({"AAPL": [{"verdict": "Pass", "date": "20260529"}]})
            loaded = verdict_memory.load_board_verdicts()
        self.assertIn("AAPL", loaded)


class ScoutOwnedTickerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = os.path.join(self.tmp.name, "data")
        os.makedirs(self.data_dir, exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    @patch("src.scout.scrape_yahoo_trending", return_value=["NVDA", "PLTR", "MSFT"])
    def test_excludes_owned_tickers(self, _mock_trending):
        with patch.object(scout, "DATA_DIR", self.data_dir):
            scout.run_scout_pipeline(owned_tickers={"NVDA", "MSFT"})
            with open(os.path.join(self.data_dir, "daily_target_list.json"), encoding="utf-8") as f:
                watchlist = json.load(f)
        self.assertIn("PLTR", watchlist)
        self.assertNotIn("NVDA", watchlist)
        self.assertNotIn("MSFT", watchlist)

    @patch("src.scout.scrape_yahoo_trending", return_value=["PLTR"])
    def test_excludes_pass_cooldown(self, _mock_trending):
        verdicts_path = os.path.join(self.data_dir, "board_verdicts.json")
        with open(verdicts_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "PLTR": [
                        {"verdict": "Pass", "date": "20990101", "unanimous_pass": False}
                    ]
                },
                f,
            )
        with patch.object(scout, "DATA_DIR", self.data_dir):
            scout.run_scout_pipeline(owned_tickers=set())
            with open(os.path.join(self.data_dir, "daily_target_list.json"), encoding="utf-8") as f:
                watchlist = json.load(f)
        self.assertNotIn("PLTR", watchlist)


if __name__ == "__main__":
    unittest.main()
