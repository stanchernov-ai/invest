import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch


class RunPhaseGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = os.path.join(self.tmp.name, "data")
        os.makedirs(self.data_dir, exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    @patch("src.storage_client.get_blob_service_client", return_value=None)
    def test_run_phase_marks_failed_on_exception(self, _mock_client):
        import function_app
        from src import storage_client

        async def boom():
            raise RuntimeError("phase exploded")

        with patch.object(storage_client, "DATA_DIR", self.data_dir):
            storage_client.begin_run_status("20260529_120049", "2026-05-29T12:00:49-07:00")
            ok = function_app._run_phase(boom(), "20260529_120049", "debate")
            status = storage_client.load_run_status_for_run("20260529_120049")

        self.assertFalse(ok)
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["debate"]["status"], "failed")
        self.assertIn("phase exploded", status["debate"]["error"])

    def test_dummy(self):
        pass


if __name__ == "__main__":
    unittest.main()
