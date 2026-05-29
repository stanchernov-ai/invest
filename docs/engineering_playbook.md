# Engineering Playbook & Decision Log

**Purpose:** A living record of decisions we've made, environment gotchas, and approaches we've **tried and rejected** — so we (and any AI agent) don't loop through dead ends we already know won't work.

**How to use this file:**
- **Before** trying an approach, skim the relevant section. If it's in "Rejected / Doesn't Work," don't retry it without a reason that's changed.
- **After** discovering a gotcha or making a non-obvious decision, add an entry. Keep entries short: *what, why, date.*
- Mark reversible decisions with a "revisit if…" condition.

> Format for new entries: `- **[Topic]** — what we learned / decided. *Why.* (YYYY-MM-DD)`

---

## 1. Environment & Tooling (Windows / PowerShell)

- **PowerShell has no heredoc** — `git commit -m "$(cat <<'EOF' … EOF)"` fails. *Use a temp file + `git commit -F _commitmsg.txt`* (then delete it). (2026-05-28)
- **Multiline `python -c "…"` breaks in PowerShell** — the parser chokes on embedded newlines/quotes. *Write a temp `_xxx.py` file and run it, then delete.* (2026-05-28)
- **Always run Python via the venv interpreter** — `.venv\Scripts\python.exe`. The base interpreter is missing `aiohttp`, `tenacity`, etc. (2026-05-28)
- **`git push` can hang waiting on a credential prompt** — set `GIT_TERMINAL_PROMPT=0` before pushing so it fails fast instead of blocking. (2026-05-28)
- **Prefer `String.Contains` / `Get-Content` over regex for HTML content checks** — PowerShell mangles escaped parens in inline regex. (2026-05-28)

## 2. Azure (Functions, Storage, CLI)

- **`az functionapp show --query "defaultHostName"` returns empty** — *Use `az rest` against the full ARM API URL and read `properties.defaultHostName`.* (2026-05-28)
- **Triggering the function needs the region-specific `defaultHostName`** — guessing `<app>.azurewebsites.net` fails DNS. Resolve the real hostname via `az rest` first. (2026-05-28)
- **`az storage blob list --auth-mode login` → permission error** — *Switch to `--auth-mode key`* (fetch the account key first). (2026-05-28)
- **`save_report()` routes `.json` files to the STATE container (`boardroom-state`), not `boardroom-reports`** — by design. Don't go hunting for `portfolio_returns.json` in reports; it's in state. (2026-05-28)
- **Pull live run artifacts locally with `tools/fetch_azure_reports.py`** — instead of `az storage blob` gymnastics, run `.venv\Scripts\python.exe tools/fetch_azure_reports.py` (use `--list` to see run IDs, `--run-id YYYYMMDD_HHMMSS` for one coherent run, `--latest N` for the newest N of each family). Downloads to `.cache/{reports,state}/` + a `manifest.json`. Reuses the pipeline's connection-string auth. *Note: default mode grabs the latest of EACH family, so the briefing and qa_dashboard may come from different runs if the newest run didn't emit a dashboard — use `--run-id` when you need them aligned.* (2026-05-28)
- **Hosting = Flex Consumption plan** — newer plan with its own deploy behavior; the GitHub Actions OIDC workflow handles it. (2026-05-28)
- **Flex Consumption default hostname is regional** — e.g. `app-boardroom-prod-b5h4epg2d0cxefa0.eastus-01.azurewebsites.net`, not `app-boardroom-prod.azurewebsites.net`. Resolve via `az rest` on the site resource (`properties.defaultHostName`). Resource group: `rg-boardroom-prod`. (2026-05-29)
- **`QA_REVIEW_BASE_URL` must be scheme + host only** — code appends `/api/qa-review`. Do **not** include `/api` in the base or you get `/api/api/qa-review`. (2026-05-29)
- **Azure “Environment variables” → App settings** — after editing, click **Apply** or settings are not live. Verify with `az functionapp config appsettings list`. (2026-05-29)
- **QA review token in URL** — if `QA_REVIEW_TOKEN` contains `%` or `&`, use `urllib.parse.quote` when building links or browsers parse the query wrong. (2026-05-29)
- **Hard 10-minute execution ceiling** — the basic plan caps runs at ~10 min. Any feature that adds latency (history engine, elevated thinking budgets) must be benchmarked against this. Baseline run ≈ 5-6 min. (2026-05-28)
- **Don't sleep/poll blindly for deploy or run completion.** Azure cannot push notifications into Cursor. Use deterministic signals instead:
  * **Deploy done:** `gh run watch --exit-status` on the latest `Deploy to Azure Functions` workflow (no arbitrary `sleep`).
  * **Pipeline run done:** the function writes `boardroom-state/run_status.json` at start (`running`) and in `finally` (`success` / `failed` / `aborted`). Poll with `scripts/wait_for_run.py --run-id YYYYMMDD_HHMMSS` (exponential backoff, exits 0/1/2). Capture `--run-id` from local time at trigger moment.
  * **Human signal:** executive briefing email still fires on success; failure email is backlog item 2.2.
  * **Rejected:** fixed `sleep 300` then list blobs hoping a new file appeared — racey and wastes time. (2026-05-28)

## 3. Data & APIs

### FMP (Financial Modeling Prep)
- **Canonical reference:** `docs/fmp_data_dictionary.md` — field map, **known bad URLs**, excluded keys, action backlog. Re-run `tools/validate_fmp_fields.py` after plan changes. (2026-05-28)
- **Account = Starter tier, no bulk endpoints.** Many FMP endpoints were **deprecated in 2025**. *Validate any endpoint against this account before building on it.* (2026-05-28)
- **Dead stable URLs (404 — do not call):** `/stable/rating`, `/stable/earning_calendar`. Use `grades-consensus` + `earnings` instead. (2026-05-28)
- **Shared EOD cache:** prepare calls `prefetch_eod_cache()` once (~1095d); `get_fmp_advanced_metrics` + `history.build_account_returns` slice the same series. *Don't add per-symbol EOD fetches without going through the cache.* (2026-05-28)
- **Working EOD endpoint:** `stable/historical-price-eod/light` — 3M momentum, 3Y CAGR, TWR. (2026-05-28)
- **Class-share symbol normalization:** FMP expects `BRK-B`, not `BRK.B`. *Use `to_fmp_symbol()` in `fmp_client`.* (2026-05-28)
- **Empty `[]` ≠ yfinance fallback** for consensus/earnings when profile succeeded — code must hit alternate endpoints or lazy-load yfinance for those fields only. (2026-05-28)
- **Cap concurrency** with `asyncio.Semaphore(5)` on FMP calls to avoid rate limits within the Azure window. (2026-05-28)
- **Batch FMP endpoints return HTTP 402 on Starter** — `/stable/batch-quote` and v3 batch quote paths are plan-blocked. Macro hedges use two parallel `/stable/quote` calls in `get_fmp_macro` (~330ms); do not propose batch-quote as an optimization on this tier. Re-probe with `tools/probe_starter_tier.py` after any plan upgrade. (2026-05-29)

### yfinance / Yahoo
- **yfinance is unreliable for 3M momentum** — returned `"N/A"`, skewing agent behavior. *Replaced with FMP EOD.* yfinance is now a fundamentals fallback only. Yahoo IP-blackout risk remains a known fragility. (2026-05-28)

## 4. Gemini / LLM Agents

- **Gemini 2.5 native "thinking" tokens are internal** — they do NOT enter the response text, so raising `thinking_budget` improves quality **without** bloating the debate context passed downstream. This is the *safe* quality lever. (2026-05-28)
- **`include_thoughts=True` risks breaking structured-output parsing** — `_run_agent` parses `response.text` as JSON; mixing thought parts can corrupt that. *Capturing thoughts needs a parsing refactor (separate thought parts from the JSON answer) — don't enable it casually.* (2026-05-28)
- **On 2.5 Pro you can't fully disable thinking** (min budget ~128); on 2.5 Flash you can set `thinking_budget=0`. (2026-05-28)
- **Financial math belongs in deterministic Python, not the LLM** — max buys, 10% cap, wash-sale, **and Round 2 vote tallies** live in `guardrails.py`, `chairman_alignment.py`, and `vote_engine.py`. Chairman/compliance prompts receive a pre-computed **VOTE_DIGEST** — do not ask the model to count votes. (2026-05-28, expanded 2026-05-29)
- **Round 2 structured JSON is vote ground truth** — `debate.json` → `raw_verdicts`. Deliver vote matrix uses `build_board_matrix()` (JSON first, markdown parse fallback). Do not re-parse debate prose for tallies. (2026-05-29)
- **Chairman bypass is intentional** — `can_bypass_chairman()` skips the Pro call on unanimous actionable Buy/Reduce days; narratives are template stubs. 3/5 majority days still invoke chairman. (2026-05-29)

## 4b. Reporting / Email HTML & Charts

- **No flexbox or CSS grid in email HTML** — Gmail/Outlook strip `display:flex`, `flex-direction`, `grid`, and `object-fit`. A `flex-direction:column` (header above chart) collapses to a row, so chart titles render *beside* the chart instead of on top. *Use `<table role="presentation">` for all multi-column/stacked layouts; put the chart title in its own block immediately above the `<img>`.* (2026-05-28)
- **QuickChart: always use the short-URL endpoint, never the inline GET fallback for large charts** — `quickchart.io/chart?c=<encoded config>` shoves the whole config into the querystring. The benchmark line chart (full trailing-12M daily series) blows past URL length limits and the image silently breaks, while small pie/bar charts survive. *Use `POST /chart/create` (with `timeout` + one retry), and downsample long series (~90 pts) to keep payloads small.* `get_quickchart_short_url` now sends `width/height/backgroundColor/devicePixelRatio` and retries before falling back. (2026-05-28)
- **Chart health is verified deterministically, not by the LLM** — the Graphics Designer QA can't "see" rendered images, so `reporting.audit_chart_health()` HTTP-probes every chart URL and feeds the result into the agent prompt as ground truth. Build chart URLs once (`build_briefing_charts`) and reuse for both rendering and health checks (short URLs differ per call). (2026-05-28)
- **QA PASS/FAIL is derived from evidence, not the model's boolean** — a QA agent (notably the Graphics Designer) would self-report `is_compliant=true` while logging CRITICAL findings in its own prose, producing a green ✅ next to "requires critical adjustments." *`main.reconcile_compliance()` now forces `is_compliant=False` for any report containing a CRITICAL finding, applied at every QA parse site (post-flight, graphics designer, integrity auditor).* Don't trust the LLM's self-graded boolean. (2026-05-28)
- **Subscription/plan-fit governance lives in the registry + standalone consultant** — `docs/subscriptions_registry.json` + `docs/tech_stack_and_subscriptions.md` are the source of truth for SaaS/cloud/dev-tool costs. Run `.venv\Scripts\python.exe -m src.finance_oversight` (optional `--fetch-latest`, `--email`). Distinct from HR Efficiency (agent tokens) and qa_review finance_cost (per-run duration). **Open question:** Gemini Ultra ($199.99/mo consumer) vs `GEMINI_API_KEY` API billing — confirm in Google AI Studio whether pipeline API calls are included or billed separately. Future: Azure Cost Management API for live spend. (2026-05-28)
- **Per-agent activity is logged deterministically, not inferred** — `src/core/agent_activity.py` is an in-memory ledger; `call_gemini_async` records every call's model + token usage (prompt/output/thinking) + errors, keyed by `agent_name` (the config key passed by `_run_agent`). `main.py` resets it at run start and snapshots into `api_telemetry['AGENT_ACTIVITY']` in `finally`. The HR Efficiency Consultant (`src/hr_review.py`) consumes this as ground truth and merges it with the full roster to surface **idle agents**; runs predating 2026-05-28 won't have the field. Cost USD is an *estimate* from labeled Gemini 2.5 pricing constants — update them if Google's pricing changes; tokens are the source of truth. (2026-05-28)
- **QA-the-QA exists** — `run_qa_integrity_audit` (agent `qa_integrity_auditor`, HEAVY model) cross-checks the QA team's PASS/FAIL verdicts against the raw debate log + chairman allocation and verifies the rendered dashboard matches the underlying reports. It runs after the graphics-designer QA so it can audit that agent too; adds ~1 heavy LLM call to the tail — watch against the 10-min ceiling. (2026-05-28)

- **Pipeline is split into 3 chained Azure Functions (`prepare` → `debate` → `deliver`)** — each gets its own 10-minute ceiling; chained via **Storage Queues** (`boardroom-debate-queue`, `boardroom-deliver-queue`) carrying the `run_id`. The **6:00 AM daily** timer (`0 0 6 * * *`) starts `prepare`; requires Function App setting `WEBSITE_TIME_ZONE=America/Los_Angeles` (matches `BOARDROOM_TIMEZONE`). Phase code: `src/jobs/{prepare,debate,deliver}.py`; state handed off via `storage_client.save_checkpoint/load_checkpoint` → `runs/{run_id}/{phase}.json`. Local end-to-end + recovery: `python -m src.main` (`src/jobs/orchestrate.run_all`). Manual per-phase re-run: HTTP `/api/debate?run_id=...`, `/api/deliver?run_id=...` (FUNCTION key) — lets you re-render/re-QA without re-debating. *Why: a single monolith hit the 10-min ceiling mid-QA and gave one opaque log.* (2026-05-28)
- **`run_status.json` is phased** — `phase` + per-phase `{status,started_at,finished_at,duration_seconds,error}`; overall `status` stays `running` until `deliver` succeeds, flips `failed` on any phase failure. Each phase self-aborts at a **540s soft timeout** (`function_app._run_phase`) so an Azure host kill still records `failed` instead of a stale `running`. (2026-05-28)
- **Graphics QA is deterministic chart-health + multimodal final-artifact review** — `run_graphics_designer_qa` downloads images from the saved `executive_briefing_*.html` on Azure and sends them with the exact HTML body to Gemini Flash. Broken URLs still gated by `audit_chart_health()` first. (2026-05-29)
- **`sync_inputs_from_cloud()` pulls only a curated state allowlist** (`board_verdicts`, `portfolio_history`, `portfolio_returns`, `run_status`) — not every historical `api_telemetry_*.json`. Downloading ~20 telemetry blobs each run wasted time and pressured FMP rate limits on cold start. Pass `state_allowlist=` to override. (2026-05-28)
- **Watchlist Pass cooldown is cross-run state, not repo artifacts** — `src/verdict_memory.py` appends chairman watchlist **Pass** entries at end of deliver **only when `debate.is_approved`**. **Implicit Pass:** symbols on the prepare watchlist not assigned Buy/Strong Buy in chairman JSON are still persisted when `watchlist_symbols` is passed from deliver. Validated on run `20260529_144833` (21 Pass rows). Scout reads `board_verdicts.json` + CSV-owned tickers. Post-flight QA does **not** gate persistence. (2026-05-29)
- **Queue-message encoding gotcha (verify on deploy)** — Python v2 queue output/trigger should round-trip the plain `run_id` string via `msg.get_body().decode("utf-8")`. If the debate/deliver phases see an empty run_id, the extension bundle is base64-wrapping messages — set the message encoding or switch to an explicit `QueueClient`. (2026-05-28)
- **Session handoff lives at the top of `docs/action_tracker.md`** — read the **"Session Handoff"** section before starting work; it lists deploy state, tomorrow's verification checklist, TCO snapshot, and recommended next steps. (2026-05-28)
- **Post-deliver retrospective loop** — after each successful `deliver`, `execute_retrospective()` runs automatically (idempotent per `run_id`). Follow `docs/post_deliver_checklist.md` to review `retrospective_{run_id}.md` in Azure and validate candidates before editing Session Handoff. Manual re-run: `/api/retrospective?run_id=…` or `tools/run_retrospective.py --force`. (2026-05-29)
- **Latest deploy on `main`:** `6107539` (May 29, 2026) — `vote_engine` Phase A. Canonical validation run: `20260529_144833`. Prior: `e39b337` (human QA review UI). (2026-05-29)

## 5. Standing Architectural Decisions

- **Fail fast during active development** — errors should HARD STOP the pipeline (not graceful-continue) so we can fix them, rather than wait out a 10-min run. *Revisit once the solution is mature.* (Stan's call, 2026-05-28)
- **Blob lease = infinite (`-1`) with `try/finally` release** — chosen over a fixed 10-min lease, with guaranteed release at the end of the trigger. (2026-05-28)
- **Returns methodology = Time-Weighted Return (TWR)**, trailing-12-month window, **securities-only** basis, recomputed each run (self-healing backfill). (2026-05-28)
- **Track `src/data` in git** except the `extracts/` and `knowledge/` subfolders (static reference material). (2026-05-28)
- **Environment-variable validation is enforced** — `settings.validate()` returning `False` now aborts the run in `main.py`. (2026-05-28)
- **Human-facing timestamps render in a configurable local zone, not UTC.** Azure's Linux host runs in UTC, so naive `datetime.now()` showed UTC in logs/filenames. *Use `settings.now_local()` for display/filenames/logs; `settings.LOCAL_TZ` set via `BOARDROOM_TIMEZONE` env (default `America/Los_Angeles`). The logging formatter converter is overridden globally to local. Data-window date math (price-fetch ranges in `history.py`/`fmp_client.py`) intentionally stays UTC to avoid off-by-one fetch bugs. `tzdata` added to requirements so `zoneinfo` works on Windows.* (2026-05-28)

## 6. Approaches Tried and Rejected (don't retry)

| Approach | Why it failed / was rejected | Use instead |
|----------|------------------------------|-------------|
| `git commit` with bash heredoc in PowerShell | PowerShell has no heredoc | Temp file + `git commit -F` |
| Multiline `python -c "…"` in PowerShell | Parser chokes on newlines/quotes | Temp `.py` file |
| `az functionapp show --query defaultHostName` | Returns empty | `az rest` ARM query for `properties.defaultHostName` |
| `az storage blob list --auth-mode login` | Permission denied | `--auth-mode key` |
| yfinance for 3M momentum | Returns `N/A`, unreliable, IP-blackout risk | FMP `historical-price-eod/light` |
| Trusting the LLM to do liquidation-cap math | Inconsistent / unsafe | Deterministic Python |
| Fixed `sleep` then blob-list for run completion | Racey, wastes agent time | `scripts/wait_for_run.py` on `run_status.json` |
| `display:flex`/`flex-direction:column` for chart title-over-chart in email | Gmail/Outlook strip flex → title renders beside chart | `<table role="presentation">` with title block above `<img>` |
| QuickChart inline GET URL (`?c=<config>`) for the line chart | Long config exceeds URL limits → broken image | `POST /chart/create` short URL + downsample series |
| Trusting the Graphics Designer LLM to notice broken charts | It can't see rendered images | Deterministic `audit_chart_health` HTTP probe fed into the prompt |
