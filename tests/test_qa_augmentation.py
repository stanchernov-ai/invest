"""Tests for QA LLM augmentation policy helpers."""
import unittest

from src.qa.qa_augmentation import (
    collect_post_mortem_drift_warnings,
    extract_qa_execution,
    should_augment_architect_llm,
    should_augment_persona_llm,
    should_augment_post_mortem_spot,
)


class TestQaAugmentationPolicy(unittest.TestCase):
    def test_persona_augment_on_fail(self):
        self.assertTrue(should_augment_persona_llm(["SYCOPHANCY"], {}))

    def test_persona_augment_borderline_pass(self):
        stats = {"total_tickers": 5, "unanimous_rate": 0.5}
        self.assertTrue(should_augment_persona_llm([], stats))

    def test_persona_skip_low_unanimity(self):
        stats = {"total_tickers": 5, "unanimous_rate": 0.2}
        self.assertFalse(should_augment_persona_llm([], stats))

    def test_architect_never_llm(self):
        self.assertFalse(should_augment_architect_llm(["CHAIRMAN SCHEMA: missing key"]))
        self.assertFalse(should_augment_architect_llm([]))

    def test_post_mortem_spot_vote_engine_scratchpad(self):
        chairman = {"chain_of_thought_scratchpad": "PYTHON VOTE ENGINE ALLOCATION"}
        self.assertTrue(should_augment_post_mortem_spot(chairman, []))

    def test_post_mortem_spot_on_drift(self):
        self.assertTrue(should_augment_post_mortem_spot({}, ["SCRATCHPAD DIGEST MISMATCH: NVDA"]))

    def test_extract_qa_execution(self):
        reports = [
            {"agent_role": "Prompt Engineer QA", "execution_mode": "llm_borderline"},
            {"agent_key": "red_teamer", "execution_mode": "llm_active"},
        ]
        ex = extract_qa_execution(reports)
        self.assertEqual(ex["prompt_engineer"], "llm_borderline")
        self.assertEqual(ex["red_teamer"], "llm_active")

    def test_collect_drift_empty_on_clean_chairman(self):
        chairman = {"chain_of_thought_scratchpad": "No digest here"}
        warnings = collect_post_mortem_drift_warnings(
            chairman, None, None, all_symbols=[], portfolio_symbols=set(),
        )
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
