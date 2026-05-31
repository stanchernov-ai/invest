import json
import os
import tempfile
import unittest
from unittest.mock import patch

from src import storage_client


class RunStatusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = os.path.join(self.tmp.name, "data")
        os.makedirs(self.data_dir, exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    @patch.object(storage_client, "get_blob_service_client", return_value=None)
    def test_per_run_status_survives_pointer_overwrite(self, _mock_client):
        with patch.object(storage_client, "DATA_DIR", self.data_dir):
            storage_client.begin_run_status("20260529_115549", "2026-05-29T11:55:49-07:00")
            storage_client.mark_phase(
                "20260529_115549",
                "prepare",
                "success",
                finished_at="2026-05-29T11:58:00-07:00",
            )

            storage_client.begin_run_status("20260529_120049", "2026-05-29T12:00:49-07:00")

            older = storage_client.load_run_status_for_run("20260529_115549")
            current = storage_client.load_run_status()

        self.assertEqual(older["run_id"], "20260529_115549")
        self.assertEqual(older["prepare"]["status"], "success")
        self.assertEqual(current["run_id"], "20260529_120049")

    @patch.object(storage_client, "get_blob_service_client", return_value=None)
    def test_is_run_in_flight(self, _mock_client):
        with patch.object(storage_client, "DATA_DIR", self.data_dir):
            self.assertIsNone(storage_client.is_run_in_flight())
            storage_client.save_run_status(
                {"run_id": "20260529_120049", "status": "running", "phase": "debate"}
            )
            in_flight = storage_client.is_run_in_flight()
            self.assertEqual(in_flight["run_id"], "20260529_120049")
            self.assertEqual(in_flight["phase"], "debate")

    @patch.object(storage_client, "get_blob_service_client", return_value=None)
    def test_current_pointer_writes_both_blobs(self, _mock_client):
        with patch.object(storage_client, "DATA_DIR", self.data_dir):
            storage_client.save_run_status({"run_id": "20260529_120049", "status": "success"})

        for name in (
            storage_client._run_status_blob("stan"),
            storage_client._run_status_current_blob("stan"),
            storage_client._run_status_blob_for_run("20260529_120049", "stan"),
        ):
            path = os.path.join(self.data_dir, name)
            self.assertTrue(os.path.exists(path), name)
            with open(path, encoding="utf-8") as f:
                payload = json.load(f)
            self.assertEqual(payload["run_id"], "20260529_120049")

    @patch.object(storage_client, "get_blob_service_client", return_value=None)
    def test_mark_phase_queued_keeps_overall_running(self, _mock_client):
        with patch.object(storage_client, "DATA_DIR", self.data_dir):
            storage_client.begin_run_status("20260529_120049", "2026-05-29T12:00:49-07:00")
            storage_client.mark_phase(
                "20260529_120049",
                "prepare",
                "success",
                finished_at="2026-05-29T12:05:00-07:00",
            )
            status = storage_client.mark_phase(
                "20260529_120049",
                "debate",
                "queued",
                started_at="2026-05-29T12:05:01-07:00",
            )

        self.assertEqual(status["status"], "running")
        self.assertEqual(status["phase"], "debate")
        self.assertEqual(status["debate"]["status"], "queued")

    @patch.object(storage_client, "get_blob_service_client", return_value=None)
    def test_abort_run_marks_terminal(self, _mock_client):
        with patch.object(storage_client, "DATA_DIR", self.data_dir):
            storage_client.begin_run_status("20260529_120049", "2026-05-29T12:00:49-07:00")
            storage_client.mark_phase(
                "20260529_120049",
                "prepare",
                "success",
                finished_at="2026-05-29T12:05:00-07:00",
            )
            storage_client.mark_phase(
                "20260529_120049",
                "debate",
                "queued",
                started_at="2026-05-29T12:05:01-07:00",
            )
            status = storage_client.abort_run(
                "20260529_120049",
                reason="stale run",
                finished_at="2026-05-29T12:50:00-07:00",
            )

        self.assertEqual(status["status"], "aborted")
        self.assertEqual(status["debate"]["status"], "aborted")
        self.assertIsNone(storage_client.is_run_in_flight())

    @patch.object(storage_client, "get_blob_service_client", return_value=None)
    @patch("src.config.settings.now_local")
    def test_abort_stale_run_if_needed(self, mock_now, _mock_client):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("America/Los_Angeles")
        mock_now.return_value = datetime(2026, 5, 29, 12, 50, 0, tzinfo=tz)
        with patch.object(storage_client, "DATA_DIR", self.data_dir):
            storage_client.begin_run_status("20260529_120049", "2026-05-29T12:45:00-07:00")
            self.assertIsNone(storage_client.abort_stale_run_if_needed(max_age_seconds=600))

            storage_client.begin_run_status("20260529_110000", "2026-05-29T11:00:00-07:00")
            aborted = storage_client.abort_stale_run_if_needed(max_age_seconds=600)

        self.assertEqual(aborted["run_id"], "20260529_110000")
        self.assertEqual(aborted["status"], "aborted")
        self.assertIn("stale run", aborted["error"])


if __name__ == "__main__":
    unittest.main()
