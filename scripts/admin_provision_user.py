#!/usr/bin/env python3
"""
Admin-provision users + portfolios + positions into Postgres.

Usage:
  set DATABASE_URL=postgresql://boardroom_app:...@host:5432/boardroom?sslmode=require
  python scripts/admin_provision_user.py --slug stan --email stan@example.com ...
  python scripts/admin_provision_user.py --from-extracts --slugs stan,tester1

Idempotent on slug: re-run updates email/display_name and replaces positions per portfolio.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")


async def upsert_user(
    conn,
    *,
    slug: str,
    email: str,
    display_name: str,
    profile_json: dict | None = None,
    portfolio_source: str = "manual",
    plan_tier: str = "beta",
    status: str = "active",
) -> str:
    profile_json = profile_json or {}
    row = await conn.fetchrow("SELECT id FROM users WHERE slug = $1", slug)
    if row:
        user_id = row["id"]
        await conn.execute(
            """
            UPDATE users
            SET email = $2, display_name = $3, profile_json = $4::jsonb,
                portfolio_source = $5, plan_tier = $6, status = $7, updated_at = now()
            WHERE id = $1
            """,
            user_id,
            email,
            display_name,
            json.dumps(profile_json),
            portfolio_source,
            plan_tier,
            status,
        )
        print(f"Updated user {slug} ({user_id})")
    else:
        row = await conn.fetchrow(
            """
            INSERT INTO users (slug, email, display_name, profile_json, portfolio_source, plan_tier, status)
            VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7)
            RETURNING id
            """,
            slug,
            email,
            display_name,
            json.dumps(profile_json),
            portfolio_source,
            plan_tier,
            status,
        )
        user_id = row["id"]
        print(f"Created user {slug} ({user_id})")
    return str(user_id)


async def replace_portfolios(conn, user_id: str, portfolios: list[dict]) -> None:
    for p in portfolios:
        prow = await conn.fetchrow(
            """
            INSERT INTO portfolios (user_id, name, bucket_type, sort_order)
            VALUES ($1::uuid, $2, $3, $4)
            ON CONFLICT (user_id, name) DO UPDATE
              SET bucket_type = EXCLUDED.bucket_type, sort_order = EXCLUDED.sort_order
            RETURNING id
            """,
            user_id,
            p["name"],
            p["bucket_type"],
            p["sort_order"],
        )
        portfolio_id = prow["id"]
        await conn.execute("DELETE FROM positions WHERE portfolio_id = $1", portfolio_id)
        for pos in p.get("positions") or []:
            sym = str(pos["symbol"]).strip().upper()
            if not sym:
                continue
            await conn.execute(
                """
                INSERT INTO positions (portfolio_id, symbol, shares, cost_basis, purchase_date)
                VALUES ($1, $2, $3, $4, $5::date)
                """,
                portfolio_id,
                sym,
                float(pos.get("shares") or 0),
                float(pos.get("cost_basis") or 0),
                pos.get("purchase_date"),
            )
        print(f"  {p['name']}: {len(p.get('positions') or [])} positions")


async def provision_one(
    conn,
    *,
    slug: str,
    email: str,
    display_name: str,
    portfolios: list[dict],
    profile_json: dict | None = None,
) -> None:
    user_id = await upsert_user(
        conn,
        slug=slug,
        email=email,
        display_name=display_name,
        profile_json=profile_json,
    )
    await replace_portfolios(conn, user_id, portfolios)


HOLDINGS_BUCKET_BY_PORTFOLIO = {
    "e*trade individual brokerage": ("taxable", 0),
    "etrade taxable": ("taxable", 0),
    "e*trade roth ira": ("roth", 1),
    "etrade roth ira": ("roth", 1),
}


def load_portfolios_from_holdings_csv(csv_path: Path) -> list[dict]:
    """Load one or more portfolios from CSV (optional Portfolio column)."""
    import csv

    if not csv_path.is_file():
        raise FileNotFoundError(csv_path)
    grouped: dict[str, list[dict]] = {}
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fields = [c.strip() for c in (reader.fieldnames or [])]
        has_portfolio = any(c.lower() == "portfolio" for c in fields)
        for row in reader:
            sym = str(row.get("Symbol", "")).strip().upper()
            if not sym:
                continue
            pos = {
                "symbol": sym,
                "shares": float(row.get("Shares") or 0),
                "cost_basis": float(row.get("CostBasis") or row.get("Cost Basis") or 0),
            }
            if has_portfolio:
                pname = str(row.get("Portfolio", "")).strip() or "Holdings"
                grouped.setdefault(pname, []).append(pos)
            else:
                grouped.setdefault("Simulated Scenario", []).append(pos)

    portfolios = []
    for name, positions in grouped.items():
        key = name.strip().lower()
        bucket_type, sort_order = HOLDINGS_BUCKET_BY_PORTFOLIO.get(key, ("custom", len(portfolios)))
        portfolios.append(
            {
                "name": name,
                "bucket_type": bucket_type,
                "sort_order": sort_order,
                "positions": positions,
            }
        )
    portfolios.sort(key=lambda p: p["sort_order"])
    return portfolios


def load_sandbox_test_portfolios(csv_path: Path | None = None) -> list[dict]:
    """Single Simulated Scenario portfolio from repo sandbox-test.csv."""
    path = csv_path or (REPO_ROOT / "sandbox-test.csv")
    return load_portfolios_from_holdings_csv(path)


async def replace_user_holdings_from_csv(conn, slug: str, csv_path: Path) -> None:
    row = await conn.fetchrow("SELECT id, email, display_name FROM users WHERE slug = $1", slug)
    if not row:
        raise ValueError(f"User slug not found: {slug}")
    user_id = str(row["id"])
    await conn.execute(
        "DELETE FROM positions WHERE portfolio_id IN (SELECT id FROM portfolios WHERE user_id = $1::uuid)",
        user_id,
    )
    await conn.execute("DELETE FROM portfolios WHERE user_id = $1::uuid", user_id)
    portfolios = load_portfolios_from_holdings_csv(csv_path)
    await replace_portfolios(conn, user_id, portfolios)
    total = sum(len(p.get("positions") or []) for p in portfolios)
    print(f"{slug}: replaced holdings from {csv_path.name} ({len(portfolios)} portfolios, {total} positions)")


async def replace_user_with_sandbox_csv(conn, slug: str, csv_path: Path | None = None) -> None:
    path = csv_path or (REPO_ROOT / "sandbox-test.csv")
    await replace_user_holdings_from_csv(conn, slug, path)


async def main() -> int:
    parser = argparse.ArgumentParser(description="Provision Boardroom users in Postgres")
    parser.add_argument("--from-extracts", action="store_true", help="Load holdings from src/data/extracts")
    parser.add_argument("--extracts-dir", default=None, help="Override extracts directory")
    parser.add_argument("--slugs", default="stan,tester1", help="Comma-separated slugs for --from-extracts batch")
    parser.add_argument("--slug", help="Single user slug")
    parser.add_argument("--email", help="Single user email")
    parser.add_argument("--display-name", help="Single user display name")
    parser.add_argument("--profile-json", default="{}", help="JSON string for profile_json")
    parser.add_argument(
        "--sandbox-csv-for-slug",
        help="Replace user's portfolios with sandbox-test.csv (e.g. tester1)",
    )
    parser.add_argument("--sandbox-csv-path", default=None, help="Override path to CSV")
    parser.add_argument(
        "--holdings-csv-for-slug",
        help="Replace user's portfolios from a holdings CSV (Portfolio,Symbol,Shares,CostBasis)",
    )
    parser.add_argument(
        "--holdings-csv-path",
        default=None,
        help="Holdings CSV path (default: data/tester1-etrade-holdings.csv for tester1)",
    )
    args = parser.parse_args()

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL not set")
        return 1

    import asyncpg

    if args.holdings_csv_for_slug:
        conn = await asyncpg.connect(db_url)
        try:
            if args.holdings_csv_path:
                csv_path = Path(args.holdings_csv_path)
            elif args.holdings_csv_for_slug == "tester1":
                csv_path = REPO_ROOT / "data" / "tester1-etrade-holdings.csv"
            else:
                raise SystemExit("ERROR: --holdings-csv-path required for non-tester1 slugs")
            await replace_user_holdings_from_csv(conn, args.holdings_csv_for_slug, csv_path)
        finally:
            await conn.close()
        return 0

    if args.sandbox_csv_for_slug:
        conn = await asyncpg.connect(db_url)
        try:
            csv_path = Path(args.sandbox_csv_path) if args.sandbox_csv_path else None
            await replace_user_with_sandbox_csv(conn, args.sandbox_csv_for_slug, csv_path)
        finally:
            await conn.close()
        return 0

    if args.from_extracts:
        from src.data.legacy_portfolio_loader import load_holdings_from_extracts

        portfolios = load_holdings_from_extracts(args.extracts_dir)
        total_pos = sum(len(p["positions"]) for p in portfolios)
        print(f"Loaded {len(portfolios)} portfolios, {total_pos} positions from extracts")

        users_spec = {
            "stan": {
                "email": "stan.chernov@gmail.com",
                "display_name": "Stan",
            },
            "tester1": {
                "email": "stan.chernov+tester1@gmail.com",
                "display_name": "Tester Troy",
            },
        }
        slugs = [s.strip() for s in args.slugs.split(",") if s.strip()]
        conn = await asyncpg.connect(db_url)
        try:
            for slug in slugs:
                spec = users_spec.get(slug)
                if not spec:
                    print(f"ERROR: no built-in spec for slug {slug}")
                    return 1
                print(f"\n=== Provisioning {slug} ===")
                await provision_one(
                    conn,
                    slug=slug,
                    email=spec["email"],
                    display_name=spec["display_name"],
                    portfolios=portfolios,
                    profile_json={},
                )
        finally:
            await conn.close()
        print("\nDone.")
        return 0

    if not args.slug or not args.email:
        print("ERROR: --slug and --email required (or use --from-extracts)")
        return 1

    profile = json.loads(args.profile_json)
    conn = await asyncpg.connect(db_url)
    try:
        await provision_one(
            conn,
            slug=args.slug,
            email=args.email,
            display_name=args.display_name or args.slug,
            portfolios=[],
            profile_json=profile,
        )
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
