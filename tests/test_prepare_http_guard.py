import json
import unittest
from unittest.mock import MagicMock, patch


class PrepareHttpGuardTests(unittest.TestCase):
    @patch("src.storage_client.abort_stale_run_if_needed", return_value=None)
    @patch("function_app._run_phase", return_value=True)
    @patch("function_app._new_run_id", return_value="20260529_130000")
    @patch("src.storage_client.is_run_in_flight")
    def test_rejects_when_run_in_flight(self, mock_in_flight, _mock_run_id, _mock_phase, _mock_abort):
        import function_app

        mock_in_flight.return_value = {
            "run_id": "20260529_120049",
            "phase": "debate",
            "status": "running",
        }
        req = MagicMock()
        debate_out = MagicMock()

        resp = function_app.boardroom_prepare_http(req, debate_out)

        self.assertEqual(resp.status_code, 409)
        body = json.loads(resp.get_body())
        self.assertEqual(body["run_id"], "20260529_120049")
        self.assertEqual(body["phase"], "debate")
        debate_out.set.assert_not_called()
        _mock_phase.assert_not_called()

    @patch("function_app._enqueue_phase")
    @patch("src.jobs.prepare.run_prepare")
    @patch("function_app._run_phase", return_value=True)
    @patch("function_app._new_run_id", return_value="20260529_130000")
    @patch("src.storage_client.is_run_in_flight", return_value=None)
    @patch("src.storage_client.abort_stale_run_if_needed", return_value=None)
    def test_allows_when_no_run_in_flight(
        self, _mock_abort, _mock_in_flight, _mock_run_id, mock_phase, _mock_prepare, mock_enqueue
    ):
        import function_app

        req = MagicMock()
        debate_out = MagicMock()

        resp = function_app.boardroom_prepare_http(req, debate_out)

        self.assertEqual(resp.status_code, 202)
        mock_phase.assert_called_once()
        debate_out.set.assert_called_once_with("20260529_130000")
        mock_enqueue.assert_called_once_with("20260529_130000", "debate")


if __name__ == "__main__":
    unittest.main()
