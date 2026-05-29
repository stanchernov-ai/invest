# Tech Stack & Subscriptions Registry

**Purpose:** Single source of truth for every SaaS, cloud, and tooling cost behind SC Invest Boardroom — so the **Finance & Subscription Oversight** consultant can judge plan fit, spot waste, and recommend cheaper or higher-quality alternatives.

**Machine-readable companion:** `docs/subscriptions_registry.json` (the oversight agent reads this first).

**How to update:** Edit the JSON when a plan or price changes, then bump `last_updated`. Re-run finance oversight to refresh recommendations.

---

## Monthly cost snapshot (confirmed + unknown)

| Service | Plan | Monthly USD | Confidence | Notes |
|---------|------|------------:|------------|-------|
| **Google AI Ultra** | Ultra ($199.99/mo) | **$199.99** | Confirmed | Consumer subscription; verify overlap with pipeline API key billing |
| **Gemini API** | Bundled in Ultra (assumed) | *$0 incremental* | Unvalidated | Pipeline LLM calls — verify no separate invoice |
| **Azure** | Pay-as-you-go + free credits | **~$8.06** (forecast ~$8.95) | Portal 2026-05-28 | Functions Flex + Blob + App Insights |
| **Cursor** | Pro+ annual ($576/yr) | **$48.00** | Confirmed | Renews 2027-05-28; dev tooling, not runtime |
| **FMP** | Starter | **$29.00** | Confirmed | Core market data |
| **GitHub** | Free | **$0** | Confirmed | Repo + Actions OIDC deploy |
| QuickChart | Free (assumed) | $0 | Assumed | Chart rendering |
| Gmail SMTP | Personal (assumed) | $0 | Assumed | Email delivery |
| Polygon.io | Free, **unused** | $0 | Confirmed | Remove stale `POLYGON_API_KEY` from Azure settings |
| yfinance | No subscription | $0 | — | Fallback only |

**Known monthly TCO (confirmed):** ~**$285/mo** ($199.99 Ultra incl. API assumed + $29 FMP + ~$8 Azure + $48 Cursor + $0 GitHub/QuickChart/Gmail/Polygon)  
**Open validation:** Gemini Ultra/API bundling still unverified against Google invoices; agent continues to hunt possible hidden costs.

---

## Architecture map (what runs where)

```
[Timer: 6:00 AM daily in WEBSITE_TIME_ZONE]  Azure Function (Flex Consumption) — `function_app.py` `0 0 6 * * *`
    ├── Sync inputs/state from Blob (boardroom-inputs, boardroom-state)
    ├── FMP API ── prices, news, macro, momentum
    ├── Gemini API ── 15+ agents (board debate, chairman, QA, graphics, integrity…)
    ├── QuickChart ── briefing charts
    └── Blob reports + Gmail SMTP ── executive briefing + QA dashboard

[Timer: 7:00 AM daily in WEBSITE_TIME_ZONE]  QA & Cost Review Team (qa_review.py) — `0 0 7 * * *`
    └── Gemini API ── weekly-style digest reviewers + HR Efficiency (from telemetry)

[GitHub Actions]  OIDC deploy → app-boardroom-prod on push to main

[Cursor Pro+]  Local/agent development (not in Azure runtime)
```

**Run frequency:** ~22 weekdays/month × 2 timers (pipeline + QA digest) = primary variable cost drivers are **Gemini tokens** and **FMP API calls**.

---

## Critical billing question: Gemini Ultra vs Gemini API

Stan believes **Gemini API usage (this pipeline's `GEMINI_API_KEY`) is included in the Google AI Ultra subscription** ($199.99/mo). **This is recorded but NOT yet validated** — the Finance Oversight agent must confirm via Google account invoices.

| | Google AI Ultra | Gemini API (this repo) |
|--|-----------------|------------------------|
| **What it is** | Consumer subscription | Developer API key used by all agents |
| **Monthly $ in registry** | $199.99 | $0 (bundled — do not double-count) |
| **Validation** | Price confirmed | **Unvalidated bundle assumption** |

**If a separate Google AI Studio / Cloud API charge appears on any invoice, update the registry immediately** — that would mean double-pay or partial coverage.

---

## What the Finance Oversight agent does

Run on demand (standalone):

```powershell
.venv\Scripts\python.exe -m src.finance_oversight
.venv\Scripts\python.exe -m src.finance_oversight --fetch-latest
.venv\Scripts\python.exe -m src.finance_oversight --email
```

It reads the registry and **deterministically** flags:
- Missing cost data (update registry when a plan is confirmed)
- Unvalidated assumptions (Ultra includes API, QuickChart free, Gmail free)
- **Possible hidden costs** inferred from the tech stack (Workspace, Azure post-credit, App Insights overages, stale paid keys in Azure settings, etc.)

Then the LLM layer adds plan-fit verdicts, **questions for Stan**, and **where to check invoices**. Its job is to hunt incomplete TCO and ask you directly — not guess silently.

Outputs: `docs/finance_oversight/oversight_*.html` + JSON.

## Per-service detail

### Google AI Ultra — $199.99/mo
- 20× Pro usage, 30 TB storage (per your plan description).
- **Value question for oversight:** Are we using enough of the Ultra entitlements to justify $200/mo vs Pro, *given* the pipeline burns API tokens separately?

### Azure — ~$8/mo (forecast ~$9)
- **App:** `app-boardroom-prod` (Flex Consumption, 10-min timeout).
- **Storage:** `boardroom-inputs`, `boardroom-state`, `boardroom-reports`.
- **Observability:** Application Insights (host.json).
- **Credits:** Free trial credits still active; watch expiry date in portal.
- **Future:** Pull live cost via Azure Cost Management API.

### Cursor Pro+ — $48/mo ($576/yr)
- Auto-renews **2027-05-28**.
- Counts toward **project TCO**, not Azure runtime.

### FMP Starter — $29/mo
- Playbook: no bulk endpoints; `stable/historical-price-eod/light` is the workhorse.
- **Plan-fit check:** As watchlist + portfolio symbols grow, does Starter rate-limit before we hit 10-min Azure ceiling?

### Unused / zero-cost items
- **Polygon.io:** Free tier, zero code usage — remove `POLYGON_API_KEY` from Azure app settings.
- **QuickChart:** Free; monitor if chart volume triggers limits.
- **yfinance:** Unofficial fallback only.

---

## Changelog

| Date | Change |
|------|--------|
| 2026-05-28 | EOD handoff section added to `docs/action_tracker.md`; deploy commits `4dc0b2e` + `29b4101` on main |
| 2026-05-28 | GitHub confirmed free tier |
| 2026-05-28 | Gemini API recorded as bundled in Ultra (Stan assumption — unvalidated); agent hunts hidden costs |
| 2026-05-28 | FMP Starter confirmed at $29/mo |
| 2026-05-28 | Initial registry from codebase inventory + Stan-provided Ultra / Azure / Cursor pricing |
