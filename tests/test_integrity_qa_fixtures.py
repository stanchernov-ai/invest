"""Golden-fixture regression tests for deterministic QA Integrity pre-checks.

Fixtures: tests/fixtures/integrity_qa/ — see manifest.json.
"""
import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from src.output import reporting
from src.qa.integrity_audit import build_deterministic_integrity_report, extract_dashboard_statuses
from src.qa.scorecard import build_qa_scorecard

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "integrity_qa"


def _load_manifest():
    with open(FIXTURES_DIR / "manifest.json", encoding="utf-8") as f:
        return json.load(f)["fixtures"]


def _load_fixture(entry: dict) -> dict:
    with open(FIXTURES_DIR / entry["qa_reports"], encoding="utf-8") as f:
        qa_reports = json.load(f)
    with open(FIXTURES_DIR / entry["expected"], encoding="utf-8") as f:
        expected = json.load(f)
    if entry.get("generate_dashboard"):
        dashboard_html = reporting.generate_qa_dashboard_html(qa_reports, "fixture_run")
    else:
        dashboard_html = (FIXTURES_DIR / entry["dashboard"]).read_text(encoding="utf-8")
    return {"id": entry["id"], "qa_reports": qa_reports, "dashboard_html": dashboard_html, "expected": expected}


def _finding_matches(finding: dict, requirement: dict) -> bool:
    if finding.get("severity") != requirement.get("severity"):
        return False
    if requirement.get("category") and finding.get("category") != requirement["category"]:
        return False
    needle = requirement.get("description_contains", "")
    if needle and needle.lower() not in (finding.get("description") or "").lower():
        return False
    return True


def _assert_report_matches(test_case, report: dict, expected: dict, fixture_id: str):
    test_case.assertEqual(
        report["is_compliant"],
        expected["expect_compliant"],
        f"{fixture_id}: is_compliant mismatch — {report.get('summary')!r}",
    )
    for req in expected.get("required_findings", []):
        test_case.assertTrue(
            any(_finding_matches(f, req) for f in report.get("findings", [])),
            f"{fixture_id}: missing {req!r}; got {report.get('findings')!r}",
        )
    for sev in expected.get("forbidden_severities", []):
        bad = [f for f in report.get("findings", []) if f.get("severity") == sev]
        test_case.assertEqual(bad, [], f"{fixture_id}: forbidden {sev}: {bad!r}")


class TestIntegrityQAGoldenFixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = [_load_fixture(e) for e in _load_manifest()]

    def test_all_golden_fixtures(self):
        for case in self.cases:
            with self.subTest(fixture=case["id"]):
                report = build_deterministic_integrity_report(case["qa_reports"], case["dashboard_html"])
                _assert_report_matches(self, report, case["expected"], case["id"])

    def test_extract_dashboard_statuses(self):
        case = next(c for c in self.cases if c["id"] == "good_alignment")
        statuses = extract_dashboard_statuses(case["dashboard_html"])
        self.assertTrue(statuses.get("Post Mortem QA Auditor"))


class TestQAScorecard(unittest.TestCase):
    def test_build_scorecard_from_reports(self):
        case = next(c for c in TestIntegrityQAGoldenFixtures.cases if c["id"] == "good_alignment")
        activity = {
            "post_mortem_qa": {"invocations": 1, "model": "gemini-2.5-flash", "total_tokens": 500,
                               "prompt_tokens": 400, "output_tokens": 100, "thinking_tokens": 0, "errors": 0},
        }
        card = build_qa_scorecard("20260529_120000", case["qa_reports"], activity)
        self.assertEqual(card["run_id"], "20260529_120000")
        self.assertEqual(len(card["agents"]), 4)
        self.assertIn("PASS", card["summary"])
        pm = next(a for a in card["agents"] if a.get("agent_key") == "post_mortem_qa")
        self.assertEqual(pm["invocations"], 1)
        self.assertTrue(pm["is_compliant"])


class TestIntegrityQALLMGate(unittest.IsolatedAsyncioTestCase):
    async def test_merge_includes_deterministic_findings(self):
        from src.qa_pipeline import run_qa_integrity_audit

        case = _load_fixture(next(e for e in _load_manifest() if e["id"] == "dashboard_mismatch"))
        with patch("src.qa_pipeline.call_gemini_async", new_callable=AsyncMock) as mock_llm:
            report = await run_qa_integrity_audit(
                case["qa_reports"], "debate log", "{}", case["dashboard_html"]
            )
        mock_llm.assert_called_once()
        self.assertFalse(report["is_compliant"])
        self.assertTrue(any(f.get("category") == "Dashboard Fidelity" for f in report["findings"]))


if __name__ == "__main__":
    unittest.main()
