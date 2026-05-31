# SC Invest Boardroom — Postgres Rollout Playbook

**Status:** Planning — execute when **Phase 2** gate clears ([`action_tracker.md`](action_tracker.md))  
**Last updated:** May 30, 2026  
**Schema SSOT:** [`saas_data_schema.md`](saas_data_schema.md) · **Architecture:** [`saas_technical_solution.md`](saas_technical_solution.md)

---

## 1. Purpose

Step-by-step playbook to provision **Azure Database for PostgreSQL — Flexible Server**, apply schema migrations, load admin-provisioned beta users, and wire the pipeline — **without throwaway work** when Entra self-service auth arrives later.

**First rollout goal:** multiple people receive daily briefings; **Stan admin-provisions** users in Postgres (no Entra login required yet). Schema and blob paths match the long-term SaaS design.

---

## 2. Prerequisites

| Gate | Check |
|------|-------|
| Phase 0 stable | Vote engine + core pipeline passing prod QA at acceptable rate |
| Phase 1 code | `PortfolioSource` abstraction merged; `CsvPortfolioSource` preserves Stan behavior |
| Azure access | Contributor on `rg-boardroom-prod` (or dedicated `rg-boardroom-data`) |
| Secrets hygiene | Plan Key Vault usage before putting connection string in Function App settings |

**Not required for first rollout:** Entra External ID, Stripe, self-service UI, `market_sync` (Phase 3).

---

## 3. Architecture (beta rollout)

```text
┌─────────────────────────────────────────────────────────────┐
│  Azure (existing)                                           │
│  ┌──────────────────┐    ┌─────────────────────────────┐   │
│  │ Function App      │    │ PostgreSQL Flexible Server   │   │
│  │ app-boardroom-prod│───▶│ boardroom (database)         │   │
│  │                   │    │  users, portfolios, positions│   │
│  └────────┬─────────┘    └─────────────────────────────┘   │
│           │                                                 │
│           ▼                                                 │
│  ┌──────────────────┐    ┌─────────────────────────────┐   │
│  │ Storage Queues    │    │ Blob (partitioned paths)     │   │
│  │ per-user messages │    │ boardroom-state/{slug}/...   │   │
│  └──────────────────┘    └─────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘

Operator (Stan): scripts/admin_provision_user.py  →  INSERT users/portfolios/positions
Timer: SELECT active users → enqueue {user_id, slug} → ManualPortfolioSource
```

---

## 4. Azure Postgres provisioning

### 4.1 Recommended SKU (beta)

| Setting | Beta value | Notes |
|---------|------------|-------|
| **Service** | Azure Database for PostgreSQL **Flexible Server** | Current managed offering |
| **Tier** | **Burstable** | Cheapest; sufficient for &lt;20 users, low QPS |
| **Compute** | `B1ms` or `B2s` | Scale up when daily fan-out grows |
| **Storage** | 32 GB (min) | Plenty for entity data; artifacts stay in Blob |
| **PostgreSQL version** | 16 or 17 | Use latest stable in portal |
| **Region** | **East US** (same as Function App) | Latency + data residency |
| **High availability** | Off for beta | Enable for paid production |
| **Public access** | See §4.3 | Prefer private endpoint when budget allows |

**Estimated cost:** ~**$15–35/mo** Burstable B1ms + storage (verify in [Azure pricing calculator](https://azure.microsoft.com/pricing/calculator/)).

### 4.2 Resource naming

```text
Resource group:  rg-boardroom-prod  (existing) or rg-boardroom-data
Server name:     psql-boardroom-prod   (globally unique)
Database name:   boardroom
Admin login:     boardroom_admin       (not used by app — break-glass only)
App login:       boardroom_app         (used by Function App)
```

### 4.3 Network and firewall

**Beta (simplest):**

1. Enable public access on Flexible Server.
2. **Allow Azure services** — permits Function App outbound to Postgres.
3. Optionally restrict to Function App outbound IPs if using dedicated IPs (Flex Consumption may vary).

**Production path (later):**

1. VNet integration + **private endpoint** for Postgres.
2. No public internet exposure.
3. Document in [`engineering_playbook.md`](engineering_playbook.md) when implemented.

### 4.4 Security defaults

- [ ] Enforce **SSL** (`sslmode=require` in connection string).
- [ ] Store connection string in **Azure Key Vault**; reference from Function App settings.
- [ ] Create **app role** `boardroom_app` with least privilege (DML on app tables only; no DDL in prod).
- [ ] Enable **automated backups** (default 7 days on Flexible Server).
- [ ] Tag resources: `project=boardroom`, `env=prod`, `component=data`.

---

## 5. Portal / CLI checklist

Execute in order. CLI examples use existing resource group from [`engineering_playbook.md`](engineering_playbook.md): `rg-boardroom-prod`.

### Step 1 — Create server (portal or CLI)

Portal: **Create a resource** → **Azure Database for PostgreSQL Flexible Server**.

Or CLI (adjust password via secure prompt — do not commit):

```powershell
az postgres flexible-server create `
  --resource-group rg-boardroom-prod `
  --name psql-boardroom-prod `
  --location eastus `
  --tier Burstable `
  --sku-name Standard_B1ms `
  --storage-size 32 `
  --version 16 `
  --admin-user boardroom_admin `
  --admin-password "<GENERATE-STRONG-PASSWORD>" `
  --public-access 0.0.0.0 `
  --yes
```

### Step 2 — Create database and app user

```powershell
az postgres flexible-server db create `
  --resource-group rg-boardroom-prod `
  --server-name psql-boardroom-prod `
  --database-name boardroom
```

Connect as admin (portal Query editor or `psql`) and run:

```sql
CREATE USER boardroom_app WITH PASSWORD '<APP-PASSWORD>';
GRANT CONNECT ON DATABASE boardroom TO boardroom_app;
-- After migrations:
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO boardroom_app;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO boardroom_app;
```

### Step 3 — Firewall rule for Azure services

```powershell
az postgres flexible-server firewall-rule create `
  --resource-group rg-boardroom-prod `
  --name psql-boardroom-prod `
  --rule-name AllowAzureServices `
  --start-ip-address 0.0.0.0 `
  --end-ip-address 0.0.0.0
```

### Step 4 — Key Vault secret

```powershell
# Create secret (vault must exist in same sub)
az keyvault secret set `
  --vault-name <your-keyvault> `
  --name boardroom-database-url `
  --value "postgresql://boardroom_app:<APP-PASSWORD>@psql-boardroom-prod.postgres.database.azure.com:5432/boardroom?sslmode=require"
```

Wire Function App setting `DATABASE_URL` as Key Vault reference.

### Step 5 — Local dev

Add to local `.env` (gitignored):

```text
DATABASE_URL=postgresql://boardroom_app:<password>@psql-boardroom-prod.postgres.database.azure.com:5432/boardroom?sslmode=require
```

For local-only dev, optional Docker Postgres on `localhost:5432` with same schema — never copy prod data to laptop without redaction.

---

## 6. Schema deployment

### 6.1 Repo layout (create in Phase 2)

```text
db/
  migrations/
    001_initial_schema.sql    ← from saas_data_schema.md §5
    002_market_data_cache.sql ← optional; may merge into 001
  seed/
    stan_migration.sql        ← optional; prefer Python loader from CSV
```

### 6.2 Apply migrations

**First time (manual):**

```powershell
# Requires psql client
psql "%DATABASE_URL%" -f db/migrations/001_initial_schema.sql
```

**Ongoing:** add a thin migration runner (`scripts/run_migrations.py`) or adopt Alembic — decide in Phase 2 PR; document choice in playbook when implemented.

### 6.3 Grant app permissions

After migrations:

```sql
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO boardroom_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO boardroom_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO boardroom_app;
```

---

## 7. Load users (admin-provisioned beta)

No Entra required. Operator workflow:

| Step | Action |
|------|--------|
| 1 | Insert `users` row (`slug`, `email`, `profile_json`, `portfolio_source='manual'`) |
| 2 | Insert `portfolios` (1+ buckets per user) |
| 3 | Insert `positions` per portfolio |
| 4 | Insert `watchlist_entries` if any |
| 5 | Verify with `ManualPortfolioSource.get_holdings(user_id)` in dev |
| 6 | Enable user in daily fan-out (`status = 'active'`) |

**Target script:** `scripts/admin_provision_user.py` (Phase 2 deliverable) — reads JSON fixture or interactive prompts; idempotent on `slug`.

**Stan migration:** separate script `scripts/migrate_stan_to_postgres.py` — reads existing CSV via `pipeline.process_portfolios()`, writes Postgres, sets `portfolio_source='csv'` until validated then `'manual'`.

---

## 8. Pipeline wiring (Phase 1 + 2)

| Component | Change |
|-----------|--------|
| `prepare.py` | Accept `user_id`; call `PortfolioSource` |
| `function_app.py` timer | Query active users; enqueue one message per user |
| Queue payload | `{"user_id": "<uuid>", "user_slug": "stan", "run_id": "..."}` — slug for logs/display only |
| `storage_client.py` | Blob paths use `user_id` prefix — see [`saas_tenancy_gaps.md`](saas_tenancy_gaps.md) |
| `notifier.py` | Resolve delivery email from `users.email` by `user_id` |
| `settings.py` | Add `DATABASE_URL`; validate when multi-user mode enabled |

**Feature flag (recommended):** `MULTI_USER_ENABLED=false` until first beta user validated; Stan-only path unchanged when false.

---

## 9. Validation checklist

Before pointing a beta friend at the pipeline:

- [ ] Migration `001` applied; `\dt` shows all tables
- [ ] App user connects from Function App (test HTTP trigger or Kudu console)
- [ ] Stan row loaded; holdings match CSV-derived `master_ledger` within tolerance
- [ ] One manual `prepare` for Stan's `user_id` succeeds end-to-end
- [ ] Blob artifacts land under `boardroom-state/stan/runs/{run_id}/`
- [ ] Briefing email sent to `users.email`
- [ ] Second test user (friend) runs without seeing Stan's data
- [ ] Connection string only in Key Vault + local `.env` — not in git

---

## 10. Rollout phases (within Phase 2)

| Sub-phase | Deliverable | User impact |
|-----------|-------------|-------------|
| **2a — Database** | Azure Postgres live, schema applied, Stan migrated | Stan only; pipeline still single-user optional |
| **2b — Multi-user fan-out** | Timer enqueues all active users; per-user blob paths | Friends receive briefings; Stan admin-loads their portfolios |
| **2c — Operator tooling** | `admin_provision_user.py`, docs for adding a user | Faster friend onboarding |
| **4 — Entra** (later) | External ID + Easy Auth; link `entra_oid` | Self-service login; same Postgres rows |

Nothing in 2a–2c is discarded when Entra ships — only `entra_oid` gets populated and HTTP routes gain auth.

---

## 11. Subscriptions registry update

After provisioning, add to [`subscriptions_registry.json`](subscriptions_registry.json):

```json
{
  "service_id": "azure_postgresql",
  "display_name": "Azure Database for PostgreSQL (Flexible Server)",
  "plan": "Burstable B1ms",
  "billing": "monthly",
  "monthly_usd": null,
  "confidence": "estimated",
  "notes": "boardroom entity store; update after first invoice"
}
```

Run finance oversight after first Azure invoice confirms cost.

---

## 12. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Connection timeout from Function App | Firewall / no Allow Azure | Add firewall rule §4.3 |
| SSL required error | Missing `sslmode=require` | Fix connection string |
| Permission denied on table | Grants not applied | Run §6.3 grants |
| Friend sees wrong holdings | Missing `user_id` filter | Audit repository queries |
| Duplicate run_id collision | Global run_id still used | Include user in run_id namespace or enforce unique per user in `runs` |

Log gotchas to [`engineering_playbook.md`](engineering_playbook.md).

---

## References

| Topic | Doc |
|-------|-----|
| Table definitions | [`saas_data_schema.md`](saas_data_schema.md) |
| Entra (later) | [`saas_technical_solution.md`](saas_technical_solution.md) §13 |
| Azure deploy / hostname | [`engineering_playbook.md`](engineering_playbook.md) |
| Backlog gate | [`action_tracker.md`](action_tracker.md) |
