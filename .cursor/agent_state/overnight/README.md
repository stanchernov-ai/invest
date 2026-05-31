# Overnight flywheel runtime (gitignored except templates)

**SSOT:** [`docs/overnight_flywheel_review.md`](../../../docs/overnight_flywheel_review.md)

| Path | Purpose |
|------|---------|
| `templates/fix_plan.template.md` | Architect starting point (committed) |
| `runs/{issue_id}/manifest.json` | Orchestrator state |
| `runs/{issue_id}/fix_plan.md` | Architect plan-only artifact |
| `runs/{issue_id}/iterations/NN/test_result.json` | Tester structured output |
| `runs/{issue_id}/supervisor_summary.json` | Final verdict |
| `worktrees/` | Isolated git worktrees per issue |
| `LOCK` | Human architect session lock |

**CLI:** `tools/overnight_fix.py` · `tools/issue_roi.py` · `tools/validate_fix_plan.py`

**While another human/agent is editing the repo:**

```powershell
.venv\Scripts\python.exe tools/overnight_fix.py lock --owner human-architect --reason "active SaaS deploy"
# when done:
.venv\Scripts\python.exe tools/overnight_fix.py unlock
```
