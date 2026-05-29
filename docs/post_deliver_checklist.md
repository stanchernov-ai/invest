# Post-Deliver Checklist

**When:** After every successful `deliver` phase (weekday pipeline or manual `/api/prepare` kickoff).  
**Time:** ~10–15 minutes human + 2 minutes scripted.  
**Goal:** Turn run artifacts into validated backlog items — not lost in email or QA HTML.

Related: [`engineering_playbook.md`](engineering_playbook.md) · [`action_tracker.md`](action_tracker.md) · [`agent_architecture.md`](agent_architecture.md) §6–§8

---

## 1. Confirm the run finished

```powershell
.venv\Scripts\python.exe scripts\wait_for_run.py --run-id YYYYMMDD_HHMMSS
```

Or read `boardroom-state/run_status.json`:

- Overall `status` = `success`
- All three phases: `prepare`, `debate`, `deliver` = `success`
- Note `briefing_blob` and `qa_blob` names

**If failed:** skip this checklist; fix the phase error first (see failure email + `run_status.json` → `error`).

---

## 2. Pull artifacts locally

```powershell
.venv\Scripts\python.exe tools\fetch_azure_reports.py --run-id YYYYMMDD_HHMMSS
```

Confirm under `.cache/`:

| File | Purpose |
|------|---------|
| `reports/executive_briefing_*.html` | Spot-check briefing (SoTU, debate section, charts) |
| `reports/qa_dashboard_*.html` | QA PASS/FAIL summary |
| `state/qa_reports_*.json` | Full QA findings |
| `state/qa_human_review_*.json` | Your confirmations (if submitted) |
| `state/debate.json` | Chairman output + **`raw_verdicts`** (Round 2 vote SSOT) |
| `state/board_verdicts.json` | Pass cooldown writes (after compliant deliver) |
| `state/api_telemetry_*.json` | Scorecard + agent activity |
| `reports/retrospective_*.md` | Auto-generated candidate action items (after deliver) |
| `state/retrospective_*.json` | Idempotency marker (skip if already processed) |

---

## 3. Human QA review (if not done yet)

Open the **Review QA accuracy** button in the QA dashboard email.

For each QA agent:

- **Confirm** if the PASS/FAIL matches what you saw in the briefing/debate
- **Reject** false positives (especially Prompt Engineer rubber-stamps)
- Add **notes** for anything the QA stack missed

Stored in Azure: `qa_human_review_{run_id}.json` + `qa_human_reviews_ledger.json`.

---

## 4. Review the retrospective (runs automatically after deliver)

**Automatic:** `execute_retrospective()` runs at the end of every successful deliver. It is **idempotent** — the same `run_id` is never processed twice unless you pass `force`.

**Azure artifacts:**
- `boardroom-reports/retrospective_{run_id}.md` — candidate action items + backlog flags
- `boardroom-state/retrospective_{run_id}.json` — completion marker
- `boardroom-state/retrospectives_ledger.json` — rolling history (deduped by run_id)

**Manual re-run** (e.g. after you submit human review later):

```powershell
.venv\Scripts\python.exe tools/run_retrospective.py --run-id YYYYMMDD_HHMMSS --force
```

Or HTTP: `GET /api/retrospective?run_id=…&force=true` (function key required).

**Local optional:**

```powershell
.venv\Scripts\python.exe tools/ecosystem_state.py show data_insights --last 3
```

---

## 5. Validate before promoting (QA-of-QA)

Do **not** paste every CRITICAL finding into the backlog blindly.

| Check | How |
|-------|-----|
| Did it actually happen? | Read `raw_debate_log_*.md`, `debate.json` chairman output, or **`raw_verdicts`** for vote math |
| Verdict memory written? | `board_verdicts.json` has Pass rows dated `run_id[:8]` when debate was approved |
| Chairman bypass? | Scratchpad contains `VOTE ENGINE BYPASS` when Pro was skipped; else `VOTE DIGEST` reference |
| Is it already fixed? | Compare to recent commits + golden tests |
| Is it a false positive? | Mark in human review; skip backlog |
| Is it code-enforceable? | Prefer Python validator + test over prompt tweak |

**Authoritative layers:** deterministic Python (🟢) > human review > LLM QA (🟡).

---

## 6. Update the backlog

Edit `docs/action_tracker.md` → **Session Handoff → Open items**:

```markdown
| **P1** | Short title — one-line fix scope. evidence: qa_reports_{run_id}.json |
```

Rules:

- One item per distinct problem (dedupe the retrospective list)
- Mark items **DONE** with commit hash when shipped
- Add `regression_test:` or `fixture:` note when a golden test covers it
- Move stale items to done or delete with reason

---

## 7. Regression guard (don't re-break)

When closing an item that was a **code fix**:

1. Add or extend a unit/golden test (`tests/test_*.py`, `tests/fixtures/`)
2. Reference the test path in the DONE line in action_tracker
3. On future retrospectives, a **possible_regression** flag fires if the same theme reappears

---

## 8. Optional — Cursor post-job agents

When coding the same day as a run, spawn (or run yourself):

1. **Data Insight** — scan `.cache/` for recurring N/A fields, idle agents
2. **API Optimization** — check `api_telemetry_*` for duplicate FMP calls
3. **Supervisor** — synthesize into `ecosystem_state.json` → `supervisor_summaries`

These are advisory; they do not replace steps 3–6.

---

## Quick reference (copy-paste)

Replace `RUN_ID`:

```powershell
.venv\Scripts\python.exe scripts\wait_for_run.py --run-id RUN_ID
.venv\Scripts\python.exe tools\fetch_azure_reports.py --run-id RUN_ID
# Retrospective already ran in deliver — read reports/retrospective_RUN_ID.md
```

Then: human review → validate findings → update `action_tracker.md`.
