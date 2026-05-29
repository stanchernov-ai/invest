"""Tests for human-confirmed QA review UI logic."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from src.qa.human_review import (
    build_review_url,
    handle_review_http,
    render_review_page,
    save_human_review,
    validate_access_token,
)


class TestHumanReviewAuth(unittest.TestCase):
    def test_validate_token(self):
        with patch.dict(os.environ, {"QA_REVIEW_TOKEN": "secret-token"}):
            self.assertTrue(validate_access_token("secret-token"))
            self.assertFalse(validate_access_token("wrong"))

    def test_build_review_url(self):
        with patch.dict(os.environ, {
            "QA_REVIEW_BASE_URL": "https://example.azurewebsites.net/api",
            "QA_REVIEW_TOKEN": "abc",
        }):
            url = build_review_url("20260529_120000")
            self.assertIn("run_id=20260529_120000", url)
            self.assertIn("token=abc", url)


class TestHumanReviewHandler(unittest.TestCase):
    def test_get_rejects_bad_token(self):
        status, body, _ = handle_review_http("GET", {"run_id": "20260529_120000", "token": "bad"})
        self.assertEqual(status, 403)

    @patch("src.qa.human_review.load_review_context")
    def test_get_renders_form(self, mock_load):
        mock_load.return_value = {
            "run_id": "20260529_120000",
            "agents": [{
                "agent_key": "post_mortem_qa",
                "agent_role": "Post Mortem QA Auditor",
                "is_compliant": True,
                "critical_findings": 0,
                "warning_findings": 0,
            }],
        }
        with patch.dict(os.environ, {"QA_REVIEW_TOKEN": "ok"}):
            status, body, _ = handle_review_http("GET", {"run_id": "20260529_120000", "token": "ok"})
        self.assertEqual(status, 200)
        self.assertIn("Post Mortem QA Auditor", body)
        self.assertIn("Save review", body)


class TestHumanReviewPersist(unittest.TestCase):
    @patch("src.qa.human_review._persist_local_ecosystem")
    @patch("src.qa.human_review._update_ledger")
    @patch("src.storage_client.save_state_blob")
    def test_save_human_review(self, mock_save, mock_ledger, mock_local):
        record = save_human_review("20260529_120000", [
            {"agent_key": "post_mortem_qa", "agent_role": "Post Mortem QA Auditor",
             "human_confirmed": True, "human_notes": "Correct call."},
        ])
        self.assertEqual(record["run_id"], "20260529_120000")
        self.assertEqual(record["reviews"][0]["human_confirmed"], True)
        mock_save.assert_called_once()


if __name__ == "__main__":
    unittest.main()
