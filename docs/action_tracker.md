# SC Invest Boardroom — Action Tracker

**Status:** Active  
**Last Updated:** May 29, 2026 (EOD — vote_engine Phase A validated on `144833`)  

This document tracks identified bugs, architectural improvements, and long-term backlog items for the SC Invest Boardroom pipeline. Items are broken down into manageable blocks with specific implementation details.

---

## Session Handoff — May 29, 2026 (vote_engine Phase A — **pick up here**)

> **Next developer — start here.** Phase A shipped and validated on production run **`20260529_144833`**. Verdict memory, per-run status, and vote math decoupling are live on `main` (`6107539`).

### Shipped & validated (May 29, 2026)

| Area | Commit / run | Detail |
|------|----------------|--------|
| **Phase A — `vote_engine`** | `6107539` | `src/core/vote_engine.py` — SSOT for Round 2 vote tallies, `VOTE_DIGEST`, chairman bypass on unanimous actionable Buy/Reduce, `apply_conviction_scores()` |
| **Python compliance expansion** | `6107539` | `compliance_audit.py` — majority alignment, originator rule, alpha pick (checklist A/D/E) before Markopolos LLM |
| **`raw_verdicts` in checkpoint** | `6107539` | `debate.json` persists structured panel JSON; deliver matrix uses JSON not markdown parse |
| **Double-run guard** | prior | `boardroom_prepare_http` → 409 when `is_run_in_flight()` |
| **Per-run status** | prior | `run_status_{run_id}.json` — phased prepare/debate/deliver (no `prepare: null` clobber) |
| **Verdict memory (implicit Pass)** | prior + **`144833`** | 21 watchlist Pass rows written to Azure `board_verdicts.json` on compliant deliver |
| **Chairman guardrails + alignment** | `01b5ed6` / `93df4ed` | Max 3 buys, 10% cap, wash-sale, majority-buy promotion (`guardrails.py`, `chairman_alignment.py`) |

### Canonical validation run — `20260529_144833`

| Check | Result |
|-------|--------|
| Deploy | `6107539` on `main` → GitHub Actions → `app-boardroom-prod` |
| End-to-end | **success** — prepare 7.9s, debate 287s, deliver 112s |
| Compliance | Approved after **1 chairman retry** (ASML 4/5 Hold, alpha pick corrected) |
| `VOTE_DIGEST` | Chairman scratchpad references pre-computed digest — no false max-3 narratives |
| `raw_verdicts` | 5 panelists in `debate.json` |
| Chairman bypass | **Not triggered** (NVDA/VRT were 3/5 majority buys, not 5/5 unanimous) — expected |
| Verdict memory | **21 Pass rows** dated `20260529` in Azure `board_verdicts.json` (explicit + implicit) |
| Human QA review | **Submitted** — all 5 agents confirmed (`qa_human_review_20260529_144833.json`) |
| Post-mortem / Prompt Engineer / Integrity | **PASS** |
| Graphics Designer | **FAIL** — 2 CRITICAL (pie chart readability — green-on-green) |

Pull artifacts: `.venv\Scripts\python.exe tools\fetch_azure_reports.py --run-id 20260529_144833`

### Vote engine — developer quick reference

| Module | Role |
|--------|------|
| `src/core/vote_engine.py` | Round 2 vote SSOT: tallies, `format_vote_digest()`, `can_bypass_chairman()`, `build_chairman_skeleton()` |
| `src/core/guardrails.py` | Financial limits after chairman (max 3, 10% cap, wash-sale) |
| `src/core/chairman_alignment.py` | Majority-buy promotion, false max-3 narrative cleanup |
| `src/core/compliance_audit.py` | Deterministic in-loop gate + vote alignment |
| `src/verdict_memory.py` | Pass cooldown writes at deliver (compliance-gated) |

**Bypass rule:** Skip chairman Pro when every symbol is vote-deterministic and all actionable Buy/Reduce mandates are **5/5 unanimous**. Majority-only days (e.g. 3/5 buy) still invoke chairman.

**Tests:** `tests/test_vote_engine.py`, `tests/test_chairman_alignment.py`, `tests/test_guardrails.py`, `tests/test_compliance_audit.py`

### Verdict memory rules (SSOT — unchanged)

1. **Write:** end of successful **deliver**, only when `debate.is_approved`.
2. **What:** watchlist **Pass** — explicit in chairman JSON **or implicit** (watchlist symbol not Buy/Strong Buy).
3. **Read:** scout at prepare — 7-day Pass cooldown (`unanimous_pass` reserved; always `false`).
4. **Not gated on:** post-flight QA CRITICAL (by design).

**Known minor issue:** `META` has duplicate Pass rows on `20260529` (earlier run + `144833`). Scout cooldown still works; dedupe is backlog P3.

### First steps next session

1. **P1 — Briefing layout:** Fix pie chart colors/contrast (`reporting.py` / QuickChart config); move State of the Union earlier — see Graphics CRITICALs on `144833`.
2. **P1 — Round 2 debate quality:** Panelists copy Round 1 overview verbatim in Round 2 (Prompt Engineer WARNING on `144833`).
3. **After each deliver:** [`post_deliver_checklist.md`](post_deliver_checklist.md).
4. **Manual pipeline kickoff:** `POST https://<defaultHostName>/api/prepare?code=<function-key>` — resolve hostname via `engineering_playbook.md` §2.

### Open items (ordered)

| Priority | Item |
|----------|------|
| ~~**P0**~~ | ~~Deploy verdict memory + per-run status + double-run guard~~ **DONE** — validated `144833`. |
| ~~**P1**~~ | ~~**Verdict memory validation**~~ **DONE** — 21 Pass rows on `144833`. |
| ~~**P1**~~ | ~~**Phase A vote_engine**~~ **DONE** — `6107539`, validated `144833`. |
| ~~**P1**~~ | ~~**State of the Union**~~ **DONE** — deterministic SoTU; validated `144833`. |
| ~~**P1**~~ | ~~**Human QA on post-fix run**~~ **DONE** — `144833`, all agents confirmed. |
| **P1** | **Briefing layout / charts** — pie chart CRITICALs, SoTU section order (`144833`; same thread as `120049`). |
| **P1** | **Round 2 prompt quality** — enforce unique rebuttal text; reduce Pass spam in logs (Systems Architect WARNING). |
| **P2** | Split `reporting.py` + extract prompts from `agents.py` |
| **P2** | Relative strength + sector weights in prepare; Buffett PE/P/S caps in Python |
| **P2** | Wire post-job Cursor agents (`api_audit`, `data_insights`, `supervisor_summaries`) |
| **P3** | Dedupe same-day `board_verdicts` rows; optional verdict memory gated on graphics CRITICAL; `unanimous_pass` 14-day cooldown |

### Archived handoffs (historical — do not pick up)

<details>
<summary>May 29 architecture cleanup (pre–vote_engine deploy)</summary>

- Run `20260529_120049`: verdict memory **not** validated (chairman omitted implicit Pass) — **fixed** in `144833`.
- Overlapping kick caused `prepare: null` — **fixed** with per-run status files.
</details>

<details>
<summary>May 29 agent/QA hardening (`e39b337`)</summary>

Human QA review UI, visual/integrity golden fixtures, QA scorecard, deterministic data oracle. See section below.
</details>

---

## Documentation index

> **Master index:** [`DOCUMENTATION.md`](DOCUMENTATION.md) — full map of all docs, SSOT rules, and when to update each file.

| Document | Use when |
|----------|----------|
| [`DOCUMENTATION.md`](DOCUMENTATION.md) | Unsure which doc to read or update |
| [`qa_layers.md`](qa_layers.md) | Which QA module runs when — deliver vs weekly vs dev |
| [`agent_architecture.md`](agent_architecture.md) | Agent diagrams, inventory, QA L0–L7 — **update when roster changes** |
| [`technical_solution.md`](technical_solution.md) | System design, data layer, deploy |
| [`engineering_playbook.md`](engineering_playbook.md) | Before retrying a rejected approach |
| [`post_deliver_checklist.md`](post_deliver_checklist.md) | After every deliver — retrospective + backlog hygiene |
| [`fmp_data_dictionary.md`](fmp_data_dictionary.md) | FMP endpoints and field map |
| [`.cursorrules`](../.cursorrules) §0.5 | **Collaboration protocol** — ask when unsure; MCQ recommended-first + free-text last |
| [`.cursorrules`](../.cursorrules) §1 | Azure `QA_REVIEW_*` app settings + correct hostname |

---

## Session Handoff — May 29, 2026 (agent/QA — detail)

> Historical detail for the agent/QA hardening session. **Current pickup:** architecture cleanup handoff above.

### Shipped this session (on `main`)

| Area | Detail |
|------|--------|
| **Commit** | `e39b337` — human QA review endpoint + deliver integration (deployed to Azure) |
| **Docs** | `0e7a31e` — session handoff, playbook Azure gotchas, `agent_architecture` human-review config |
| **Prior commits** | Oracle dedup + deterministic Python (`data_oracle.py`); visual/integrity golden fixtures; QA scorecard; `docs/agent_architecture.md` SSOT |
| **Data Oracle** | 🟢 Python price gate in prepare only; debate reuses checkpoint (no duplicate LLM) |
| **Visual QA** | `src/qa/visual_audit.py` + `tests/fixtures/visual_qa/` |
| **Integrity QA** | `src/qa/integrity_audit.py` + `tests/fixtures/integrity_qa/` |
| **QA scorecard** | `QA_SCORECARD` in telemetry; `qa_scorecards[]` / `qa_human_reviews[]` in ecosystem state |
| **Human review UI** | Azure `GET/POST /api/qa-review` (`qa_human_review` function); email button in QA dashboard |
| **Azure app settings** | `QA_REVIEW_BASE_URL` + `QA_REVIEW_TOKEN` configured (see below) |
| **Cursor** | §0.5 Collaboration Protocol; documentation habit in `.cursorrules` |

### Azure config (confirmed)

| Setting | Value |
|---------|--------|
| **Function App** | `app-boardroom-prod` · resource group `rg-boardroom-prod` |
| **Default domain** | `app-boardroom-prod-b5h4epg2d0cxefa0.eastus-01.azurewebsites.net` |
| **`QA_REVIEW_BASE_URL`** | `https://app-boardroom-prod-b5h4epg2d0cxefa0.eastus-01.azurewebsites.net` (no trailing `/api`) |
| **`QA_REVIEW_TOKEN`** | Set in portal + `.env` (do not commit `.env`) |

**Do not use** short hostname `app-boardroom-prod.azurewebsites.net` — DNS does not resolve for this Flex app.

### First steps next session (15 min)

1. Confirm GitHub Actions deploy green for `e39b337`: [workflow runs](https://github.com/stanchernov-ai/invest/actions/workflows/deploy.yml).
2. After next **deliver** run: open QA email → tap **Review QA accuracy** → confirm/save per-agent reviews.
3. Pull artifacts: `.venv\Scripts\python.exe tools\fetch_azure_reports.py --run-id <run_id>`.
4. Check `qa_human_review_<run_id>.json` in state container and `ecosystem_state.json` → `qa_human_reviews`.

### Open items (ordered)

| Priority | Item |
|----------|------|
| ~~**P1**~~ | ~~**URL-encode `token` in `build_review_url()`**~~ **DONE (May 29, 2026)** — `urlencode()` in `src/qa/human_review.py`. |
| ~~**P1**~~ | ~~**First human review on a real run**~~ **DONE (May 29)** — see Session Handoff + `qa_human_review_20260529_095341.json`. |
| **P2** | Wire post-job Cursor agents (`api_audit`, `data_insights`, `supervisor_summaries` still empty in ecosystem state). |
| **P2** | Relative strength + sector weights in prepare (FMP thread). |
| **P2** | Buffett PE/P/S caps in Python (`.cursorrules` P0). |
| **P3** | Weekly scorecard digest email; per-finding human review; consolidate overlapping QA weekly roles. |
| ~~**P3**~~ | ~~Promote chairman financial limits to full Python validators.~~ **DONE (May 29, 2026)** — `src/core/guardrails.py`: max 3 buys, 10% cap, wash-sale. |

### Reference (FMP / market data — still active backlog)

See **Session Handoff — FMP / Market Data (reference)** below and [`docs/fmp_data_dictionary.md`](fmp_data_dictionary.md).

---

## Session Handoff — FMP / Market Data (reference — not current pickup)

> Historical context; P2 FMP work continues when agent/QA thread is stable.

### Done (May 28 commit — FMP)

| Item | Detail |
|------|--------|
| **Commit** | `63730fe` on `main` → https://github.com/stanchernov-ai/invest |
| **Azure** | GitHub Actions **Deploy #20** for that commit (~2 min; check green on [workflow runs](https://github.com/stanchernov-ai/invest/actions/workflows/deploy.yml)) |
| **FMP fixes** | Dead URLs → `grades-consensus` + `earnings`; consensus/earnings/FCS live again |
| **Prompts** | Richer `mega_prompt` (PEG, P/S, D/E, beta, ROE, FCF, sector, RS vs QQQ, macro TLT/VXX, regime block) |
| **P1** | Shared `prefetch_eod_cache`; news headlines include `(YYYY-MM-DD)` |
| **Docs** | `docs/fmp_data_dictionary.md`, probe `tools/validate_fmp_fields.py`, tests under `tests/` |
| **Guardrails** | SSOT = **`.cursorrules`**; `docs/agent_guardrails.md` is pointer only |

**Not committed (local only):** `test_chart.py`, `tools/fmp_field_probe_results.json`

### First thing in the morning (15 min)

1. Confirm **Actions run #20** = green for `63730fe`.
2. Optional: trigger **prepare** once (or wait for weekday 11:00 UTC) and pull telemetry:
   * `.venv\Scripts\python.exe tools\fetch_azure_reports.py --list` then `--run-id …`
3. In `api_telemetry_*_prepare.json` confirm: `EOD_CACHE`, `grades_consensus` / `earn` not `[]`, headlines dated, FCS sometimes ≠ 0.

### Then build (P2 — recommended order)

1. **Relative strength + sector weights** in `prepare.py` / prompt (Livermore + Simons).
2. **Buffett caps in code** — conviction ≤ 7 when PE > 40 or P/S > 10.
3. ~~**Mandate TWR**~~ — **DONE (May 29):** prepare passes real 12M TWR from `account_returns` into `generate_dynamic_mandate`.
4. ~~**Macro `batch-quote`**~~ — **NOT on Starter (HTTP 402).** Keep parallel `/stable/quote` in `get_fmp_macro`; see `tools/probe_starter_tier.py`.
5. ~~**Graphics Designer on final HTML artifact**~~ — **DONE (May 29):** `run_graphics_designer_qa` reviews saved `executive_briefing_*.html` + downloaded chart images (not templates/code). Optional future: full-page email-client screenshot via headless browser.

Full API reference + dead URLs: **`docs/fmp_data_dictionary.md`**. Guardrails: **`.cursorrules`**.

---

## Session Handoff — FMP / Market Data (reference detail)

**Primary reference:** [`docs/fmp_data_dictionary.md`](fmp_data_dictionary.md) — endpoints, dead URLs, field names, excluded keys, validation commands, and the **action backlog**.

**Guardrails (personas, layers, audit tags):** [`.cursorrules`](../.cursorrules) at repo root — not `docs/agent_guardrails.md` (pointer only).

### What shipped (this commit → `origin/main` → Azure deploy)

| Area | Change |
|------|--------|
| **P0 — Dead APIs fixed** | `/stable/rating` → `grades-consensus`; `/stable/earning_calendar` → `earnings`. Consensus + next earnings + FCS work again. |
| **P0 — Prompt enrichment** | `mega_prompt` now includes PEG, P/S, D/E, beta, ROE, FCF yield, sector, analyst consensus, RS vs QQQ, % off 52w high, macro TLT/VXX, market regime block. |
| **P0 — key-metrics-ttm** | ROE + FCF yield parsed (call was previously wasted). |
| **P1 — EOD dedupe** | `prefetch_eod_cache()` once per symbol (~1095d); metrics + TWR history share cache (~30 fewer EOD calls/run). |
| **P1 — News dates** | Headlines: `[SYM] (YYYY-MM-DD): title`. |
| **Tooling** | `tools/validate_fmp_fields.py`, `tests/test_fmp_client.py`, `tests/test_eod_cache.py`. |

### Verify after deploy (next weekday run or manual prepare)

1. **GitHub Actions** — `Deploy to Azure Functions` green on latest `main` push.
2. **Prepare telemetry** (`api_telemetry_{run_id}_prepare.json`):
   * `grades_consensus` / `earn` responses **non-empty** for equities (not `[]`).
   * `EOD_CACHE` object present with `symbol_count`.
   * `historical_metrics.response` shows `"points"` > 0; URL may say `eod_cache`.
3. **Debate prompt** (checkpoint / raw log): `=== MARKET REGIME ===`, richer per-ticker KPI line, news with dates.
4. **FCS** — should occasionally be non-zero when consensus Buy + upside >15% or earnings ≤21d (was often stuck at 0 before).
5. **Local:** `.venv\Scripts\python.exe -m unittest tests.test_fmp_client tests.test_eod_cache -v`  
   `.venv\Scripts\python.exe tools\validate_fmp_fields.py`

### Next priorities (ordered — stay on this thread)

1. **P2 — Relative strength & sector concentration** — portfolio sector weight table in prompt; optional deterministic Buffett PE>40 / P>S>10 conviction cap in code.
2. ~~**P2 — Mandate math**~~ — **DONE (May 29):** real 12M TWR from `account_returns`.
3. ~~**P2 — Macro batch quote**~~ — **Rejected on Starter (HTTP 402).** Parallel `/quote` is correct for this tier.
4. **P3 — New FMP endpoints** — 10Y yield, estimate revisions (see dictionary §P3).

### Do not retry (documented dead paths)

* `GET /stable/rating`, `GET /stable/earning_calendar` (404)
* `GET /stable/earnings-calendar?symbol=X` (global feed, 0 rows per symbol)
* v3 `rating` / `earning_calendar` on Starter (403)
* JSON keys: `mktCap` (use `marketCap`), `changesPercentage` (use `changePercentage`), ROE on `ratios-ttm` (use `key-metrics-ttm`)

---

## Session Handoff — May 28, 2026 EOD (archived)

<details>
<summary>Earlier EOD notes (three-phase pipeline deploy)</summary>

* Three chained Azure Functions: prepare → debate → deliver (`1e6b2f8`).
* Verify queue chain, phase durations, briefing email, merged telemetry with `AGENT_ACTIVITY`.
* Local: `python -m src.main` or phase HTTP retriggers.

</details>

### Confirmed monthly TCO (~$285/mo)
| Service | $/mo | Source |
|---------|-----:|--------|
| Google AI Ultra (incl. API assumed bundled) | $199.99 | Stan |
| FMP Starter | $29.00 | Stan |
| Azure (pay-as-you-go + free credits) | ~$8.06 | Portal |
| Cursor Pro+ | $48.00 | Stan ($576/yr) |
| GitHub, QuickChart, Gmail, Polygon | $0 | Confirmed / assumed |

**Still unvalidated:** Gemini API truly included in Ultra (check Google invoices). Finance Oversight agent hunts hidden costs — see `docs/subscriptions_registry.json` → `possible_hidden_costs`.

### Key docs & entry points (built today)
| Doc / module | Purpose |
|--------------|---------|
| `docs/subscriptions_registry.json` | Machine-readable SaaS cost registry — **update when prices change** |
| `docs/tech_stack_and_subscriptions.md` | Human-readable stack map + TCO |
| `src/finance_oversight.py` | Standalone subscription/plan-fit consultant (`python -m src.finance_oversight`) |
| `src/hr_review.py` | Agent roster utilization (`python -m src.hr_review <telemetry>`) |
| `tools/fetch_azure_reports.py` | Pull Azure artifacts to `.cache/` |
| `docs/engineering_playbook.md` §4b | Chart/email/QA/compliance gotchas |

### Recommended next backlog (when results look good)
1. **Validate 6.1** — benchmark runtime + token cost on first post-deploy run; dial thinking budgets if needed.
2. **5.2 Opportunity Audit** — coverage matrix of paid FMP fields vs. what agents consume.
3. **3.2 Cursor rules** — `.cursor/rules/architecture_validator.mdc` for PR/architecture review.
4. **5.3 Storage housekeeping** — configurable retention, telemetry blob cost.
5. **Finance automation** — Azure Cost Management API pull into registry (moving costs).
6. **Merge/commit local WIP** — `test_chart.py` if still relevant; commit EOD doc updates.

### Known open issues to watch
* Some historical runs have **no `qa_dashboard_*` blob** (pipeline may abort before QA HTML step) — confirm fixed on next success run.
* **`reconcile_compliance()`** now forces ❌ if any CRITICAL finding exists — Graphics Designer may correctly fail until layout issues are resolved.
* Azure **free trial credits** will eventually expire — watch Cost Management forecast.

---

## Phase 0: Runtime Architecture — Three-Phase Split

### 0.1 Split monolithic run into prepare → debate → deliver — DONE (code complete, May 28, 2026)
* **Problem:** A single Azure Function ran data prep + board debate + all QA + email in one invocation. With the QA Integrity auditor on Pro reading the full debate log + dashboard, runs hit **~13 min locally and the hard 10:00 Azure ceiling**, getting killed mid-QA (run `20260528_231049`). One opaque log made it hard to tell *where* it broke.
* **Decision (Stan, Option A):** Split into **three independent functions**, each with its own 10-minute budget, chained so one kicks off the next. Smaller files, and a failure localizes to a phase.
* **Architecture:**
  * **Job 1 `prepare`** (`src/jobs/prepare.py`) — sync inputs, parse ledger, FMP metrics/news/macro, TWR returns, build the board mega-prompt. **Prepare-phase price gate** = deterministic Python (`src/core/data_oracle.py`); corrupt $0 prices fail Job 1 before debate tokens. Writes `runs/{run_id}/prepare.json` checkpoint (includes `oracle`, `price_feed`).
  * **Job 2 `debate`** (`src/jobs/debate.py`) — the board engine (`engine.app.astream`): panel, rebuttal, synthesis, Munger, chairman + deterministic 10% cap, **compliance gate**. Writes `runs/{run_id}/debate.json`. No rendering/email.
  * **Job 3 `deliver`** (`src/jobs/deliver.py`) — render briefing + QA dashboard, **post-work QA**, email both, merge telemetry. 
* **QA trims (first cuts, per Stan "non-crucial QA like graph first"):**
  * **Graphics QA is now deterministic** (`qa_pipeline.build_graphics_report`) — built straight from the chart-health HTTP probe, **no LLM**. (The LLM reviewer never actually saw images.)
  * **QA Integrity auditor → Flash + hard 90s timeout** (`qa_pipeline.run_qa_integrity_audit`). On timeout it emits a non-blocking WARNING instead of killing the run or false-failing QA.
  * Post-flight trio (post-mortem / systems architect / prompt engineer) unchanged, still parallel.
* **Chaining:** **Azure Storage Queues** (non-blocking). `prepare` → `boardroom-debate-queue` → `debate` → `boardroom-deliver-queue` → `deliver`. Each queue message carries the `run_id`. Queues auto-created by the output binding. Timer (11:00 UTC weekdays) starts `prepare` only.
* **Manual/recovery entrypoints:** HTTP routes `/api/prepare`, `/api/debate?run_id=...`, `/api/deliver?run_id=...`, `/api/retrospective?run_id=...` (FUNCTION auth) to force a run, **re-run a single phase**, or re-run retrospective. Local end-to-end: `python -m src.main` (runs all three in-process via `src/jobs/orchestrate.py`).
* **run_status is now phased:** single `run_status.json` with `phase` + per-phase `{status, started_at, finished_at, duration_seconds, error}` sub-objects. Overall `status` stays `running` until `deliver` succeeds (so `wait_for_run.py` still works) and flips to `failed` on any phase failure. Each phase also self-aborts at a **540s soft timeout** so a host kill records `failed` instead of a stale `running`.
* **Sync fix:** `sync_inputs_from_cloud()` now pulls only a curated state allowlist (`board_verdicts`, `portfolio_history`, `portfolio_returns`, `run_status`) instead of **every** historical `api_telemetry_*.json` — removes tens of seconds + cold-start FMP rate-limit pressure.
* **Telemetry:** each phase writes `api_telemetry_{run_id}_{phase}.json`; `deliver` merges all three (summing per-agent activity) into the canonical `api_telemetry_{run_id}.json` so HR/finance consumers keep working.
* **NEW shared modules:** `src/qa_pipeline.py` (moved QA + matrix helpers out of `main.py`), `src/logging_setup.py`, `src/jobs/` package. `main.py` is now a thin local wrapper.
* **Verify on deploy (TODO):**
  1. Add app setting **function/host key** is not required for queue chaining, but confirm `AzureWebJobsStorage` is set (it is — app already runs).
  2. First run: `prepare` completes (~1–2 min), debate queue message appears, `debate` runs (~5 min), deliver queue message, `deliver` emails briefing + QA dashboard. Watch each phase < 10 min.
  3. Confirm queue messages decode as plain `run_id` (extension-bundle base64 behavior) — if `debate`/`deliver` see empty run_id, set the queue message encoding or switch to explicit `QueueClient`.
  4. `api_telemetry_{run_id}.json` contains merged `AGENT_ACTIVITY` from all phases.
* **Not yet committed/deployed** as of this writing — review diff first.

---

## Phase 1: Immediate Bug Fixes & Hygiene

### 1.1 Azure Blob Lease Duration (Concurrency Fix) — DONE (May 28, 2026)
* **Description:** The current blob lease duration is 60 seconds, but the pipeline takes longer. This risks a second instance acquiring the lock and running concurrently.
* **Implementation Details:** 
  * Update `function_app.py` to acquire the lease for the maximum allowed time or a duration that covers the Azure Function timeout (10 minutes for Consumption plan). 
  * *Note:* Azure Blob Storage leases can be set to 15-60 seconds, or infinite (`-1`). We will set it to `-1` (infinite) upon acquisition.
  * Wrap the `main_batch()` execution in a strict `try/finally` block to ensure `lease_client.release()` is *always* called, even if the pipeline crashes, so the lock isn't permanently stuck.
* **Resolution:**
  * Updated `function_app.py` to use `lease_duration=-1` and added a `try...finally` block.

### 1.2 Munger Audit Results Discarded — DONE (May 28, 2026)
* **Description:** `execute_munger_audit()` runs but its output is never passed to the Chairman, wasting tokens and losing valuable concentration risk analysis.
* **Implementation Details:**
  * In `src/core/engine.py`, capture the output of the `asyncio.gather(*tasks)` for the Munger audit.
  * Format the results into a string (e.g., `"MUNGER AUDIT WARNINGS: ..."`).
  * Inject this string dynamically into the `chairman` prompt during `execute_chairman_arbitration()`.
* **Resolution:** 
  * Updated `execute_munger_audit` to save results to `self.state.munger_overrides`.
  * Updated `execute_chairman_arbitration` to inject `[CRITICAL MUNGER AUDIT CONCENTRATION WARNINGS]` if present.

### 1.3 Hardcoded Temporary Paths — DONE (May 28, 2026)
* **Description:** The codebase uses `/tmp/data` and `/tmp/output`, which causes issues on Windows development environments.
* **Implementation Details:**
  * Update `src/pipeline.py`, `src/storage_client.py`, `src/scout.py`, and `src/main.py`.
  * Replace hardcoded `/tmp/` strings with Python's `tempfile.gettempdir()` or a centralized `DATA_DIR` and `OUTPUT_DIR` defined in `src/config/settings.py` (e.g., resolving to a local `.workspace/` folder during dev, and `/tmp/` in prod).
* **Resolution:**
  * Added module-level `DATA_DIR` / `OUTPUT_DIR` to `src/config/settings.py`. Defaults to `/tmp/...` on POSIX (Azure Linux) and `tempfile.gettempdir()/...` on Windows; both overridable via `BOARDROOM_DATA_DIR` / `BOARDROOM_OUTPUT_DIR` env vars.
  * Replaced all 10 hardcoded `/tmp/` references across `pipeline.py`, `storage_client.py`, `scout.py`, and `main.py` to import and use the centralized constants.
  * *Caveat:* `pipeline.py` and `scout.py` now import from `src.config.settings`, so running them as standalone scripts requires module-style execution (`python -m src.scout`). They run normally through `main_batch` / `function_app`.

### 1.4 Missing API Key Validation — DONE (May 28, 2026)
* **Description:** `GEMINI_API_KEY` is not validated at startup, causing deep asynchronous failures if missing.
* **Implementation Details:**
  * Add `GEMINI_API_KEY` to the `Settings` class in `src/config/settings.py`.
  * Update `Settings.validate()` to check for it and abort immediately if missing.
* **Resolution:**
  * Added `GEMINI_API_KEY` to `Settings` and as the first check in `Settings.validate()` so the pipeline fails fast (`settings.validate()` is called at the top of `main_batch`).

---

## Phase 2: Architectural Improvements

### 2.1 Move 10% Liquidation Cap Math to Python — DONE (May 28, 2026)
* **Description:** The Chairman LLM is currently asked to calculate exactly 10% of the portfolio and execute fractional trims. LLMs struggle with deterministic math, risking compliance failures.
* **Implementation Details:**
  * Update the Chairman's prompt to remove the strict math requirement. Instead, ask the Chairman to *rank* his preferred sell/trim candidates and specify the new assets he wants to buy.
  * In `src/core/engine.py` (or a helper utility), intercept the Chairman's output *before* Compliance.
  * Use Python to calculate exactly 10% of `total_portfolio_value`.
  * Iterate through the Chairman's ranked sell list, trimming positions programmatically until the 10% cap is reached or the buys are funded.
  * Pass this mathematically validated execution plan to the Compliance agent.
* **Resolution:** 
  * Updated Chairman's system prompt.
  * Enforced mathematical validation inside `execute_chairman_arbitration` in `src/core/engine.py`.

### 2.2 Global Error Notifications (Silent Failures) — DONE (May 28, 2026)
* **Description:** If the pipeline aborts (e.g., Data Oracle fails, FMP crashes), it exits silently without notifying the user.
* **Implementation Details:**
  * Add a `send_error_alert(error_message: str)` function to `src/output/notifier.py`.
  * In `src/main.py`, wrap the core logic of `main_batch()` in a global `try/except`.
  * On caught exceptions (or explicit `FatalDataError`), trigger the error alert email so the user is immediately aware of the failure.
* **Resolution:**
  * Added `send_error_alert` to `notifier.py`.
  * Handled `DATA ORACLE`, `Compliance`, `Advanced metrics`, and generic fatal exceptions in `src/main.py` via `notifier.send_error_alert`.

### 2.3 Replace yfinance 3M Momentum with FMP — DONE (May 28, 2026)
* **Description:** `yfinance` was used for the 3M trend but is prone to rate-limiting and scraping blocks. FMP is preferred but has tier limits and deprecated endpoints.
* **Implementation Details:**
  * **Action:** Create an isolated test script (e.g., `tests/test_fmp_historical.py`).
  * Test FMP's `/api/v3/historical-price-full/{symbol}` endpoint using the Starter Tier API key.
  * Validate if it supports the required throughput without hitting 429s.
  * *Decision Gate:* If successful, refactor `fetch_momentum_trend` in `fmp_client.py` to use FMP. If it fails tier limits, keep `yfinance` as the primary with enhanced error handling.
* **Root cause (confirmed from live run `20260528_195832` telemetry):** Every `3m_momentum` returned `"N/A"` from yfinance, so `3M Trend` rendered as `0.00%` for all assets. This broke Livermore's momentum strategy (blanket Sell/Pass) and skewed the debate.
* **Resolution:**
  * Endpoint validation against the live starter-tier key: `stable/historical-price-eod/light` and `.../full` both return **HTTP 200** (~67 trading days for a 95-day window); the legacy `v3/historical-price-full` returns **403** (deprecated / not on starter tier).
  * Refactored `fetch_momentum_trend` in `fmp_client.py` to call `stable/historical-price-eod/light` via the existing `aiohttp` session + `fetch_json_endpoint` (so it inherits `tenacity` retry/backoff). Records are newest-first; trend = `(price[0] - price[-1]) / price[-1] * 100`. Signature changed to `(symbol, api_key, session, telemetry)`; call site updated.
  * **Removed yfinance from the momentum path** entirely. Telemetry now records `source: fmp_stable_eod_light` with the redacted URL. (`fetch_yfinance_fallback` remains only as a last-resort fundamentals net when FMP profile/quote fails.)
  * Verified locally against live FMP: NVDA +11.85%, AVGO +29.13%, GOOGL +25.25%, META −0.31%, SPY +10.59%, QQQ +22.31%, MNDY +10.49%.
* **Follow-up (optional):** `3y_cagr` is still hardcoded `"N/A"`; the same EOD endpoint with a wider window could populate it. yfinance remains a dependency only for the fundamentals fallback — a future cleanup could drop it if FMP proves consistently sufficient.

---

## Phase 3: Observability, Tooling & Agent Access

### 3.1 Provide AI Agents Access to Azure Outputs — DONE (May 28, 2026)
* **Description:** Allow Cursor agents to read historical reports, debate logs, and telemetry stored in Azure Blob Storage to provide weekly feedback and performance analysis.
* **Implementation Details:**
  * Create a utility script (e.g., `tools/fetch_azure_reports.py`) that uses `azure-storage-blob` to download the latest files from the `boardroom-reports` and `boardroom-state` containers to a local `.cache/` directory.
  * The Cursor agent can then be instructed to run this script via the Shell tool and read the resulting files to analyze past performance.
* **Resolution (2026-05-28):** Added `tools/fetch_azure_reports.py`. Reuses the pipeline's `get_blob_service_client` + container constants (DRY auth via `AZURE_STORAGE_CONNECTION_STRING`). Downloads timestamped artifact families (`executive_briefing_`, `qa_dashboard_`, `raw_debate_log_`, `api_telemetry_`) plus the current state singletons (`run_status`, `portfolio_history`, `portfolio_returns`, `board_verdicts`) into `.cache/{reports,state}/` and writes a `manifest.json`.
  * Flags: `--list` (enumerate run IDs, no download), `--latest N` (N of each family, default 1), `--run-id YYYYMMDD_HHMMSS` (one coherent run), `--out`, `--no-state-singletons`. Exit codes 0/2/3.
  * Run from repo root via the venv: `.venv\Scripts\python.exe tools/fetch_azure_reports.py`. `.cache/` is gitignored.
  * **Verified live:** `--list` returned 23 runs; default fetch pulled 8 files (~840 KB) and wrote the manifest. Unblocks Phase 5 (QA review team reading real outputs).

### 3.2 Cursor Architecture & QA Agents
* **Description:** Create specialized agent workflows/rules to validate architecture changes and analyze portfolio performance.
* **Implementation Details:**
  * Create a `.cursor/rules/architecture_validator.mdc` file defining how the agent should review PRs or structural changes against the `technical_solution.md`.
  * Define prompts for weekly performance analysis (e.g., comparing `portfolio_history.json` trends against the debate logs).

### 3.3 Run Completion Signal (No More Blind Polling) — DONE
* **Description:** Replace agent `sleep` + blob-list guessing with a deterministic completion contract so deploy/run monitoring is efficient and reliable.
* **Problem:** Azure cannot push notifications into Cursor. Prior workflow used fixed waits and listed blobs hoping new files appeared — racey and slow.
* **Resolution (2026-05-28):**
  * Pipeline writes `boardroom-state/run_status.json` at run start (`running`) and in `finally` (`success` / `failed` / `aborted`) with `run_id`, timestamps, duration, artifact names, and error detail.
  * Added `scripts/wait_for_run.py` — polls with exponential backoff (15s → 60s), exits 0/1/2/3. Documented in `engineering_playbook.md`.
  * **Deploy monitoring:** use `gh run watch --exit-status` (no sleep).
  * **Run monitoring:** capture `--run-id` at trigger time, then `wait_for_run.py --run-id …`.
* **Deferred:** optional GitHub Actions post-deploy smoke job that triggers + waits automatically; failure email alert (cross-ref 2.2).

---

## Phase 4: Reporting & Visual Formatting

Reference briefing: `executive_briefing_20260528_204417.html` (Azure `boardroom-reports`).

### 4.1 Guarantee Multi-Paragraph Debate — DONE (May 28, 2026)
* **Description:** The "Debate" section should render as multiple paragraphs, not one long block.
* **Finding:** The renderer (`reporting.py`) already splits `boardroom_brawl` on newlines, and the `clerk` prompt asks for "exactly 3 paragraphs" — so 204417 renders correctly. However, the `ChiefOfStaffSynthesis.boardroom_brawl` **schema description** contradicted the prompt ("3-4 sentence narrative"), risking a single-blob regression if the model follows the schema.
* **Resolution:** Updated the `boardroom_brawl` field description in `src/core/schemas.py` to explicitly require exactly 3 newline-separated paragraphs (`\n\n` between them), aligning schema with prompt so paragraph layout is guaranteed rather than incidental.

### 4.2 Per-Account Asset Allocation Pie Charts — DONE
* **Description:** Keep the existing total-portfolio pie chart, and add a second visual breaking allocation out **per account** (side-by-side pies) so Stan can see performance/allocation by account.
* **Data availability (CONFIRMED):** All four requested accounts exist in the input data:
  | Account | Source |
  |---------|--------|
  | eTrade Taxable | `etrade_taxable.csv` |
  | eTrade Roth IRA | `etrade_roth.csv` |
  | Fidelity 401K | `fidelity_portfolio.csv` → `Account Name` in {`WORKDAY 401(K)`, `BrokerageLink`} |
  | Fidelity Roth 401K | `fidelity_portfolio.csv` → `Account Name` = `BrokerageLink Roth` |
* **Required changes:**
  1. **Data model (`pipeline.py`):** Today the ledger collapses to 3 buckets (`Taxable`/`Roth`/`401K`) and mis-files all Fidelity holdings as "Taxable" (filename has no roth/401k token). Refactor `parse_broker_csv` / `process_portfolios` to tag each position with a specific account key (eTrade Taxable, eTrade Roth, Fidelity 401K, Fidelity Roth 401K), using the Fidelity `Account Name` column and the eTrade filename.
  2. **Parsing caveat:** Exclude the Fidelity `$85,728.18 "BROKERAGELINK"` aggregate/sweep line from `WORKDAY 401(K)` to avoid double-counting against the individual BrokerageLink holdings.
  3. **Reporting (`reporting.py`):** Add a `build_account_pie_charts(...)` helper producing up to 4 QuickChart pie URLs, and render them side-by-side under "Asset Allocation" (email-client-safe layout, e.g., a 2x2 table of images).
* **Decision (confirmed with Stan):** Fidelity 401K = `WORKDAY 401(K)` + `BrokerageLink`; Fidelity Roth 401K = `BrokerageLink Roth`.
* **Resolution (2026-05-28):** Added `pipeline.build_account_holdings()` — an independent re-parse of the input CSVs that groups symbol-level holdings into the 4 accounts (eTrade by filename, Fidelity by `Account Name` column), avoiding the unreliable filename-derived `Taxable/Roth/401K` ledger buckets. Added `reporting.build_account_pie_charts()` (smaller 400x300 outlabeledPie per account, colored by per-account return) and a new "Allocation by Account" section rendered as a 2-per-row table via Jinja `batch(2)`. Wired through `main.py`. Verified end-to-end against the live Azure input CSVs: all 4 accounts populate correctly and QuickChart returns `200 image/png`.
* **Note for Stan:** Each account pie shows **securities held** (value > $1,000), consistent with the existing total pie. The Fidelity 401K's large symbol-less `BROKERAGELINK` sweep line (~$85K uninvested) and the $2 VANG money-market are intentionally excluded, so the 401K pie reflects the BrokerageLink securities (TSM/ANET/NVDA), not the full account cash balance.

### 4.3 Action Plan "Verdict Pill" Restyle — DONE
* **Description:** Restore the preferred Action Plan layout (confirmed via Stan's reference screenshot, saved at `assets/...image-bf0ed61d...png`).
* **Target layout (per position):**
  1. A **colored rounded pill** reading `VERDICT : TICKER` (e.g., `STRONG BUY : META`) — green for Strong Buy/Buy, neutral/gray for Hold, amber/red for Trim/Sell. This replaces the current plain `<h3>CATEGORY</h3>` header + `<h4>TICKER</h4>`.
  2. `**Strategic Context:**` paragraph (unchanged content, uses `pos.synthesis`).
  3. `**The Champion (Name):**` "quote" — champion name wrapped in **parentheses** (currently rendered without parens).
  4. `**The Dissent (Name):**` "quote" — e.g., `The Dissent (None): "N/A"` when unanimous.
  5. A thin horizontal divider between positions.
* **Delta vs current `reporting.py` template (lines ~285-300):**
  * Swap the category `<h3>`/ticker `<h4>` structure for a per-position pill badge built from `category` + `pos.symbol`, while keeping the existing category sort order (STRONG BUY → BUY → HOLD → TRIM → SELL).
  * Wrap `pos.narrative.champion` / `dissenter` names in parentheses.
  * Reuse existing `.champion` (green) / `.dissenter` (red) CSS; add a small pill style with verdict-based background color (inline styles for email-client safety).
* **Scope:** Template-only change in `generate_html_briefing` (no data-model impact). Pairs well with the 4.2 chart work.
* **Resolution (2026-05-28):** Updated `src/output/reporting.py`. Added a `.verdict-pill` CSS class and a `pill_styles` Jinja map (green = Strong Buy/Buy, gray = Hold, amber = Trim, red = Sell/Strong Sell). Replaced the `<h3>CATEGORY</h3>` + `<h4>TICKER</h4>` structure with a single per-position pill (`CATEGORY : TICKER`), wrapped Champion/Dissent names in parentheses, and added a divider between positions. Verified via isolated Jinja render.

### 4.4 Time-Weighted Returns (YTD + Trailing 12M, per Account) — DONE
* **Description:** Stan wants real performance returns (not just unrealized gain) — YTD and trailing-12-month, for the total portfolio and each account — reconstructed from trade activity since we lack a balance history.
* **Decisions (confirmed with Stan):**
  * **Methodology:** Time-Weighted Return (flow-neutral; the standard "how am I doing" metric). Neutralizes deposits, withdrawals, 401(k) contributions, and trades.
  * **Window:** Trailing 12 months (YTD derived from the same series).
  * **Basis:** Securities only (consistent with the value/pie numbers); reinvested dividends treated as share additions, not return.
* **How it works:** Anchored on today's actual per-account holdings, the engine walks the brokerage activity files backward (signed share events) to reconstruct shares held on every past trading day, values them with FMP EOD closes, and daily-links each day's price-only return: `r_t = Σ(shares_overnight × Δprice) / value_yesterday`. Cumulative product → YTD and 12M. Computed per account and aggregated to Total.
* **Self-healing backfill:** The full trailing window is recomputed from source every run, so a missed run (or a missed week) is automatically caught up on the next execution — no separate gap-fill job needed.
* **Resolution (2026-05-28):**
  * New `src/history.py` — `parse_share_events()` (eTrade by activity filename, Fidelity by per-row `Account` column) + `build_account_returns()` (async TWR engine, concurrency-capped at 5 FMP calls, share-class ticker normalization e.g. `BRK.B`→`BRK-B`, fully non-fatal).
  * New `fetch_price_series()` in `src/data/fmp_client.py` (reuses the proven `stable/historical-price-eod/light` feed).
  * `pipeline.build_account_holdings()` now also returns per-symbol `shares` (the TWR anchor).
  * `reporting.py` renders a **Time-Weighted Returns** table (Total + 4 accounts, YTD + 12M, green/red) near the top of the briefing.
  * `main.py` computes returns inside the existing aiohttp session and persists `portfolio_returns.json` to blob.
  * **Verified end-to-end** against live Azure CSVs: 254 trading days reconstructed; daily total grew $11K→$155K over the year while TWR correctly reported **Total +38.26% (12M) / +9.68% (YTD)** — confirming contributions are excluded. Engine runtime ~33s.
* **Possible follow-ups:** money-weighted (XIRR) view; benchmark the 12M line chart against the new daily-total series; surface a small per-account sparkline.

### 4.5 Chart Rendering & Report Flow Fixes — DONE (May 28, 2026)
* **Description:** On the live briefing the charts looked broken/ugly: the benchmark line chart rendered as a broken image, and chart titles appeared *beside* their charts instead of on top. Stan also wanted the report to flow better — move the Time-Weighted Returns table to the bottom at ~half width, and replace the verbose end-of-report QA summary with a compact agent + PASS/FAIL icon list.
* **Root causes:**
  * **Header beside chart:** the briefing used `display:flex; flex-direction:column`. Gmail/Outlook strip flexbox, collapsing the column into a row so the `<h2>` rendered next to the image.
  * **Broken line chart:** `get_quickchart_short_url` had no timeout/retry, so on a failed POST it fell back to a giant inline GET URL with the whole config encoded. Only the line chart (~250 history points → largest config) blew past URL limits; the small pie/bar fallbacks survived.
* **Resolution (`src/output/reporting.py`, `src/main.py`):**
  * Rewrote both chart sections as **email-safe `<table>` layouts** — chart title is its own block stacked directly above the `<img>`. Removed all `flex`/`object-fit`. Added `.chart-title` CSS.
  * Hardened `get_quickchart_short_url`: 15s timeout + one retry, sends `width/height/backgroundColor:white/devicePixelRatio`, only falls back to the inline GET URL as a last resort.
  * Added `_downsample()` — the benchmark line series is capped to ~90 evenly-spaced points (identical-looking line, small payload).
  * Extracted `build_briefing_charts()` so URLs are built **once** and reused for both rendering and health checks; `generate_html_briefing` accepts a `chart_urls` kwarg.
  * **Report flow:** moved the Time-Weighted Returns table from near the top to just above the footer, constrained to ~55% width (paired empty cell) so it reads as intentional rather than a sparse full-width strip.
  * **Compact QA footer:** replaced the verbose per-agent summary with `<strong>Agent</strong> ✅/❌` only, plus a "see the QA Audit Dashboard for details on any ❌" hint.
* **Verified:** isolated Jinja render — headers precede their images, no flexbox, table-based layout, returns table sits above the footer at half width, QA footer is icon-only.

---

## Phase 5: Standing QA Review Team & Cost Governance

**Goal:** A recurring, multi-specialist review of the *framework itself* (code, logs, data, cost) that produces consolidated recommendations — distinct from the existing per-run debate QA.

**What already exists (build on, don't duplicate):**
* In-pipeline post-flight QA (`run_post_flight_qa` in `main.py`) already runs three reviewers against each run's debate log: `post_mortem_qa` (procedural), `system_architect` (technical/data-structure), `prompt_engineer` (persona drift). These review a *single run's output*, not the framework over time.
* `storage_client.execute_retention_policy(days_to_keep=14)` already purges blobs older than 14 days from the state/report containers (protecting `daily_execution.lock`, `board_verdicts.json`, `portfolio_history.json`).
* Phase 3.2 (Cursor Architecture & QA Agents) is the natural home for implementing these as Cursor subagents/rules on a weekly cadence.

### 5.1 Specialized QA Review Team — PARTIAL (May 28, 2026)
A team of focused reviewers, each producing a short scored report + prioritized recommendations. Originally proposed as Cursor subagents on a weekly cadence; **partially implemented as an Azure timer job.**

| Reviewer | Focus | Status |
|----------|-------|--------|
| **Data Flow** | Ingestion → ledger → report integrity | In `src/qa_review.py` QA_TEAM_CONFIG |
| **Prompt Engineering** | Persona drift, sycophancy | In QA_TEAM_CONFIG |
| **APIs** | Endpoint health, 429s | In QA_TEAM_CONFIG |
| **Tech Stack** | Pipeline structure, deploy health | In QA_TEAM_CONFIG |
| **Finance / Cost** | Per-run duration optimization | In QA_TEAM_CONFIG (distinct from 5.7 subscription oversight) |
| **Opportunity Audit** | Unused data fields | In QA_TEAM_CONFIG |
| **Graphics Designer** | Briefing visual polish | In QA_TEAM_CONFIG + in-pipeline `graphics_designer_qa` (5.5) |
| **HR Efficiency** | Agent roster right-sizing | **5.4** — wired into digest via `hr_review.py` |

* **What runs today:** `function_app.py` timer **7:00 AM daily** (Pacific via `WEBSITE_TIME_ZONE`) → `run_qa_review_team()` → emails QA digest. Pipeline timer **6:00 AM daily** → prepare. Fetches latest blobs from Azure; includes HR section when `AGENT_ACTIVITY` present in telemetry.
* **Still open:** Cursor subagent/rules wrapper (3.2), weekly digest log in `docs/qa_reviews/`, orchestrating as a "QA Lead" skill.

### 5.2 Opportunity Audit — Value per API Call — IN PROGRESS
* **Description:** Stan's concern: "leaving gold on the ground." Audit each agent and each paid data field to ensure we're using what we pay for.
* **Done (2026-05-28):**
  * **`docs/fmp_data_dictionary.md`** — stable endpoint/field reference, known bad URLs, fields to exclude, action backlog.
  * **`tools/validate_fmp_fields.py`** — live probe script (re-run after FMP plan changes).
  * **P0 code fix:** dead `/stable/rating` → `grades-consensus`; dead `/stable/earning_calendar` → `earnings`; parse `key-metrics-ttm` (ROE, FCF yield); empty-list yfinance fallback; extended `mega_prompt` (PEG/P/S/D/E, beta, sector, RS vs QQQ, macro TLT/VXX); dedupe SPY/QQQ fetches in prepare.
  * **`tests/test_fmp_client.py`** — smoke tests (consensus + earnings populated for AAPL).
* **P1 done (2026-05-28):** shared EOD prefetch in prepare (`prefetch_eod_cache`); news headlines include `publishedDate`.
* **Still open (P2+):** Buffett deterministic caps, relative strength / sector weights — see `docs/fmp_data_dictionary.md`. Mandate TWR done; batch-quote blocked on Starter (402).

### 5.3 Azure Storage Housekeeping & Cost Control — PLANNED
* **Description:** A dedicated "clean house" routine to delete older Azure files and keep monthly storage cost down. Stan wants this more deliberate than the current passive retention.
* **What exists:** `execute_retention_policy(14)` runs at the end of every pipeline run.
* **Enhancements to consider:**
  * Make retention window configurable (env var) and tier-aware (e.g., keep last N briefings regardless of age; aggressively purge large `api_telemetry_*.json` sooner — those are ~700 KB each).
  * Optionally move cold artifacts to a cheaper access tier (Cool/Archive) instead of deleting, if history is valuable.
  * A standalone Cursor/maintenance task (or scheduled function) to report current storage footprint + projected monthly cost and prune on demand.
  * Verify the deployment storage account (`rgboardroomprod93bf`) isn't accumulating old build artifacts.

### 5.4 HR Efficiency Consultant — DONE (May 28, 2026)
* **Description:** A meta-governance reviewer that keeps the *agent roster itself* lean as we keep adding agents. Stan's concern: "I think we almost need an HR Efficiency Consultant to ensure we are not using unneeded agents." Tracks activity across all agents and reports on team efficiency, redundancy, and gaps.
* **Distinct from 5.2 (Opportunity):** Opportunity maximizes value extracted from each *API call/data field*; HR right-sizes the *headcount* — eliminating redundant/idle/low-impact agents and recommending new roles only where they add clear value.
* **What it tracks:**
  * **Utilization** — which agents actually fire each run, how often, and their token/cost footprint (from telemetry + debate logs).
  * **Redundancy** — agents whose outputs overlap or are never consumed downstream (e.g., results discarded like the historical Munger-audit issue).
  * **Impact** — does an agent's contribution change a verdict/outcome, or is it decorative?
  * **Gaps** — missing roles that would materially improve decisions or governance.
* **Output:** A per-period "org chart + utilization report" — table of agent → invocations → token cost → consumed-by → keep/merge/cut recommendation, plus proposed new roles. Feeds the weekly QA digest.
* **Implementation notes:** Likely a Cursor subagent reading the agent roster (`agents.py`), per-run debate logs, and telemetry. Needs lightweight per-agent activity logging if not already captured (tie into Phase 3.1 fetch + telemetry).
* **Resolution (2026-05-28):** Built the missing **deterministic per-agent activity logging** first, then the consultant on top of it.
  * **New `src/core/agent_activity.py`** — an in-memory ledger (`reset`/`record`/`snapshot`). `call_gemini_async` (the single LLM chokepoint) now records every invocation's model + token usage (prompt/output/thinking) + errors, keyed by the `agent_name` config key (`_run_agent` already passes `agent_key`). `main.py` calls `agent_activity.reset()` at run start and snapshots into `api_telemetry['AGENT_ACTIVITY']` in the `finally` block — 3 surgical lines + 1 import, so it composes cleanly with concurrent edits.
  * **New `src/hr_review.py`** — `build_utilization()` merges the **full configured roster** with the activity ledger so **idle agents (0 invocations) are surfaced**, computes an estimated USD cost (rough Gemini 2.5 pricing constants, clearly labeled — tokens are the source of truth), and sorts by cost. Text + HTML renderers, plus `run_hr_efficiency_review()` (HEAVY model, `HRReport` schema: per-agent KEEP/MERGE/CUT/ADD_BUDGET/WATCH verdict, redundancies, proposed new roles, roster-health 1-5). The LLM gets the deterministic table as ground truth — it never guesses who fired.
  * **Wired into the standing QA digest (`qa_review.py`):** removed the old generic `hr_efficiency` stub from `QA_TEAM_CONFIG`; the digest now parses `AGENT_ACTIVITY` from the latest telemetry, runs the consultant, and renders the utilization table + verdicts at the top of the digest.
  * **Standalone:** `python -m src.hr_review <telemetry.json>` prints the utilization table (pairs with the 3.1 `.cache/` fetch).
  * **Verified:** roster-merge/idle-detection/cost/sort and the HTML+digest rendering all confirmed via isolated tests. Live AGENT_ACTIVITY will populate on the next pipeline build (runs predating this change won't have it).
* **Latency:** zero added cost to the per-run pipeline (logging is in-memory); the LLM consultant runs only in the separate QA digest process.

### 5.5 Graphics Designer — DONE (in-pipeline) (May 28, 2026)
* **Description:** A design-focused reviewer/agent whose sole job is to make the final report "amazing." Stan: "want a graphics designer agent to make sure final report is amazing."
* **Scope:**
  * Visual hierarchy, typography, spacing, and color consistency across the HTML briefing.
  * Chart quality and legibility (pie/bar/line) — labels, contrast, sizing, the new per-account grid (4.2), and the verdict pills (4.3).
  * Rendering robustness across email clients and browsers (inline styles, table-based layouts, image fallbacks for QuickChart).
  * Brand/polish: header, section dividers, mobile/responsive behavior.
* **Resolution (2026-05-28):** Implemented as the **in-pipeline `graphics_designer_qa` agent** (`run_graphics_designer_qa` in `main.py`) rather than a weekly Cursor subagent, so it gates every run.
  * **Broken-chart detection:** the agent can't "see" rendered images, so `reporting.audit_chart_health()` HTTP-probes every chart URL (status + content-type) and feeds a deterministic CHART HEALTH REPORT into the prompt as ground truth. Any BROKEN chart is a CRITICAL finding.
  * **Sharpened instructions (`agents.py`):** now explicitly audits for email-unsafe CSS (flex/grid/object-fit), header-beside-chart, missing alt text, **report flow / section ordering**, and **element sizing/balance** (e.g. a narrow table stretched full width).
* **Follow-up (optional):** a *weekly* design subagent that critiques trends across many briefings (vs. the per-run gate) once Phase 3.1 fetch exists.

### 5.6 QA Integrity Auditor (QA-of-the-QA) & Deterministic Compliance — DONE (May 28, 2026)
* **Description:** Stan: "we need a QA to QA that QA dashboard" — validate the QA dashboard actually matches what happened and that the QA agents' own verdicts were accurate. Also fixes a trust bug where an agent self-reported ✅ PASS while logging CRITICAL issues.
* **Resolution (2026-05-28):**
  * New **`qa_integrity_auditor`** agent (`run_qa_integrity_audit` in `main.py`, HEAVY model). It cross-checks every QA agent's PASS/FAIL verdict + findings against the raw debate log and chairman allocation (catching both hallucinated problems and rubber-stamped passes), verifies the rendered QA dashboard faithfully reflects the underlying reports, and flags coverage blind spots. Runs after the graphics-designer QA so it audits that agent too, then appears in the final dashboard.
  * **Deterministic compliance guard:** `main.reconcile_compliance()` forces `is_compliant=False` for any report containing a CRITICAL finding, applied at every QA parse site (post-flight, graphics designer, integrity auditor). The PASS/FAIL badge is now derived from evidence, not the model's self-graded boolean — fixes the "✅ PASS — requires critical adjustments" contradiction seen in run `20260528`.
* **Latency note:** adds ~1 heavy LLM call + 4 HTTP chart probes to the tail; benchmark against the 10-min ceiling on the next run and parallelize the graphics/integrity audits if it creeps.
* **Roster note (feeds 5.4):** this adds two more agents (`graphics_designer_qa` already existed; `qa_integrity_auditor` is new). The growing QA roster makes the HR Efficiency Consultant (5.4) more relevant.

### 5.7 Finance & Subscription Oversight — DONE (May 28, 2026)
* **Description:** Stan wants subscription/plan-fit governance across the whole project — not just per-run token usage (HR) or per-run duration (qa_review finance_cost), but "are we on the right plan, right tool, spending wisely?" including dev tooling (Cursor) and moving cloud/API bills. Agent must **find missing invoices, ask Stan for gaps, and surface possible hidden costs** from the tech stack.
* **Resolution (2026-05-28):**
  * **`docs/subscriptions_registry.json`** — machine-readable registry with confirmed costs: Ultra $199.99, FMP $29, Azure ~$8.06, Cursor $48/mo, GitHub $0 free, Polygon $0 unused. Gemini API recorded as **bundled in Ultra** (Stan assumption — `validation_status: unvalidated`). Includes `possible_hidden_costs` hunt list (Workspace, Azure post-credit, QuickChart paid, App Insights overages, stale Azure app-setting keys, etc.).
  * **`docs/tech_stack_and_subscriptions.md`** — human narrative + architecture map.
  * **`src/finance_oversight.py`** — standalone on-demand consultant: deterministic validation audit (missing data, unvalidated assumptions, hidden-cost list) + LLM plan-fit verdicts; outputs `docs/finance_oversight/oversight_*.html/json`; flags include `questions_for_stan`, `validation_actions`; optional `--fetch-latest` / `--email`.
  * **Future automation** documented in registry: Azure Cost Management API, Google invoice reconciliation.
* **Open validation:** Confirm Gemini API has no separate Google AI Studio invoice. Run finance oversight after updating registry when bills change.

---

## Phase 6: Agent Reasoning & Behavior Quality

### 6.1 Native "Thinking" Budgets for Decision-Critical Agents — DONE (in progress to validate)
* **Description:** Improve output quality by deliberately investing more Gemini 2.5 **native thinking** (internal reasoning) on the agents whose reasoning drives decisions, while protecting the context window and the 10-minute Azure ceiling.
* **Key insight:** Native thinking tokens are *internal* — they do **not** enter the response text, so they raise quality **without** bloating the debate history passed to downstream agents. This is the safe lever.
* **Resolution (2026-05-28):**
  * Added tunable budgets in `agents.py` (`THINK_PANELIST=4096`, `THINK_CHAIRMAN=8192`) and a `thinking_budget` key on the 5 board members + Chairman.
  * `engine._run_agent` now attaches `types.ThinkingConfig(thinking_budget=...)` when present. Verified the SDK config shape locally.
  * **Red Teamer left at default** — its output isn't consumed by any agent for decisions (read-only narrative), so elevated thinking is low ROI (see 5.2 opportunity note below).
* **Validate next run:** benchmark total runtime vs the ~5-6 min baseline (and the 10-min hard ceiling) and the Gemini token/cost delta; dial budgets down if runtime creeps up.
* **Deferred sub-items:**
  * **6.2 Thought-summary capture** — `include_thoughts=True` to log Chairman/Buffett reasoning to telemetry for drift detection (e.g., the live `STRONG BUY : MNDY` Buffett-drift case). Needs a parsing refactor in `_run_agent` (separate thought parts from the JSON answer) so it doesn't break structured-output parsing — do carefully.
  * **6.3 Red Teamer utilization** — its bear case is rendered but never fed back into the debate/decisions. Either wire it into the Chairman's final gut-check / Compliance, or accept it as reader-only. (Cross-ref Opportunity Audit 5.2.)

> **Note:** The agent-behavior/prompt-drift fixes triaged from Stan's Gemini list (Buffett value anchor, Livermore Stand-Aside, Chairman deterministic tie-break, synthesis contradiction, compliance de-hardcoding) are the natural rest of Phase 6 once the backlog write-up is confirmed.

---

## Backlog (Deferred Items)

* **Single Bad Ticker Abort:** Currently, one bad ticker kills the FMP fetch. *Decision:* Kept as-is intentionally to fail-fast during active development. Will implement graceful degradation when the solution matures.
* **Context Window Bloat:** The "Mega Prompt" appends the entire debate history. *Decision:* Monitor token usage. Implement summarization between rounds only if token limits or costs become an issue.
* **QuickChart.io Dependency:** HTML emails rely on an external chart rendering service. *Decision:* Acceptable for now. Future state could generate charts locally using `matplotlib` and attach as inline CID images.