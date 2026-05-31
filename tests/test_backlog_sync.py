"""Tests for action_tracker backlog sync."""
import tempfile
import unittest
from pathlib import Path

from src.qa.backlog_sync import (
    merge_run_into_backlog,
    parse_backlog_items,
    write_backlog_items,
)
from src.qa.candidate_triage import candidate_key

SAMPLE_CAND = {
    "source": "qa_report",
    "agent_role": "Systems Architect",
    "severity": "CRITICAL",
    "suggested_priority": "P1",
    "description": "Unique zebra catalyst table rendering gap in briefing",
    "recommendation": "Add catalyst fallback row to briefing template",
}

TRACKER_SNIPPET = """# Action Tracker

## Session Handoff

### Open items (prioritized)

| Pri | ID | Effort | Item | Notes |
|-----|-----|--------|------|-------|
| **P1** | PASS-SPAM-1 | M | Reduce watchlist Pass spam in debate log | old format row |

**Done (now prod):** DEPLOY-1, REVIEW-1.

---

## Session Handoff — archived
"""


class TestBacklogParse(unittest.TestCase):
    def test_parse_old_format_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "action_tracker.md"
            path.write_text(TRACKER_SNIPPET, encoding="utf-8")
            items = parse_backlog_items(path)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["item_id"], "PASS-SPAM-1")


class TestBacklogSync(unittest.TestCase):
    def test_adds_new_qa_finding(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "action_tracker.md"
            path.write_text(TRACKER_SNIPPET, encoding="utf-8")
            cache = Path(tmp) / "cache"
            cache.mkdir()
            (cache / "state").mkdir(parents=True)

            result = merge_run_into_backlog(
                "20260530_235519",
                tracker_path=path,
                cache_dir=cache,
                candidates=[SAMPLE_CAND],
            )
            self.assertEqual(result["added"], 1)
            items = parse_backlog_items(path)
            ids = [i["item_id"] for i in items]
            self.assertTrue(any("zebra" in (i["item"] or "").lower() for i in items))

    def test_dedupes_similar_finding(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "action_tracker.md"
            path.write_text(TRACKER_SNIPPET, encoding="utf-8")
            cache = Path(tmp) / "cache"
            (cache / "state").mkdir(parents=True)

            dup = dict(SAMPLE_CAND)
            dup["description"] = "Reduce watchlist Pass spam in debate log for many symbols"
            result = merge_run_into_backlog(
                "20260530_235519",
                tracker_path=path,
                cache_dir=cache,
                candidates=[dup],
            )
            self.assertEqual(result["added"], 0)
            self.assertGreater(result["skipped"], 0)

    def test_triage_discard_skips_add(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "action_tracker.md"
            path.write_text(TRACKER_SNIPPET, encoding="utf-8")
            cache = Path(tmp) / "cache"
            state = cache / "state"
            state.mkdir(parents=True)
            key = candidate_key(SAMPLE_CAND)
            import json
            state.joinpath("candidate_triage_20260530_235519.json").write_text(
                json.dumps({"items": [{"candidate_key": key, "disposition": "discard"}]}),
                encoding="utf-8",
            )
            result = merge_run_into_backlog(
                "20260530_235519",
                tracker_path=path,
                cache_dir=cache,
                candidates=[SAMPLE_CAND],
            )
            self.assertEqual(result["added"], 1)
            items = parse_backlog_items(path)
            self.assertTrue(any(i.get("status") == "discarded" for i in items))


class TestBacklogWrite(unittest.TestCase):
    def test_write_new_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "action_tracker.md"
            path.write_text(TRACKER_SNIPPET, encoding="utf-8")
            write_backlog_items(path, [{
                "priority": "P1",
                "item_id": "QA-TEST-01",
                "status": "open",
                "source": "Systems Architect",
                "fix": "code",
                "item": "Test finding",
                "evidence": "qa_reports_test.json",
            }])
            text = path.read_text(encoding="utf-8")
            self.assertIn("| Pri | ID | Status | Source | Fix | Item | Evidence |", text)
            self.assertIn("QA-TEST-01", text)


if __name__ == "__main__":
    unittest.main()
