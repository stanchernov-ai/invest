#!/usr/bin/env python3
"""Apply SQL migrations from db/migrations/ (requires DATABASE_URL)."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = REPO_ROOT / "db" / "migrations"


async def main() -> int:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: Set DATABASE_URL (e.g. postgresql://boardroom_app:local_dev_password@localhost:5432/boardroom)")
        return 1

    try:
        import asyncpg
    except ImportError:
        print("ERROR: asyncpg not installed. Run: pip install -r requirements.txt")
        return 1

    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        print(f"ERROR: No migrations in {MIGRATIONS_DIR}")
        return 1

    conn = await asyncpg.connect(db_url)
    try:
        for path in files:
            sql = path.read_text(encoding="utf-8")
            print(f"Applying {path.name} ...")
            try:
                await conn.execute(sql)
            except Exception as exc:
                if "pgcrypto" in str(exc).lower() and "allow" in str(exc).lower():
                    print(
                        "\nAzure blocked extension pgcrypto. Allow-list it first:\n"
                        "  Portal → psql-boardroom-prod → Server parameters → azure.extensions\n"
                        "  Add PGCRYPTO → Save → wait ~1 min → re-run this script.\n"
                        "  Or CLI:\n"
                        "  az postgres flexible-server parameter set -g rg-boardroom-prod "
                        "-n psql-boardroom-prod --name azure.extensions --value PGCRYPTO\n"
                    )
                raise
            print(f"  OK")
    finally:
        await conn.close()

    print("Migrations complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
