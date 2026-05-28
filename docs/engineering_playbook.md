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
- **Hosting = Flex Consumption plan** — newer plan with its own deploy behavior; the GitHub Actions OIDC workflow handles it. (2026-05-28)
- **Hard 10-minute execution ceiling** — the basic plan caps runs at ~10 min. Any feature that adds latency (history engine, elevated thinking budgets) must be benchmarked against this. Baseline run ≈ 5-6 min. (2026-05-28)
- **Don't sleep/poll blindly for deploy or run completion.** Azure cannot push notifications into Cursor. Use deterministic signals instead:
  * **Deploy done:** `gh run watch --exit-status` on the latest `Deploy to Azure Functions` workflow (no arbitrary `sleep`).
  * **Pipeline run done:** the function writes `boardroom-state/run_status.json` at start (`running`) and in `finally` (`success` / `failed` / `aborted`). Poll with `scripts/wait_for_run.py --run-id YYYYMMDD_HHMMSS` (exponential backoff, exits 0/1/2). Capture `--run-id` from local time at trigger moment.
  * **Human signal:** executive briefing email still fires on success; failure email is backlog item 2.2.
  * **Rejected:** fixed `sleep 300` then list blobs hoping a new file appeared — racey and wastes time. (2026-05-28)

## 3. Data & APIs

### FMP (Financial Modeling Prep)
- **Account = Starter tier, no bulk endpoints.** Many FMP endpoints were **deprecated in 2025**. *Validate any endpoint against this account before building on it.* (2026-05-28)
- **Working EOD endpoint:** `stable/historical-price-eod/light` — used for 3M momentum and the TWR price series. (2026-05-28)
- **Class-share symbol normalization:** FMP expects `BRK-B`, not `BRK.B`. *Apply `sym.replace(".", "-")` before FMP calls.* (2026-05-28)
- **Cap concurrency** with `asyncio.Semaphore(5)` on FMP calls to avoid rate limits within the Azure window. (2026-05-28)

### yfinance / Yahoo
- **yfinance is unreliable for 3M momentum** — returned `"N/A"`, skewing agent behavior. *Replaced with FMP EOD.* yfinance is now a fundamentals fallback only. Yahoo IP-blackout risk remains a known fragility. (2026-05-28)

## 4. Gemini / LLM Agents

- **Gemini 2.5 native "thinking" tokens are internal** — they do NOT enter the response text, so raising `thinking_budget` improves quality **without** bloating the debate context passed downstream. This is the *safe* quality lever. (2026-05-28)
- **`include_thoughts=True` risks breaking structured-output parsing** — `_run_agent` parses `response.text` as JSON; mixing thought parts can corrupt that. *Capturing thoughts needs a parsing refactor (separate thought parts from the JSON answer) — don't enable it casually.* (2026-05-28)
- **On 2.5 Pro you can't fully disable thinking** (min budget ~128); on 2.5 Flash you can set `thinking_budget=0`. (2026-05-28)
- **Financial math belongs in deterministic Python, not the LLM** — the 10% liquidation cap and similar limits should be enforced in code, not trusted to the model. (2026-05-28)

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
