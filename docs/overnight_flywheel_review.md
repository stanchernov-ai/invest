# Overnight Self-Healing Flywheel — Review (May 31, 2026)

**Audience:** Developer pushing the next prod deploy + overnight automation work.  
**Reviewer:** Cursor session (Supervisor-aligned).  
**Verdict:** Strategy direction is sound; **do not wire overnight fixes to the 6 AM production pipeline** until Tier 1 gates are proven on isolated worktrees.

---

## SME mapping — assessment

| SME role | Proposed equivalent | Assessment |
|----------|---------------------|------------|
| **Analyst / Triage** | `sync_backlog.py` + `candidate_triage` + §0.6 | **Accurate.** Missing piece is a **deterministic ROI scorer** (file count, `fix=code`, rule already in `post_job_audit.py`) — agree this is Tier 0, not LLM. |
| **Architect** | `debate_qa_architect_handoff.md` (human) | **Correct gap.** `fix_plan_{issue_id}.md` as plan-only artifact fits `.cursorrules` §0.5 (human approves scope). Do not let Architect invoke Developer in same turn. |
| **Developer** | Cursor Agent manual | **Correct.** Overnight = Cursor CLI/SDK on **git worktree per issue**, one issue per branch. Never commit directly to `main`. |
| **Tester / Gatekeeper** | `pre_commit_check.py` + golden fixtures | **Correct.** This is your L3 for **code**; production L3–L5 stays separate. Pipe **exit code + JSON findings** to Supervisor, not prose. |
| **Supervisor** | `supervisor_agent.mdc` + `post_job_audit.py` | **Accurate.** Extend `supervisor_summaries` with `run_kind: overnight_fix` and `issue_id`. |
| **Deterministic bridge** | `ecosystem_state.json`, blobs | **Critical.** Already partially built (C1/C2 in `cursor_dev_plane_handoff.md`). Enforce: **blob path + schema version** between agents. |

**Agree:** No fifth QA role for code paths. Debate QA remains production-only.

---

## Tier 0 — keep and harden

**Aligns with product principles** (humans approve fix queue; no silent financial logic changes).

| Ticket | Priority | Notes |
|--------|----------|-------|
| **C2** — Persist standing QA digest to blob | P0 for Analyst | Unblocks ROI input without re-parsing Gmail |
| **Layer 7 golden fixtures** (PE-PERSONA, R2 verbatim) | P0 for Tester | Match **detectable defect classes**, not full LLM verdict parity |
| **Triage auto-promote** (`fix=code` + prior human mark) | P1 | Must log promotion reason to `ecosystem_state.json` |

**Prod caveat (May 31):** `boardroom-prepare-queue` was **missing** in `AzureWebJobsStorage`; manual enqueue did not trigger `boardroom_prepare` until local `kickoff_user_run.py`. **Before relying on dispatcher fan-out**, verify queue exists and dequeue count increments after deploy. Consider HTTP prepare only for manual runs until queue trigger is validated.

---

## Tier 1 — supervised self-healing (2–4 weeks)

**Recommended shape** (completes the truncated proposal):

```
overnight_fix.py --issue QA-090637-03 --max-iterations 3
  1. Analyst: load Open item + ROI from ecosystem_state + blob refs
  2. Architect: write fix_plan_{issue_id}.md (no code)
  3. Human gate (optional): approve plan via file marker or CLI flag
  4. Developer: Cursor SDK in worktree → implement plan scope only
  5. Tester: pre_commit_check.py + targeted pytest; fail → stderr JSON to Supervisor
  6. Supervisor: PASS | PASS_WITH_WARNINGS | BLOCKED | ESCALATE → append supervisor_summaries
  7. On PASS: open PR (human merges); never push main from agent
```

**Hard boundaries:**

- `max-iterations` = Two-Strike Rule per file+problem (already in `supervisor_agent.mdc`)
- **Forbidden:** Auto-merge, auto-deploy, auto-kickoff `/api/prepare`, changes to `verdict_memory` / liquidation logic without human label
- **Allowed overnight:** Prompt copy, reporting HTML/CSS, deterministic QA rules, test fixtures

---

## What this deploy includes (no pipeline execution)

| Area | Change |
|------|--------|
| **Email** | `email_routing.py` — testers: briefing only; `stan`: briefing + QA + legal |
| **Prepare** | `generate_dynamic_mandate` → `portfolio_policy` (fixes import crash) |
| **Multi-user local** | `orchestrate.run_all(user_id=...)`, kickoff/enqueue/admin scripts |
| **Troy holdings** | `data/tester1-etrade-holdings.csv` (DB provision via admin script, not in deploy artifact path for runtime) |

**Not in this deploy:** Queue trigger fix, `overnight_fix.py`, Architect plan artifacts, Tier 0 C2 blob digest.

**App setting:** `STAN_PERSONAL_EMAIL` reverted to `stan.chernov@gmail.com` on prod (test override removed).

---

## Risks for the next developer

1. **Flex Consumption + new queues** — Create queues before first dispatcher run; run `syncfunctiontriggers` after deploy; confirm dequeue in logs.
2. **HTTP `/api/prepare`** still defaults `user_id=stan` — multi-user manual runs should use queue JSON or local kickoff.
3. **Overnight + 6 AM collision** — Use `storage_client.is_run_in_flight()` or per-issue lock; do not share global prepare lock with production.
4. **SAAS-2b** — Implemented in code; mark tracker done; document `OWNER_SLUGS` in `email_routing.py` when adding prod users.

---

## Suggested PR split (for your push)

1. **PR-A (this deploy):** email routing, prepare fix, orchestrate `user_id`, legal skip for testers, ops scripts  
2. **PR-B (infra):** queue bootstrap doc + optional `scripts/ensure_azure_queues.py`  
3. **PR-C (Tier 0):** C2 digest blob + golden fixtures  
4. **PR-D (Tier 1):** `overnight_fix.py` skeleton + `fix_plan_` template only  

**Shipped (PR-D skeleton):** `src/overnight/`, `tools/overnight_fix.py`, `tools/issue_roi.py`, `tools/validate_fix_plan.py`, template at `.cursor/agent_state/overnight/templates/fix_plan.template.md`.

---

## Artifact schemas (PR-D)

| File | Format | Writer | Reader |
|------|--------|--------|--------|
| `manifest.json` | JSON | `overnight_fix.py init` | Orchestrator, validate-plan |
| `fix_plan.md` | Markdown + YAML frontmatter | Architect (human/Cursor) | Developer, Tester |
| `test_result.json` | JSON | `overnight_fix.py test` | Developer retry, Supervisor |
| `supervisor_summary.json` | JSON | Tester on PASS/ESCALATE | `ecosystem_state` → `supervisor_summaries`, `overnight_runs` |

**Handoff rule:** Developer reads `fix_plan.md` + prior `test_result.json` only — not freeform chat between agents.

**Supervisor fields:** `run_kind: overnight_fix`, `issue_id`, `verdict` ∈ `PASS` | `PASS_WITH_WARNINGS` | `BLOCKED` | `ESCALATE`.

**CLI quick start:**

```powershell
.venv\Scripts\python.exe tools/issue_roi.py --fix-type code --limit 5
.venv\Scripts\python.exe tools/overnight_fix.py init --issue QA-090637-02
# edit fix_plan.md → verdict: READY
.venv\Scripts\python.exe tools/overnight_fix.py validate-plan --issue QA-090637-02
.venv\Scripts\python.exe tools/overnight_fix.py test --issue QA-090637-02 --iteration 1
```
