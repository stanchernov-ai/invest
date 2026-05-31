-- Extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- users
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug            TEXT NOT NULL UNIQUE,
    entra_oid       TEXT UNIQUE,
    email           TEXT NOT NULL UNIQUE,
    display_name    TEXT,
    profile_json    JSONB NOT NULL DEFAULT '{}'::jsonb,
    plan_tier       TEXT NOT NULL DEFAULT 'beta'
                    CHECK (plan_tier IN ('beta', 'free', 'pro', 'paused')),
    portfolio_source TEXT NOT NULL DEFAULT 'manual'
                    CHECK (portfolio_source IN ('xls', 'manual')),
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'paused', 'deleted')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX users_status_active_idx ON users (status) WHERE status = 'active';
CREATE INDEX users_entra_oid_idx ON users (entra_oid) WHERE entra_oid IS NOT NULL;

-- portfolios
CREATE TABLE portfolios (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    bucket_type  TEXT NOT NULL DEFAULT 'custom'
                 CHECK (bucket_type IN ('taxable', 'roth', '401k', 'custom')),
    sort_order   INT NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, name)
);

-- positions
CREATE TABLE positions (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id   UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    symbol         TEXT NOT NULL,
    shares         NUMERIC(18, 6) NOT NULL CHECK (shares >= 0),
    cost_basis     NUMERIC(18, 2),
    purchase_date  DATE,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (portfolio_id, symbol)
);

-- watchlist_entries
CREATE TABLE watchlist_entries (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol     TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, symbol)
);

-- runs
CREATE TABLE runs (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL REFERENCES users(id),
    run_id       TEXT NOT NULL UNIQUE,
    scope        TEXT NOT NULL DEFAULT 'all_portfolios',
    status       TEXT NOT NULL,
    blob_prefix  TEXT NOT NULL,
    started_at   TIMESTAMPTZ,
    finished_at  TIMESTAMPTZ
);

CREATE INDEX runs_user_id_started_idx ON runs (user_id, started_at DESC);

-- market_data_cache (Phase 3 — may ship in migration 002)
CREATE TABLE market_data_cache (
    symbol             TEXT NOT NULL,
    as_of_date         DATE NOT NULL,
    eod_close          NUMERIC(18, 4),
    fundamentals_json  JSONB,
    fetched_at         TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (symbol, as_of_date)
);