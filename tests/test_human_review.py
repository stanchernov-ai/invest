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
            "QA_REVIEW_BASE_URL": "https://example.azurewebsites.net",
            "QA_REVIEW_TOKEN": "abc",
        }):
            url = build_review_url("20260529_120000")
            self.assertEqual(
                url,
                "https://example.azurewebsites.net/api/qa-review?run_id=20260529_120000&token=abc",
            )

    def test_build_review_url_encodes_special_chars(self):
        token = "abc%def+ghi&jkl"
        with patch.dict(os.environ, {
            "QA_REVIEW_BASE_URL": "https://example.azurewebsites.net",
            "QA_REVIEW_TOKEN": token,
        }):
            url = build_review_url("20260529_120000")
            self.assertIn("run_id=20260529_120000", url)
            self.assertIn("token=abc%25def%2Bghi%26jkl", url)
            self.assertNotIn(f"token={token}", url)


class TestHumanReviewHandler(unittest.TestCase):
    def test_get_rejects_bad_token(self):
        status, body, _ = handle_review_http("GET", {"run_id": "20260529_120000", "token": "bad"})
        self.assertEqual(status, 403)

    @patch("src.qa.human_review._load_full_review_context")
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
            "triage": {"run_id": "20260529_120000", "candidates": []},
        }
        with patch.dict(os.environ, {"QA_REVIEW_TOKEN": "ok"}):
            status, body, _ = handle_review_http("GET", {"run_id": "20260529_120000", "token": "ok"})
        self.assertEqual(status, 200)
        self.assertIn("Post Mortem QA Auditor", body)
        self.assertIn("Save review &amp; triage", body)
        self.assertIn("QA Backlog", body)


class TestHumanReviewPersist(unittest.TestCase):
    @patch("src.qa.human_review._load_full_review_context")
    @patch("src.qa.candidate_triage.save_candidate_triage")
    @patch("src.qa.candidate_triage.parse_triage_from_form")
    @patch("src.qa.candidate_triage.format_sync_hint")
    @patch("src.qa.human_review._refresh_retrospective_after_review")
    @patch("src.qa.human_review._persist_local_ecosystem")
    @patch("src.qa.human_review._update_ledger")
    @patch("src.storage_client.save_state_blob")
    def test_save_human_review(
        self, mock_save, mock_ledger, mock_local, mock_retro,
        mock_promoted_md, mock_parse_triage, mock_save_triage, mock_load_ctx,
    ):
        mock_parse_triage.return_value = []
        mock_promoted_md.return_value = "sync hint"
        mock_load_ctx.return_value = {
            "run_id": "20260529_120000",
            "agents": [],
            "triage": {"run_id": "20260529_120000", "candidates": []},
        }
        mock_save_triage.return_value = {"summary": "1 fix code · 0 fix agent · 0 discarded · 0 pending"}
        record = save_human_review("20260529_120000", [
            {"agent_key": "post_mortem_qa", "agent_role": "Post Mortem QA Auditor",
             "human_confirmed": True, "human_notes": "Correct call."},
        ])
        self.assertEqual(record["run_id"], "20260529_120000")
        self.assertEqual(record["reviews"][0]["human_confirmed"], True)
        mock_save.assert_called_once()
        mock_retro.assert_called_once_with("20260529_120000")


if __name__ == "__main__":
    unittest.main()
