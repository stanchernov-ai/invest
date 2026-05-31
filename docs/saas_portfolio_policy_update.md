# SaaS Architecture Update — Portfolio Policy & Multi-Tenant Refactoring

**Date:** May 31, 2026  
**To:** Systems Architect  
**From:** Engineering  
**Subject:** Multi-Tenant Portfolio Policy & Commercial GTM Readiness

This document summarizes the architectural changes implemented today to transition the single-tenant, hardcoded pipeline into a dynamic, multi-tenant SaaS application, specifically focusing on the Portfolio Policy and legal compliance.

---

## 1. What We Shipped Today

We decoupled the core portfolio logic from the hardcoded LLM prompts and global Python constants, moving to a dynamic `user_profile` model that aligns with our commercial GTM strategy.

### A. The `PortfolioPolicy` Abstraction
Created `src/core/portfolio_policy.py` to map a user's `profile_json` into text blocks and numeric guardrails.
- **Removed Hardcoded Doctrines:** Completely removed `MUNGER_DOCTRINE` and `RETAIL_EDGE_DOCTRINE` from `schemas.py` and `engine.py`. This removes the legal risk of implied endorsements from living investors (which previously violated our commercial boundaries).
- **Introduced Sliders:** Replaced static doctrines with dynamic "Risk" and "Conviction" sliders (0-100 scales).
  - **High Conviction (>70):** Instructs the board to act aggressively, concentrate on top ideas, and maintain a small number of distinct stocks in the portfolio to maximize alpha.
  - **Low Conviction (<30):** Instructs the board to use a "Distribution Doctrine," enforcing strict risk management, preservation, and a highly diverse portfolio with many different distinct stocks.
  - **Risk Slider:** Dynamically shifts the mandate between "Asymmetric Risk" and "Preservation".
- **Dynamic Mandate:** Moved `generate_dynamic_mandate()` into the `PortfolioPolicy` class so it can utilize the user's actual age, target retirement age, and benchmark.

### B. Configurable Deterministic Guardrails
Previously, limits like `LIQUIDATION_CAP_PCT` and `MAX_DAILY_BUYS` were hardcoded globally in `guardrails.py` or `.env`. 
- Refactored `apply_chairman_guardrails` to accept a `user_profile` dictionary.
- The rules now pull limits dynamically from the user's `PortfolioPolicy` instead of environment variables.
- This ensures that when we provision new users, their deterministic limits will automatically adapt to their `profile_json`.

### C. Documentation & Schema Updates
- Updated `docs/saas_data_schema.md` to reflect the new `profile_json` shape, which client UI forms will map to:
  ```json
  {
    "date_of_birth": "1978-08-06",
    "target_retirement_age": 65,
    "monthly_contribution_usd": 500,
    "benchmark": "NASDAQ",
    "benchmark_alpha_target_pct": 5,
    "primary_panelist": "tesla",
    "risk_slider": 75,
    "conviction_slider": 80,
    "liquidation_cap_pct": 0.10,
    "max_daily_buys": 3,
    "asset_guidance": {
      "equity_target_pct": 100,
      "bond_etf_symbols": ["TLT", "BND"],
      "hedge_symbols": ["TLT", "VXX"]
    },
    "timezone": "America/Los_Angeles"
  }
  ```

---

## 2. Alignment with Product & Legal Principles

- **No Living Investors as Primary Personas:** We are strictly utilizing historical, public-domain personas (Tesla, Hypatia, Sun Tzu, etc.) for the `primary_panelist` configuration, adhering to Right of Publicity and Implied Endorsement constraints.
- **No Guaranteed Returns:** Slider templates emphasize "preservation" or "growth" but strictly avoid forbidden marketing language like "risk-free" or "guaranteed returns".
- **Board Decides, Code Executes:** The adversarial 3/5 debate mechanism remains unchanged. The `PortfolioPolicy` biases the *instruction* to the whole board, but deterministic execution (vote counting, liquidation capping) remains firmly in Python.

---

## 3. Recommended Next Steps for Architecture Review

We are now ready to tackle Phase 1 and Phase 2 of the SaaS rollout. We request architectural guidance on the following execution path:

1. **Phase 1: `PortfolioSource` Abstraction:** 
   - Refactor `prepare.py` to use a clean interface (`CsvPortfolioSource` vs `ManualPortfolioSource`) instead of hardcoding the CSV load. This allows local dev to continue smoothly while opening the door for database ingestion.
2. **Phase 2a: Database Integration:**
   - Wire `prepare.py` to accept a `user_id`, query Postgres for the user's `profile_json`, and pass it into `resolve_policy(user_profile)`. Currently, `prepare.py` is passing an empty dict which defaults to the original "Stan" settings.
3. **Phase 2b: The Daily Dispatcher:**
   - Update the Azure Function timer to query the database for all `active` users and push individual jobs to the queue for each user, unlocking multi-tenant concurrency.
4. **Phase 4: Client Profile UI API:**
   - Begin defining the REST API contracts (e.g., `PATCH /api/me/profile`) and Expo UI forms for users to interact with their sliders.

We look forward to your feedback on the `PortfolioPolicy` structure and the sequence of these next phases.