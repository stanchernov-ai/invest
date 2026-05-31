#!/usr/bin/env python3
"""
Run full pipeline (prepare → debate → deliver) for one user by slug.

Usage:
  python scripts/kickoff_user_run.py --slug tester1
  python scripts/kickoff_user_run.py --slug tester1 --replace-with-sandbox-csv

Briefing goes to the user's Postgres email; QA/legal/validation emails go to
STAN_PERSONAL_EMAIL (owner) only — see src/output/email_routing.py.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")


async def _fetch_user(slug: str) -> dict:
    from src.data.db import fetch_row

    row = await fetch_row(
        "SELECT id::text AS id, slug, email, display_name FROM users WHERE slug = $1",
        slug,
    )
    if not row:
        raise SystemExit(f"ERROR: no user with slug={slug!r}. Provision first.")
    return dict(row)


async def main() -> int:
    parser = argparse.ArgumentParser(description="Kick off full pipeline for one user")
    parser.add_argument("--slug", required=True, help="users.slug (e.g. tester1)")
    parser.add_argument(
        "--replace-with-sandbox-csv",
        action="store_true",
        help="Replace holdings with sandbox-test.csv before run",
    )
    parser.add_argument("--run-id", help="Optional run_id (default: now YYYYMMDD_HHMMSS)")
    args = parser.parse_args()

    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("ERROR: DATABASE_URL not set")

    user = await _fetch_user(args.slug)
    user_id = user["id"]

    if args.replace_with_sandbox_csv:
        import subprocess

        subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "admin_provision_user.py"),
                "--sandbox-csv-for-slug",
                args.slug,
            ],
            cwd=str(REPO_ROOT),
            check=True,
        )

    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"Kickoff slug={args.slug} user_id={user_id} run_id={run_id}")
    print(f"Briefing recipient: {user['email']}")
    if args.slug != "stan":
        print(f"QA/validation emails: owner inbox ({os.environ.get('STAN_PERSONAL_EMAIL', 'STAN_PERSONAL_EMAIL unset')})")

    from src.jobs.orchestrate import run_all

    result = await run_all(run_id=run_id, user_id=user_id)
    print(f"Finished: {result}")
    return 0 if result.get("status") == "success" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
