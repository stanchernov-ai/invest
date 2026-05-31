"""Tests for HR utilization status resolution."""
import unittest

from src.hr_review import build_utilization, resolve_execution_status


class TestHrReviewStatus(unittest.TestCase):
    def test_chairman_vote_engine_not_idle(self):
        tel = {"chairman_bypassed": True, "allocation_source": "vote_engine"}
        status = resolve_execution_status("chairman", {"invocations": 0}, tel)
        self.assertEqual(status, "VOTE_ENGINE")

    def test_compliance_python_gate(self):
        tel = {"compliance_source": "python_only"}
        status = resolve_execution_status("compliance", {"invocations": 0}, tel)
        self.assertEqual(status, "PYTHON_GATE")

    def test_data_oracle_infra(self):
        status = resolve_execution_status("data_oracle", {"invocations": 0}, {})
        self.assertEqual(status, "INFRA")

    def test_qa_execution_from_telemetry(self):
        tel = {
            "QA_EXECUTION": {"prompt_engineer": "llm_borderline"},
            "chairman_bypassed": True,
        }
        status = resolve_execution_status("prompt_engineer", {"invocations": 0}, tel)
        self.assertEqual(status, "LLM (BORDERLINE)")

    def test_red_teamer_with_calls_ok(self):
        rows = build_utilization(
            {"red_teamer": {"invocations": 1, "total_tokens": 1000, "model": "gemini-2.5-flash"}},
            telemetry={},
        )
        rt = next(r for r in rows if r["agent"] == "red_teamer")
        self.assertEqual(rt["status"], "OK")
        self.assertFalse(rt["idle"])

    def test_build_utilization_chairman_not_idle_on_bypass(self):
        rows = build_utilization(
            {"hypatia": {"invocations": 2, "total_tokens": 100, "model": "gemini-2.5-pro"}},
            telemetry={"chairman_bypassed": True, "allocation_source": "vote_engine"},
        )
        chair = next(r for r in rows if r["agent"] == "chairman")
        self.assertEqual(chair["status"], "VOTE_ENGINE")
        self.assertFalse(chair["idle"])


if __name__ == "__main__":
    unittest.main()
