"""Tests for post_job_audit oversight builder."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.qa.post_job_audit import (
    append_oversight_to_ecosystem,
    build_post_job_oversight,
    oversight_blob_name,
    save_post_job_oversight_blob,
)


class TestPostJobAudit(unittest.TestCase):
    def test_build_oversight_blocked_on_many_criticals(self):
        telemetry = {
            "AGENT_ACTIVITY": {
                    "franklin": {"invocations": 2, "total_tokens": 1000, "model": "gemini-2.5-pro",
                            "prompt_tokens": 800, "output_tokens": 200, "thinking_tokens": 0, "errors": 0},
            },
            "chairman_bypassed": True,
            "allocation_source": "vote_engine",
            "compliance_source": "python_only",
        }
        qa_reports = [
            {"agent_role": "A", "is_compliant": False, "findings": [{"severity": "CRITICAL"}]},
            {"agent_role": "B", "is_compliant": False, "findings": [{"severity": "CRITICAL"}]},
            {"agent_role": "C", "is_compliant": False, "findings": [{"severity": "CRITICAL"}]},
        ]
        bundle = build_post_job_oversight("20260529_191611", telemetry, qa_reports)
        self.assertEqual(bundle["metrics"]["verdict"], "BLOCKED")
        self.assertEqual(bundle["metrics"]["qa_critical_count"], 3)
        self.assertEqual(oversight_blob_name("20260529_191611"), "post_job_oversight_20260529_191611.json")

    def test_append_idempotent(self):
        telemetry = {"AGENT_ACTIVITY": {}, "chairman_bypassed": True}
        bundle = build_post_job_oversight("20260529_191611", telemetry, [])
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "ecosystem_state.json"
            with patch("tools.ecosystem_state.STATE_PATH", state_path):
                from tools import ecosystem_state

                ecosystem_state.EXAMPLE_PATH = Path(tmp) / "missing.json"
                first = append_oversight_to_ecosystem(bundle)
                second = append_oversight_to_ecosystem(bundle)
                self.assertTrue(first["api_audit"])
                self.assertFalse(second["api_audit"])
                state = ecosystem_state.load_state()
                self.assertEqual(len(state["supervisor_summaries"]), 1)

    def test_save_blob_calls_storage(self):
        bundle = build_post_job_oversight("20260529_191611", {"AGENT_ACTIVITY": {}}, [])
        with patch("src.storage_client.save_state_blob") as mock_save:
            name = save_post_job_oversight_blob(bundle)
            self.assertEqual(name, "post_job_oversight_20260529_191611.json")
            mock_save.assert_called_once()
            saved = mock_save.call_args[0][1]
            self.assertEqual(saved["run_id"], "20260529_191611")


if __name__ == "__main__":
    unittest.main()
