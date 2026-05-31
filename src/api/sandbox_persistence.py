"""Persist simulated sandbox scenarios to Postgres."""
from __future__ import annotations

import os
from typing import Any

from src.data.db import execute_query, fetch_row

SANDBOX_PORTFOLIO_NAME = "Simulated Scenario"
THEORETICAL_BASELINE = 100_000.0
DEFAULT_SANDBOX_SLUG = "local-sandbox"
DEFAULT_SANDBOX_EMAIL = "sandbox@local.dev"


def _sandbox_slug() -> str:
    return os.environ.get("SANDBOX_USER_SLUG", DEFAULT_SANDBOX_SLUG).strip()


async def get_or_create_sandbox_user() -> dict[str, Any]:
    slug = _sandbox_slug()
    row = await fetch_row(
        "SELECT id, slug, email FROM users WHERE slug = $1 AND status = 'active'",
        slug,
    )
    if row:
        return dict(row)

    row = await fetch_row(
        """
        INSERT INTO users (slug, email, display_name, portfolio_source, profile_json)
        VALUES ($1, $2, $3, 'manual', '{}'::jsonb)
        RETURNING id, slug, email
        """,
        slug,
        os.environ.get("SANDBOX_USER_EMAIL", DEFAULT_SANDBOX_EMAIL),
        "Local Sandbox",
    )
    return dict(row)


async def get_or_create_sandbox_portfolio(user_id) -> dict[str, Any]:
    row = await fetch_row(
        """
        SELECT id, name FROM portfolios
        WHERE user_id = $1 AND name = $2
        """,
        user_id,
        SANDBOX_PORTFOLIO_NAME,
    )
    if row:
        return dict(row)

    row = await fetch_row(
        """
        INSERT INTO portfolios (user_id, name, bucket_type, sort_order)
        VALUES ($1, $2, 'custom', 0)
        RETURNING id, name
        """,
        user_id,
        SANDBOX_PORTFOLIO_NAME,
    )
    return dict(row)


def _normalize_positions(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach weight % and theoretical $ allocation on a $100k baseline."""
    notionals = []
    for pos in raw:
        shares = float(pos.get("shares") or 0)
        cost = float(pos.get("cost_basis") or 0)
        notionals.append(max(shares * cost, 0.0))

    total = sum(notionals) or 1.0
    normalized = []
    for pos, notional in zip(raw, notionals):
        weight_pct = round((notional / total) * 100, 2)
        theoretical_value = round((weight_pct / 100) * THEORETICAL_BASELINE, 2)
        normalized.append(
            {
                "symbol": pos["symbol"],
                "shares": float(pos.get("shares") or 0),
                "cost_basis": float(pos.get("cost_basis") or 0),
                "weight_pct": weight_pct,
                "theoretical_value": theoretical_value,
            }
        )
    return normalized


async def persist_sandbox_positions(
    raw_positions: list[dict[str, Any]],
) -> dict[str, Any]:
    user = await get_or_create_sandbox_user()
    user_id = user["id"]
    portfolio = await get_or_create_sandbox_portfolio(user_id)
    portfolio_id = portfolio["id"]

    await execute_query("DELETE FROM positions WHERE portfolio_id = $1", portfolio_id)

    for pos in raw_positions:
        sym = str(pos["symbol"]).strip().upper()
        if not sym:
            continue
        await execute_query(
            """
            INSERT INTO positions (portfolio_id, symbol, shares, cost_basis)
            VALUES ($1, $2, $3, $4)
            """,
            portfolio_id,
            sym,
            float(pos.get("shares") or 0),
            float(pos.get("cost_basis") or 0),
        )

    positions = _normalize_positions(raw_positions)
    return {
        "user_id": str(user_id),
        "user_slug": user["slug"],
        "portfolio_id": str(portfolio_id),
        "portfolio_name": portfolio["name"],
        "positions": positions,
        "theoretical_baseline": THEORETICAL_BASELINE,
        "persisted": True,
    }
