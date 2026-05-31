---
schema_version: 1
issue_id: {{ISSUE_ID}}
fix_type: {{FIX_TYPE}}
verdict: DRAFT
effort: S
risk: low
estimated_files: 1
---

# Fix plan: {{ISSUE_ID}}

## Problem statement

{{DESCRIPTION}}

## Root cause (hypothesis)

<!-- Architect fills before setting verdict: READY -->

## Success criteria

- [ ] Targeted unit tests pass (list modules below)
- [ ] No edits to denylisted financial modules
- [ ] Pre-commit gate passes

## Scope

### In scope

| Path | Change |
|------|--------|
| `src/...` | <!-- one row per file, max 5 --> |

### Out of scope

- `src/core/vote_engine.py`, `guardrails.py`, `compliance_audit.py`, `engine.py`
- Auto-deploy, auto-merge, `/api/prepare`

## Implementation steps

1. <!-- plan-only — no full function bodies -->
2.

## Do not regress

- See `docs/product_principles.md` and `docs/engineering_playbook.md`

## Test commands

```powershell
.venv\Scripts\python.exe -m unittest tests.test_EXAMPLE -v
```

## Rollback

Revert branch `ai/fix-{{ISSUE_ID}}`; no migrations.
