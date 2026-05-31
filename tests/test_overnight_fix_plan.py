"""Tests for overnight fix_plan validation."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.overnight.fix_plan import parse_fix_plan, validate_fix_plan


VALID_PLAN = """---
schema_version: 1
issue_id: QA-TEST-01
fix_type: code
verdict: READY
effort: S
risk: low
estimated_files: 1
---

# Fix plan

## Success criteria

- [ ] Unit tests pass

## Scope

### In scope

| Path | Change |
|------|--------|
| `src/output/reporting.py` | Add footer |

## Test commands

```powershell
.venv\\Scripts\\python.exe -m unittest tests.test_reporting_briefing -v
```
"""


class TestFixPlanValidation(unittest.TestCase):
    def test_valid_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fix_plan.md"
            path.write_text(VALID_PLAN, encoding="utf-8")
            plan = parse_fix_plan(path)
            ok, errors = validate_fix_plan(plan, issue_id="QA-TEST-01")
            self.assertTrue(ok, errors)
            self.assertEqual(plan.in_scope_paths, ["src/output/reporting.py"])
            self.assertEqual(len(plan.test_commands), 1)

    def test_denylist_blocks_financial_module(self) -> None:
        bad = VALID_PLAN.replace(
            "`src/output/reporting.py`",
            "`src/core/vote_engine.py`",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fix_plan.md"
            path.write_text(bad, encoding="utf-8")
            plan = parse_fix_plan(path)
            ok, errors = validate_fix_plan(plan, issue_id="QA-TEST-01")
            self.assertFalse(ok)
            self.assertTrue(any("denylist" in e for e in errors))

    def test_agent_requires_approval(self) -> None:
        agent_plan = VALID_PLAN.replace("fix_type: code", "fix_type: agent")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fix_plan.md"
            path.write_text(agent_plan, encoding="utf-8")
            plan = parse_fix_plan(path)
            ok, errors = validate_fix_plan(
                plan,
                issue_id="QA-TEST-01",
                requires_human_approval=True,
                approved_by=None,
            )
            self.assertFalse(ok)
            self.assertTrue(any("approved_by" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
