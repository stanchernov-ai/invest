"""Tests for deterministic overnight ROI scoring."""
from __future__ import annotations

import unittest

from src.overnight.roi import score_item


class TestOvernightRoi(unittest.TestCase):
    def test_code_beats_agent(self) -> None:
        code = score_item({
            "priority": "P2",
            "fix": "code",
            "status": "open",
            "item": "Add footer to briefing HTML",
            "evidence": "qa_reports_20260531_090637.json",
        })
        agent = score_item({
            "priority": "P2",
            "fix": "agent",
            "status": "open",
            "item": "Tune prompt engineer",
            "evidence": "",
        })
        self.assertGreater(code, agent)

    def test_financial_keyword_zeroed(self) -> None:
        score = score_item({
            "priority": "P1",
            "fix": "code",
            "status": "open",
            "item": "Adjust vote_engine funding sell selection",
            "evidence": "",
        })
        self.assertEqual(score, 0.0)

    def test_discarded_negative(self) -> None:
        score = score_item({"priority": "P0", "fix": "discard", "status": "discarded", "item": "x"})
        self.assertLess(score, 0)


if __name__ == "__main__":
    unittest.main()
