"""Tests for post_job_sync and sync_ecosystem."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.qa.post_job_audit import build_post_job_oversight
from src.qa.post_mortem_audit import merge_post_mortem_reports
from tools.post_job_sync import run_post_job_sync


class TestMergePostMortemSkipLlm(unittest.TestCase):
    def test_empty_violations_no_llm_is_pass(self):
        merged = merge_post_mortem_reports([], None)
        self.assertTrue(merged["is_compliant"])
        self.assertEqual(merged["findings"], [])


class TestPostJobSync(unittest.TestCase):
    def test_writes_ecosystem_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            (cache / "state").mkdir()
            run_id = "20260529_152151"
            telemetry = {
                "AGENT_ACTIVITY": {
                    "hypatia": {"invocations": 2, "total_tokens": 1000, "model": "gemini-2.5-pro",
                                "prompt_tokens": 800, "output_tokens": 200, "thinking_tokens": 0, "errors": 0},
                    "chairman": {"invocations": 0, "total_tokens": 0, "model": "gemini-2.5-pro",
                                 "prompt_tokens": 0, "output_tokens": 0, "thinking_tokens": 0, "errors": 0},
                },
                "chairman_bypassed": True,
                "munger_skipped": True,
                "QA_SCORECARD": {"summary": "1 PASS / 4 FAIL", "agents": [], "totals": {"non_compliant_count": 4}},
            }
            (cache / "state" / f"api_telemetry_{run_id}.json").write_text(
                json.dumps(telemetry), encoding="utf-8"
            )
            qa_reports = [{
                "agent_role": "Post Mortem QA Auditor",
                "is_compliant": True,
                "findings": [{"severity": "CRITICAL", "description": "test"}],
            }]
            (cache / "state" / f"qa_reports_{run_id}.json").write_text(
                json.dumps(qa_reports), encoding="utf-8"
            )

            with patch("tools.ecosystem_state.STATE_PATH", cache / "ecosystem_state.json"):
                from tools import ecosystem_state

                ecosystem_state.EXAMPLE_PATH = cache / "missing_example.json"
                bundle = build_post_job_oversight(run_id, telemetry, qa_reports)
                (cache / "state" / f"post_job_oversight_{run_id}.json").write_text(
                    json.dumps(bundle), encoding="utf-8"
                )
                result = run_post_job_sync(run_id, cache)
                self.assertEqual(result["qa_critical_count"], 1)
                state = ecosystem_state.load_state()
                self.assertTrue(any(e.get("agent") == "api_optimization" for e in state["api_audit"]))
                self.assertTrue(any(e.get("agent") == "data_insight" for e in state["data_insights"]))
                self.assertTrue(any(e.get("agent") == "supervisor" for e in state["supervisor_summaries"]))


if __name__ == "__main__":
    unittest.main()
