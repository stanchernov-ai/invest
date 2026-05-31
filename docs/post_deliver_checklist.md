# Post-Deliver Checklist

**When:** After every successful `deliver` phase (weekday pipeline or manual `/api/prepare` kickoff).  
**Time:** ~10–15 minutes human + 2 minutes scripted.  
**Goal:** QA findings land in **one backlog file** — `docs/action_tracker.md` Open items. Fix the code or fix the QA agent.

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

## 2. Pull artifacts + sync backlog

```powershell
.venv\Scripts\python.exe tools/fetch_azure_reports.py --run-id YYYYMMDD_HHMMSS --post-job
```

`--post-job` fetches artifacts, runs post-job agents, **and** merges QA findings into `action_tracker.md` via `sync_backlog.py`.

Confirm under `.cache/`:

| File | Purpose |
|------|---------|
| `reports/executive_briefing_*.html` | Spot-check briefing (SoTU, debate section, charts) |
| `reports/qa_dashboard_*.html` | QA PASS/FAIL + backlog items at bottom |
| `state/qa_reports_*.json` | Full QA findings (evidence for Open items) |
| `state/qa_human_review_*.json` | Your confirmations (if submitted) |
| `state/candidate_triage_*.json` | Fix code / fix agent / discard decisions |
| `state/debate.json` | Chairman output + **`raw_verdicts`** (Round 2 vote SSOT) |
| `state/post_job_oversight_*.json` | API Optimization + Data Insight + Supervisor |

**Manual backlog sync only:**

```powershell
.venv\Scripts\python.exe tools/sync_backlog.py --run-id YYYYMMDD_HHMMSS
```

---

## 3. Human QA review + backlog triage

Open the QA dashboard email → **Review QA accuracy** and **Triage backlog items**.

For each QA agent:

- **Confirm** or **reject** the PASS/FAIL verdict
- For each finding: **fix code**, **fix QA agent**, or **discard** (false positive)

Re-run sync after triage if you already fetched:

```powershell
.venv\Scripts\python.exe tools/sync_backlog.py --run-id YYYYMMDD_HHMMSS
```

---

## 4. Validate before closing items

| Check | How |
|-------|-----|
| Did it actually happen? | Read `raw_debate_log_*.md`, `debate.json`, or **`raw_verdicts`** |
| False positive? | Mark **discard** in triage; sync sets `Status=discarded` |
| QA agent wrong? | Mark **fix agent**; tune prompt or deterministic gate |
| Real bug? | Mark **fix code**; ship Python validator + test |
| Already tracked? | Sync dedupes — one row per distinct problem |

**Authoritative layers:** deterministic Python (🟢) > human review > LLM QA (🟡).

---

## 5. Work the backlog

All open work lives in **`docs/action_tracker.md` → Open items** — no separate “items to consider” file.

When shipping a fix:

1. Mark item done (remove row or set `Status=done`)
2. One line in **Done (now prod)** if user-facing
3. Add regression test when fixing code-enforced behavior

Rules: [`doc_hygiene.md`](doc_hygiene.md).

---

## 6. Regression guard

When closing a **code fix**:

1. Add or extend a unit/golden test
2. Reference test path in the DONE line
3. Future syncs flag **possible_regression** if the same theme reappears

---

## Quick reference

```powershell
.venv\Scripts\python.exe scripts/wait_for_run.py --run-id RUN_ID
.venv\Scripts\python.exe tools/fetch_azure_reports.py --run-id RUN_ID --post-job
# QA review + triage in browser → sync_backlog again if needed
```

Then: validate → fix code or fix agent → update Open items status.
