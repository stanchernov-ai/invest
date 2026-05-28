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

## Backlog (Deferred Items)

* **Single Bad Ticker Abort:** Currently, one bad ticker kills the FMP fetch. *Decision:* Kept as-is intentionally to fail-fast during active development. Will implement graceful degradation when the solution matures.
* **Context Window Bloat:** The "Mega Prompt" appends the entire debate history. *Decision:* Monitor token usage. Implement summarization between rounds only if token limits or costs become an issue.
* **QuickChart.io Dependency:** HTML emails rely on an external chart rendering service. *Decision:* Acceptable for now. Future state could generate charts locally using `matplotlib` and attach as inline CID images.