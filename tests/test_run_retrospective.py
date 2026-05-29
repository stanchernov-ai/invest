import unittest
from unittest.mock import patch

from src.qa.retrospective import (
    build_candidate_actions,
    cross_check_backlog,
    parse_backlog,
    collect_human_review_items,
    should_skip_run,
    execute_retrospective,
)


class TestRunRetrospective(unittest.TestCase):
    def test_build_candidate_actions_from_qa_and_human(self):
        qa_reports = [{
            "agent_role": "Post Mortem QA Auditor",
            "is_compliant": False,
            "findings": [{
                "severity": "CRITICAL",
                "category": "Procedural",
                "description": "Chairman failed to execute TLT hedge purchase.",
                "recommendation": "Enforce hedge in guardrails.",
            }],
            "summary": "Hedge missing.",
        }]
        human = {
            "reviews": [{
                "agent_role": "Prompt Engineer QA",
                "human_confirmed": False,
                "human_notes": "Should audit agent configs, not just persona drift.",
            }],
        }
        candidates = build_candidate_actions(qa_reports, human, None)
        self.assertGreaterEqual(len(candidates), 2)

    def test_human_review_notes_when_confirmed(self):
        human = {
            "reviews": [{
                "agent_role": "Post Mortem QA Auditor",
                "human_confirmed": True,
                "human_notes": "State of the Union is broken — portfolio overview missing.",
            }],
        }
        items = collect_human_review_items(human)
        self.assertEqual(len(items), 1)
        self.assertIn("State of the Union", items[0]["description"])

    def test_cross_check_flags_done_overlap(self):
        candidates = [{
            "description": "State of the Union shows per-ticker quotes instead of portfolio overview.",
            "recommendation": "Fix clerk extraction.",
            "suggested_priority": "P1",
        }]
        backlog = {
            "open": [],
            "done": [{
                "priority": "P1",
                "text": "State of the Union fix — deterministic portfolio critiques. DONE May 29",
            }],
        }
        flags = cross_check_backlog(candidates, backlog)
        self.assertTrue(any(f["type"] == "possible_regression" for f in flags))

    def test_parse_backlog_open_and_done(self):
        sample = """
| **P1** | Prompt Engineer QA scope — audit agent configs |
| ~~**P1**~~ | ~~State of the Union fix~~ **DONE (May 29)** |
"""
        from pathlib import Path
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
            fh.write(sample)
            path = Path(fh.name)
        try:
            parsed = parse_backlog(path)
            self.assertEqual(len(parsed["open"]), 1)
            self.assertEqual(len(parsed["done"]), 1)
        finally:
            path.unlink()

    @patch("src.qa.retrospective.storage_client.load_state_blob")
    def test_should_skip_completed_run(self, mock_load):
        mock_load.return_value = {"status": "completed", "run_id": "20260529_120000"}
        marker = should_skip_run("20260529_120000")
        self.assertIsNotNone(marker)
        self.assertEqual(marker["status"], "completed")

    @patch("src.qa.retrospective.storage_client.load_state_blob")
    def test_force_bypasses_skip(self, mock_load):
        mock_load.return_value = {"status": "completed"}
        self.assertIsNone(should_skip_run("20260529_120000", force=True))

    @patch("src.qa.retrospective._update_ledger")
    @patch("src.qa.retrospective.storage_client.save_report")
    @patch("src.qa.retrospective.storage_client.save_state_blob")
    @patch("src.qa.retrospective.storage_client.load_run_status")
    @patch("src.qa.retrospective.should_skip_run")
    @patch("src.qa.retrospective.storage_client.load_state_blob")
    def test_execute_idempotent_skip(
        self, mock_load_blob, mock_skip, mock_status, mock_save_state, mock_save_report, mock_ledger
    ):
        mock_skip.return_value = {
            "status": "completed",
            "candidate_count": 3,
            "flag_count": 1,
            "markdown_blob": "retrospective_20260529_120000.md",
        }
        result = execute_retrospective("20260529_120000")
        self.assertEqual(result["status"], "skipped")
        mock_save_report.assert_not_called()


if __name__ == "__main__":
    unittest.main()
