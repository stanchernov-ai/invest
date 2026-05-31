"""Tests for candidate action triage (promote / discard)."""
import os
import unittest
from unittest.mock import patch

from src.qa.candidate_triage import (
    candidate_key,
    format_promoted_markdown,
    load_triage_context,
    parse_triage_from_form,
    render_dashboard_candidates_html,
    render_triage_section_html,
    save_candidate_triage,
)


SAMPLE_CAND = {
    "source": "qa_report",
    "agent_role": "Systems Architect",
    "severity": "CRITICAL",
    "suggested_priority": "P1",
    "description": "Watchlist Pass spam in debate log",
    "recommendation": "Reduce Pass mentions",
}


class TestCandidateKey(unittest.TestCase):
    def test_stable_key(self):
        k1 = candidate_key(SAMPLE_CAND)
        k2 = candidate_key(dict(SAMPLE_CAND))
        self.assertEqual(k1, k2)
        self.assertEqual(len(k1), 16)


class TestCandidateTriagePersist(unittest.TestCase):
    @patch("src.qa.candidate_triage._persist_local_ecosystem")
    @patch("src.qa.candidate_triage._update_ledger")
    @patch("src.storage_client.save_state_blob")
    def test_save_promote_and_discard(self, mock_save, mock_ledger, mock_local):
        key = candidate_key(SAMPLE_CAND)
        record = save_candidate_triage("20260529_120000", [
            {**SAMPLE_CAND, "candidate_key": key, "disposition": "promote", "notes": "Valid issue."},
            {
                "candidate_key": "abc123",
                "disposition": "discard",
                "notes": "False positive.",
                "description": "Other finding",
            },
        ])
        self.assertEqual(record["promoted_count"], 1)
        self.assertEqual(record["discarded_count"], 1)
        self.assertIn("1 promoted", record["summary"])
        mock_save.assert_called_once()


class TestCandidateTriageRender(unittest.TestCase):
    def test_dashboard_section_lists_candidates(self):
        html = render_dashboard_candidates_html([SAMPLE_CAND], triage_url="https://x/api/qa-review#candidates")
        self.assertIn("Candidate Action Items", html)
        self.assertIn("Watchlist Pass spam", html)
        self.assertIn("Triage candidates", html)

    def test_triage_form_has_disposition_radios(self):
        ctx = {
            "run_id": "20260529_120000",
            "candidates": [{**SAMPLE_CAND, "candidate_key": candidate_key(SAMPLE_CAND), "disposition": "pending"}],
        }
        html = render_triage_section_html(ctx)
        self.assertIn("Add to backlog", html)
        self.assertIn("Discard", html)
        self.assertIn('name="disposition_0"', html)

    def test_format_promoted_markdown(self):
        key = candidate_key(SAMPLE_CAND)
        md = format_promoted_markdown("20260529_120000", [
            {**SAMPLE_CAND, "candidate_key": key, "disposition": "promote"},
        ])
        self.assertIn("**P1**", md)
        self.assertIn("qa_reports_20260529_120000.json", md)


class TestCandidateTriageParse(unittest.TestCase):
    def test_parse_form(self):
        key = candidate_key(SAMPLE_CAND)
        form = {
            "candidate_count": "1",
            "candidate_key_0": key,
            "disposition_0": "promote",
            "triage_notes_0": "Add this week",
            "candidate_description_0": SAMPLE_CAND["description"],
            "candidate_priority_0": "P1",
            "candidate_agent_role_0": SAMPLE_CAND["agent_role"],
            "candidate_severity_0": "CRITICAL",
            "candidate_source_0": "qa_report",
        }
        items = parse_triage_from_form(form)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["disposition"], "promote")


class TestCandidateTriageLoad(unittest.TestCase):
    @patch("src.storage_client.load_state_blob")
    def test_load_from_retrospective_marker(self, mock_load):
        mock_load.side_effect = lambda name: {
            "retrospective_20260529_120000.json": {"candidates": [SAMPLE_CAND]},
            "candidate_triage_20260529_120000.json": {
                "items": [{
                    "candidate_key": candidate_key(SAMPLE_CAND),
                    "disposition": "promote",
                    "notes": "Yes",
                }],
            },
        }.get(name)

        ctx = load_triage_context("20260529_120000")
        self.assertEqual(len(ctx["candidates"]), 1)
        self.assertEqual(ctx["candidates"][0]["disposition"], "promote")


class TestQaDashboardWithCandidates(unittest.TestCase):
    def test_generate_qa_dashboard_includes_candidates(self):
        from src.output import reporting

        reports = [{"agent_role": "Test QA", "is_compliant": True, "summary": "OK", "findings": []}]
        html = reporting.generate_qa_dashboard_html(
            reports, "20260529_120000",
            candidates=[SAMPLE_CAND],
            triage_url="https://example.com/api/qa-review#candidates",
        )
        self.assertIn("Candidate Action Items", html)
        self.assertIn("Watchlist Pass spam", html)


class TestReviewUrlFragment(unittest.TestCase):
    def test_build_review_url_with_fragment(self):
        from src.qa.human_review import build_review_url

        with patch.dict(os.environ, {
            "QA_REVIEW_BASE_URL": "https://example.azurewebsites.net",
            "QA_REVIEW_TOKEN": "abc",
        }):
            url = build_review_url("20260529_120000", fragment="candidates")
            self.assertEqual(
                url,
                "https://example.azurewebsites.net/api/qa-review?run_id=20260529_120000&token=abc#candidates",
            )


if __name__ == "__main__":
    unittest.main()
