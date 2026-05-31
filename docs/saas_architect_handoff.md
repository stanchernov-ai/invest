# SaaS Architecture Handoff — Phase 1 & 2 Multi-Tenant Rollout

**Date:** May 31, 2026
**To:** Systems Architect & Engineering Team
**From:** Engineering

This document serves as the handoff for the successful implementation of the **Multi-User GTM Architecture Plan**. The foundation is now set up to support distinct beta users accessing their own partitioned data streams natively, without relying on hardcoded parameters.

---

## 1. Accomplishments & What We Shipped

### A. Data Layer & Tenancy Isolation
- Threaded the `user_id` parameter directly through the `storage_client.py` and `verdict_memory.py`.
- Blob artifacts (reports, runs, telemetry) are now securely written into `{user_id}/...` partitioned folders instead of the root blob containers.
- Updated the `prepare`, `debate`, and `deliver` phase pipelines to inherently accept and cascade the `user_id` context.
- Generated the Azure Postgres schema scripts (`db/migrations/001_initial_schema.sql`) and a PowerShell automation script (`scripts/provision_azure_postgres.ps1`) to spin up the entity store database.
- Added database connectivity configuration utilizing `asyncpg` within `src/data/db.py`.

### B. Identity & REST API
- Built out the Entra External ID deployment script (`scripts/provision_entra.ps1`).
- Developed a secure Python JWT authentication decorator (`@require_auth` in `src/api/auth.py`) mapped to validate Entra token requests locally and lookup users dynamically.
- Constructed the REST CRUD routes (`src/api/routes.py`) connected via the new Function App blueprints (`function_app.py`) for managing:
  - `GET/PATCH /api/me`
  - `GET/POST /api/portfolios`
  - `GET/PUT /api/portfolios/{portfolio_id}/positions`

### C. Expo Client Repository (`sc-invest-boardroom-app`)
- Created the distinct Expo client repository within the project scope.
- Scaffolded the structural UI layout mirroring the "Stealth Wealth" aesthetic, defining basic `react-navigation` tabs within `App.tsx`.
- Drafted the React-based Frontend Auth Component (`AuthScreen.tsx`).
- Built out Frontend Profile Configuration UI forms tailored for the risk/conviction slider inputs (`ProfileScreen.tsx`).
- Developed the Portfolio component mapping forms enabling users to add symbols, shares, and cost basis inputs (`PortfolioScreen.tsx`).
- Created the Briefing WebView placeholder components for users to read their daily HTML reports natively (`BriefingScreen.tsx`).

### D. Orchestration / Multi-User Dispatcher
- Migrated the original single-runner `function_app.py` timer trigger logic into the new `boardroom_dispatcher` paradigm.
- The system now reads all `active` mapped users from the Postgres store and actively fans out isolated pipeline instances onto the `PREPARE_QUEUE`, decoupling execution time limitations from scaling user constraints.

---

## 2. Next Steps & Known Gaps

1. **Client App Data Hookup:** The Expo client UI forms currently mock API endpoints (`console.log`). We need to integrate `axios` calls with the MSAL token logic against the live Azure Functions endpoint.
2. **Postgres Ingestion in Pipeline:** `src/jobs/prepare.py` is currently hardcoded to generate an empty `user_profile = {}` to pass into `resolve_policy()`. Now that the database is created, this needs to be wired to read the `profile_json` from the `users` table via `user_id`.
3. **Portfolio Source Transition:** The pipeline still utilizes `pipeline.process_portfolios()` to read CSVs from the local disk. We need to implement the `PortfolioSource` abstraction to dynamically fetch positions from the `positions` table instead of CSVs.

The repository has been successfully committed, pushed to production, and the first multi-user dispatch has been triggered for verification.