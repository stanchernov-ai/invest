# SC Invest Boardroom — Action Tracker

**Status:** Active  
**Last Updated:** May 28, 2026  

This document tracks identified bugs, architectural improvements, and long-term backlog items for the SC Invest Boardroom pipeline. Items are broken down into manageable blocks with specific implementation details.

---

## Phase 1: Immediate Bug Fixes & Hygiene

### 1.1 Azure Blob Lease Duration (Concurrency Fix)
* **Description:** The current blob lease duration is 60 seconds, but the pipeline takes longer. This risks a second instance acquiring the lock and running concurrently.
* **Implementation Details:** 
  * Update `function_app.py` to acquire the lease for the maximum allowed time or a duration that covers the Azure Function timeout (10 minutes for Consumption plan). 
  * *Note:* Azure Blob Storage leases can be set to 15-60 seconds, or infinite (`-1`). We will set it to `-1` (infinite) upon acquisition.
  * Wrap the `main_batch()` execution in a strict `try/finally` block to ensure `lease_client.release()` is *always* called, even if the pipeline crashes, so the lock isn't permanently stuck.

### 1.2 Munger Audit Results Discarded
* **Description:** `execute_munger_audit()` runs but its output is never passed to the Chairman, wasting tokens and losing valuable concentration risk analysis.
* **Implementation Details:**
  * In `src/core/engine.py`, capture the output of the `asyncio.gather(*tasks)` for the Munger audit.
  * Format the results into a string (e.g., `"MUNGER AUDIT WARNINGS: ..."`).
  * Inject this string dynamically into the `chairman` prompt during `execute_chairman_arbitration()`.

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

### 2.1 Move 10% Liquidation Cap Math to Python
* **Description:** The Chairman LLM is currently asked to calculate exactly 10% of the portfolio and execute fractional trims. LLMs struggle with deterministic math, risking compliance failures.
* **Implementation Details:**
  * Update the Chairman's prompt to remove the strict math requirement. Instead, ask the Chairman to *rank* his preferred sell/trim candidates and specify the new assets he wants to buy.
  * In `src/core/engine.py` (or a helper utility), intercept the Chairman's output *before* Compliance.
  * Use Python to calculate exactly 10% of `total_portfolio_value`.
  * Iterate through the Chairman's ranked sell list, trimming positions programmatically until the 10% cap is reached or the buys are funded.
  * Pass this mathematically validated execution plan to the Compliance agent.

### 2.2 Global Error Notifications (Silent Failures)
* **Description:** If the pipeline aborts (e.g., Data Oracle fails, FMP crashes), it exits silently without notifying the user.
* **Implementation Details:**
  * Add a `send_error_alert(error_message: str)` function to `src/output/notifier.py`.
  * In `src/main.py`, wrap the core logic of `main_batch()` in a global `try/except`.
  * On caught exceptions (or explicit `FatalDataError`), trigger the error alert email so the user is immediately aware of the failure.

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

### 3.1 Provide AI Agents Access to Azure Outputs
* **Description:** Allow Cursor agents to read historical reports, debate logs, and telemetry stored in Azure Blob Storage to provide weekly feedback and performance analysis.
* **Implementation Details:**
  * Create a utility script (e.g., `tools/fetch_azure_reports.py`) that uses `azure-storage-blob` to download the latest files from the `boardroom-reports` and `boardroom-state` containers to a local `.cache/` directory.
  * The Cursor agent can then be instructed to run this script via the Shell tool and read the resulting files to analyze past performance.

### 3.2 Cursor Architecture & QA Agents
* **Description:** Create specialized agent workflows/rules to validate architecture changes and analyze portfolio performance.
* **Implementation Details:**
  * Create a `.cursor/rules/architecture_validator.mdc` file defining how the agent should review PRs or structural changes against the `technical_solution.md`.
  * Define prompts for weekly performance analysis (e.g., comparing `portfolio_history.json` trends against the debate logs).

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

---

## Phase 5: Standing QA Review Team & Cost Governance

**Goal:** A recurring, multi-specialist review of the *framework itself* (code, logs, data, cost) that produces consolidated recommendations — distinct from the existing per-run debate QA.

**What already exists (build on, don't duplicate):**
* In-pipeline post-flight QA (`run_post_flight_qa` in `main.py`) already runs three reviewers against each run's debate log: `post_mortem_qa` (procedural), `system_architect` (technical/data-structure), `prompt_engineer` (persona drift). These review a *single run's output*, not the framework over time.
* `storage_client.execute_retention_policy(days_to_keep=14)` already purges blobs older than 14 days from the state/report containers (protecting `daily_execution.lock`, `board_verdicts.json`, `portfolio_history.json`).
* Phase 3.2 (Cursor Architecture & QA Agents) is the natural home for implementing these as Cursor subagents/rules on a weekly cadence.

### 5.1 Specialized QA Review Team — PLANNED
A team of focused reviewers, each producing a short scored report + prioritized recommendations. Proposed as **Cursor subagents/skills** run on a weekly cadence (reading the repo + the latest Azure logs/telemetry via the Phase 3.1 fetch script), with outputs consolidated into a single weekly digest.

| Reviewer | Focus | Primary inputs |
|----------|-------|----------------|
| **Data Flow** | Ingestion → ledger → prompt → report integrity; null/zero handling; double-counting; data quality | `pipeline.py`, telemetry JSON, raw debate log |
| **Prompt Engineering** | Persona drift, sycophancy, prompt/schema conflicts, instruction adherence | `agents.py`, `schemas.py`, debate logs |
| **APIs** | Endpoint health, deprecations, 4xx/429 rates, fallback usage, redundant calls | telemetry JSON (per-endpoint URLs + responses) |
| **Tech Stack & Orchestration** | Pipeline structure, concurrency, retries, error handling, deploy/runtime health | `engine.py`, `main.py`, `function_app.py`, Actions logs |
| **Finance / Cost** | Full monthly cost (Gemini tokens, FMP tier, Azure Functions + Storage + App Insights, email); identify cheaper alternatives **without losing functionality** | telemetry, Azure billing, model/plan choices |
| **Opportunity / Value Extraction** | Are we extracting maximum value from each agent + each paid API call? Identify unused data fields, underused agents, "gold on the ground" | full agent roster, prompts, raw data vs what's actually used |
| **HR Efficiency Consultant** | Right-size the agent roster: track every agent's activity/utilization, flag redundant, idle, or low-impact agents, surface gaps where a missing role would add value | agent roster, per-run debate logs, telemetry (which agents fired + token spend) |
| **Graphics Designer** | Final report visual polish — layout, typography, color, chart quality/legibility, responsive/email rendering — so the briefing looks "amazing" | `reporting.py` template, rendered HTML briefing, chart outputs |

* **Implementation notes:**
  * Each reviewer = a Cursor subagent with a tight system prompt + a scoring rubric (e.g., 1-5 per area + top 3 actions).
  * Orchestrate via a "QA Lead" prompt/skill that runs all reviewers and merges into a ranked weekly recommendation list appended to a `docs/qa_reviews/` log.
  * **Open questions for Stan:** (a) Cursor subagents vs adding more in-pipeline LLM agents? (b) Weekly cadence acceptable? (c) Should the weekly digest be emailed like the briefing?

### 5.2 Opportunity Audit — Value per API Call — PLANNED
* **Description:** Stan's concern: "leaving gold on the ground." Audit each agent and each paid data field to ensure we're using what we pay for.
* **Examples to investigate:** FMP fields fetched but unused in prompts (e.g., `3y_cagr` always `N/A`, `de`/`ps` ratios, `beta` for Kelly sizing); the unused `POLYGON_API_KEY` app setting; watchlist data richness vs how agents use it; whether Munger audit / QA agent outputs are surfaced.
* **Action:** Produce a coverage matrix (data field / agent capability → where consumed → value rating) and a prioritized list of high-value, low-effort additions.

### 5.3 Azure Storage Housekeeping & Cost Control — PLANNED
* **Description:** A dedicated "clean house" routine to delete older Azure files and keep monthly storage cost down. Stan wants this more deliberate than the current passive retention.
* **What exists:** `execute_retention_policy(14)` runs at the end of every pipeline run.
* **Enhancements to consider:**
  * Make retention window configurable (env var) and tier-aware (e.g., keep last N briefings regardless of age; aggressively purge large `api_telemetry_*.json` sooner — those are ~700 KB each).
  * Optionally move cold artifacts to a cheaper access tier (Cool/Archive) instead of deleting, if history is valuable.
  * A standalone Cursor/maintenance task (or scheduled function) to report current storage footprint + projected monthly cost and prune on demand.
  * Verify the deployment storage account (`rgboardroomprod93bf`) isn't accumulating old build artifacts.

### 5.4 HR Efficiency Consultant — PLANNED
* **Description:** A meta-governance reviewer that keeps the *agent roster itself* lean as we keep adding agents. Stan's concern: "I think we almost need an HR Efficiency Consultant to ensure we are not using unneeded agents." Tracks activity across all agents and reports on team efficiency, redundancy, and gaps.
* **Distinct from 5.2 (Opportunity):** Opportunity maximizes value extracted from each *API call/data field*; HR right-sizes the *headcount* — eliminating redundant/idle/low-impact agents and recommending new roles only where they add clear value.
* **What it tracks:**
  * **Utilization** — which agents actually fire each run, how often, and their token/cost footprint (from telemetry + debate logs).
  * **Redundancy** — agents whose outputs overlap or are never consumed downstream (e.g., results discarded like the historical Munger-audit issue).
  * **Impact** — does an agent's contribution change a verdict/outcome, or is it decorative?
  * **Gaps** — missing roles that would materially improve decisions or governance.
* **Output:** A per-period "org chart + utilization report" — table of agent → invocations → token cost → consumed-by → keep/merge/cut recommendation, plus proposed new roles. Feeds the weekly QA digest.
* **Implementation notes:** Likely a Cursor subagent reading the agent roster (`agents.py`), per-run debate logs, and telemetry. Needs lightweight per-agent activity logging if not already captured (tie into Phase 3.1 fetch + telemetry).

### 5.5 Graphics Designer — PLANNED
* **Description:** A design-focused reviewer/agent whose sole job is to make the final report "amazing." Stan: "want a graphics designer agent to make sure final report is amazing."
* **Scope:**
  * Visual hierarchy, typography, spacing, and color consistency across the HTML briefing.
  * Chart quality and legibility (pie/bar/line) — labels, contrast, sizing, the new per-account grid (4.2), and the verdict pills (4.3).
  * Rendering robustness across email clients and browsers (inline styles, table-based layouts, image fallbacks for QuickChart).
  * Brand/polish: header, section dividers, mobile/responsive behavior.
* **Output:** A prioritized list of concrete visual improvements (with before/after notes) and, where low-risk, proposed template diffs to `reporting.py`. Could run after each design change or weekly.
* **Implementation notes:** Cursor subagent that reads `reporting.py` + a rendered sample briefing (pulled from Azure via Phase 3.1) and critiques against a design rubric. Pairs naturally with the Phase 4 reporting work just completed.

---

## Backlog (Deferred Items)

* **Single Bad Ticker Abort:** Currently, one bad ticker kills the FMP fetch. *Decision:* Kept as-is intentionally to fail-fast during active development. Will implement graceful degradation when the solution matures.
* **Context Window Bloat:** The "Mega Prompt" appends the entire debate history. *Decision:* Monitor token usage. Implement summarization between rounds only if token limits or costs become an issue.
* **QuickChart.io Dependency:** HTML emails rely on an external chart rendering service. *Decision:* Acceptable for now. Future state could generate charts locally using `matplotlib` and attach as inline CID images.