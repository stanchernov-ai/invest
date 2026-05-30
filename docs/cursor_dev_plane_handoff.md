# Cursor Dev Plane Handoff — Agents & Ecosystem State

**Status:** Active handoff for developers  
**Last updated:** May 30, 2026  
**Owner:** Stan  
**SSOT for:** Cursor maintenance agents, `ecosystem_state.json`, post-job workflows, and standing QA digest plumbing.

**Related:** [`agent_optimization_handoff.md`](agent_optimization_handoff.md) (production pipeline) · [`.cursorrules`](../.cursorrules) §2–§5 · [`agent_architecture.md`](agent_architecture.md) §2

---

## 1. Three planes (reminder)

| Plane | Trigger | Automation level |
|-------|---------|------------------|
| **Production** | Azure timer 6 AM + 7 AM | Fully scheduled |
| **Cursor dev** | Git hooks + manual Cursor | **Partially** automated |
| **On-demand** | CLI (`finance_oversight`, `fetch_azure_reports`) | Manual |

This doc covers **Cursor dev** + **standing QA output plumbing** + **local state sync**.

---

## 2. Cursor agent inventory

| Agent | Rule file | Documented trigger | Actually automated? | Output bucket | Last activity (May 30, 2026) |
|-------|-----------|-------------------|---------------------|---------------|------------------------------|
| Action Tracker | `action_tracker.mdc` | Session start | Manual read | Human context | N/A |
| **QA Validation** | `qa_validation_agent.mdc` | Pre-commit | **Yes** — `scripts/pre_commit_check.py` | `qa_flags` | Active (multiple PASS/BLOCK entries) |
| **Refactoring** | `refactoring_agent.mdc` | Pre-commit | **Yes** — same hook | `qa_flags.refactoring_violations` | Active (0 violations recently) |
| **API Optimization** | `api_optimization_agent.mdc` | Post-job | **No** | `api_audit` | **Empty — never ran** |
| **Data Insight** | `data_insight_agent.mdc` | Post-job | **No** | `data_insights` | **Empty — never ran** |
| **Supervisor** | `supervisor_agent.mdc` | pre_push, post_job, daily | **No** (`alwaysApply` ≠ execution) | `supervisor_summaries` | **Empty — never ran** |

**Ledger path:** `.cursor/agent_state/ecosystem_state.json` (gitignored; bootstrap from `ecosystem_state.example.json`)

**CLI:** `.venv\Scripts\python.exe tools\ecosystem_state.py show --last 5`

---

## 3. Why post-job agents are dormant

`.cursorrules` §4 says API Optimization, Data Insight, and Supervisor run **after pipeline completes** — but:

1. No Azure Function, git hook, or scheduled script invokes them.
2. [`post_deliver_checklist.md`](post_deliver_checklist.md) §8 lists them as **optional manual** Cursor steps.
3. Nothing appends to `api_audit`, `data_insights`, or `supervisor_summaries` unless a human runs Cursor with those personas.

**Result:** Production runs daily; dev-plane audit trail is empty except pre-commit `qa_flags`.

---

## 4. Implementation tickets

### Ticket C1 — `fetch_azure_reports --sync-ecosystem`

| Field | Detail |
|-------|--------|
| **Problem** | `persist_scorecard()` and retrospective `_append_local_insights()` run on Azure (no local `.cursor` path) — local `qa_scorecards`, `data_insights`, `qa_human_reviews` stay empty |
| **File** | `tools/fetch_azure_reports.py` (or new `tools/sync_ecosystem_from_azure.py`) |
| **Flag** | `--sync-ecosystem` after successful fetch |

**After fetch for `run_id`, append idempotently via `tools/ecosystem_state.append_entry()`:**

| Source blob | Target bucket |
|-------------|---------------|
| `api_telemetry_{run_id}.json` → `QA_SCORECARD` | `qa_scorecards` |
| `retrospective_{run_id}.json` (state container) | `data_insights` (mirror `_append_local_insights` shape in `src/qa/retrospective.py`) |
| `qa_human_review_{run_id}.json` | `qa_human_reviews` |

**Idempotency:** skip if `run_id` already in bucket (same pattern as `retrospective._append_local_insights`).

**Add to `ARTIFACT_FAMILIES`:** `retrospective_` → `STATE_CONTAINER` (marker JSON lives in `boardroom-state`).

**Acceptance:** After `fetch --run-id X --sync-ecosystem`, `ecosystem_state.py show qa_scorecards --last 1` is non-empty.

---

### Ticket C2 — Persist standing QA digest

| Field | Detail |
|-------|--------|
| **Problem** | `src/qa_review.py` → `run_qa_review_team()` emails digest and exits — no blob, no backlog |
| **File** | `src/qa_review.py` |
| **Change (Phase A)** | After `send_qa_digest()`, save `qa_digest_{run_id}.json` to `boardroom-state` (derive `run_id` from latest telemetry filename) |
| **Change (Phase B)** | New `src/qa/digest_backlog.py` — top 3 recommendations → deduped markdown rows; optional CLI `tools/sync_digest_to_tracker.py --dry-run` |
| **Do not** auto-edit `action_tracker.md` from Azure in v1 |

**Acceptance:** After 7 AM run, `qa_digest_{run_id}.json` exists in state container.

---

### Ticket C3 — Human review feedback loop

| Field | Detail |
|-------|--------|
| **Problem** | Review UI deployed (`/api/qa-review`) but local ledger empty; retrospective at deliver time predates human review |
| **Files** | `src/qa/human_review.py`, `src/qa/retrospective.py` |

**Changes:**

1. **On `save_human_review()`** — non-blocking `execute_retrospective(run_id, force=True, write_local_insights=False)` to refresh candidates after Stan submits form.
2. **Ticket C1** — sync `qa_human_reviews` on fetch.

**Acceptance:** Submitting review form updates `retrospective_{run_id}.md` within same HTTP request; fetch sync populates local ledger.

---

### Ticket C4 — Post-job sync script (optional alternative to Cursor)

| Field | Detail |
|-------|--------|
| **File** | New `tools/post_job_sync.py` |
| **Input** | `.cache/state/api_telemetry_{run_id}.json`, debate log, qa_reports |
| **Output** | Deterministic `api_audit` + `data_insights` entries (idle agents, duplicate FMP patterns, QA CRITICAL count) |
| **Invocation** | Document in `post_deliver_checklist.md`: `fetch && post_job_sync --run-id X` |
| **Supervisor v1** | Python synthesizer reading `api_audit` + `data_insights` → one `supervisor_summaries` row (LLM optional v2) |

**Deterministic checks (v1, no LLM):**

- `AGENT_ACTIVITY` agents with `invocations==0` vs full `agent_config` roster
- Token spend ranking
- QA CRITICAL count from `qa_reports_{run_id}.json`

---

### Ticket C5 — Supervisor / post-job policy decision

| Option | Description |
|--------|-------------|
| **A (recommended)** | Implement C1 + C4 — automation without requiring Cursor chat |
| **B** | Demote to checklist-only — update `.cursorrules` §4 to say "manual only"; remove `alwaysApply` from supervisor rule |

Product owner pick before investing in LLM Supervisor synthesis.

---

## 5. Standing QA plane (7 AM timer)

**Entry:** `function_app.qa_review_daily_run` → `src/qa_review.py`

| Key | Role | Output consumer today |
|-----|------|------------------------|
| `data_flow` | Data Flow Analyst | Digest email only |
| `prompt_engineering` | Prompt Engineer | Overlaps deliver `prompt_engineer` |
| `api_health` | API Health Monitor | Digest email only |
| `tech_stack` | Tech Stack Architect | Overlaps pre-commit / refactoring |
| `finance_cost` | Finance & Cost Consultant | Digest email only |
| `opportunity_audit` | Opportunity Auditor | Digest email only |
| `graphics_designer` | Graphics Designer | Overlaps deliver `graphics_designer_qa` |
| *(injected)* | HR via `hr_review.py` | Digest HTML section |

**Consolidation backlog:** `agent_architecture.md` §9 — do not add new QA roles until overlap reduced.

---

## 6. On-demand consultants (never scheduled)

| Module | Command | Output |
|--------|---------|--------|
| `src/hr_review.py` | `python -m src.hr_review .cache/state/api_telemetry_*.json` | Utilization table + KEEP/MERGE/CUT |
| `src/finance_oversight.py` | `python -m src.finance_oversight` | `docs/finance_oversight/oversight_*.html` |

---

## 7. Pre-commit agent (working reference)

**Hook:** `.githooks/pre-commit` → `scripts/pre_commit_check.py`

**Records:**

```json
{
  "agent": "qa_validation",
  "phase": "pre_commit",
  "verdict": "PASS|BLOCK",
  "tests_passed": true,
  "staged_python_files": ["..."],
  "refactoring_violations": [],
  "evidence_ref": "scripts/pre_commit_check.py"
}
```

**Install:** `.venv\Scripts\python.exe scripts\install_git_hooks.py`

---

## 8. Validation

```powershell
# Ecosystem state
.venv\Scripts\python.exe tools\ecosystem_state.py show --last 3

# Fetch + (after C1) sync
.venv\Scripts\python.exe tools\fetch_azure_reports.py --run-id 20260529_152151
# .venv\Scripts\python.exe tools\fetch_azure_reports.py --run-id 20260529_152151 --sync-ecosystem

# Standing QA manual
.venv\Scripts\python.exe -m src.qa_review
```

---

## 9. Doc updates after implementing

| Ticket | Update |
|--------|--------|
| C1 | `post_deliver_checklist.md` §8, `DOCUMENTATION.md` machine state table |
| C2 | `qa_layers.md` standing QA section |
| C4/C5 | `.cursorrules` §4 if policy changes |
