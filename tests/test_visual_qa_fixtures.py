"""Golden-fixture regression tests for deterministic Visual QA.

Fixtures live in tests/fixtures/visual_qa/ — see manifest.json.
To add a case: drop in briefing.html + *.chart_health.json + *.expected.json,
register in manifest.json, and run unittest.
"""
import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from src.qa.visual_audit import audit_briefing_html, build_deterministic_visual_report
from src.qa_pipeline import run_graphics_designer_qa

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "visual_qa"


def _load_manifest():
    with open(FIXTURES_DIR / "manifest.json", encoding="utf-8") as f:
        return json.load(f)["fixtures"]


def _load_fixture(entry: dict) -> dict:
    html = (FIXTURES_DIR / entry["html"]).read_text(encoding="utf-8")
    with open(FIXTURES_DIR / entry["chart_health"], encoding="utf-8") as f:
        chart_health = json.load(f)
    with open(FIXTURES_DIR / entry["expected"], encoding="utf-8") as f:
        expected = json.load(f)
    return {"id": entry["id"], "html": html, "chart_health": chart_health, "expected": expected}


def _finding_matches(finding: dict, requirement: dict) -> bool:
    if finding.get("severity") != requirement.get("severity"):
        return False
    if requirement.get("category") and finding.get("category") != requirement["category"]:
        return False
    needle = requirement.get("description_contains", "")
    if needle and needle.lower() not in (finding.get("description") or "").lower():
        return False
    return True


def _assert_report_matches_fixture(test_case, report: dict, expected: dict, fixture_id: str):
    test_case.assertEqual(
        report["is_compliant"],
        expected["expect_compliant"],
        f"{fixture_id}: is_compliant mismatch — summary={report.get('summary')!r}",
    )
    for req in expected.get("required_findings", []):
        test_case.assertTrue(
            any(_finding_matches(f, req) for f in report.get("findings", [])),
            f"{fixture_id}: missing required finding {req!r}; got {report.get('findings')!r}",
        )
    for sev in expected.get("forbidden_severities", []):
        bad = [f for f in report.get("findings", []) if f.get("severity") == sev]
        test_case.assertEqual(
            bad, [],
            f"{fixture_id}: forbidden {sev} findings present: {bad!r}",
        )


class TestVisualQAGoldenFixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = [_load_fixture(e) for e in _load_manifest()]

    def test_manifest_has_cases(self):
        self.assertGreaterEqual(len(self.cases), 5)

    def test_all_golden_fixtures(self):
        for case in self.cases:
            with self.subTest(fixture=case["id"]):
                report = build_deterministic_visual_report(case["html"], case["chart_health"])
                _assert_report_matches_fixture(self, report, case["expected"], case["id"])

    def test_html_audit_isolated(self):
        html = (FIXTURES_DIR / "broken_flex_layout.html").read_text(encoding="utf-8")
        findings = audit_briefing_html(html)
        self.assertTrue(any(f["category"] == "Email Layout" for f in findings))


class TestVisualQALLMGate(unittest.IsolatedAsyncioTestCase):
    async def test_skips_llm_when_deterministic_fails(self):
        case = _load_fixture(next(c for c in _load_manifest() if c["id"] == "broken_flex_layout"))
        with patch("src.qa_pipeline.call_gemini_async", new_callable=AsyncMock) as mock_llm:
            report = await run_graphics_designer_qa(case["html"], case["chart_health"])
        mock_llm.assert_not_called()
        self.assertFalse(report["is_compliant"])


if __name__ == "__main__":
    unittest.main()
