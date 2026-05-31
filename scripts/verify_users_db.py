#!/usr/bin/env python3
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv

load_dotenv()


async def main():
    from src.data.db import fetch_query, fetch_row

    for slug in ("stan", "tester1", "local-sandbox"):
        u = await fetch_row("SELECT id, slug, email FROM users WHERE slug = $1", slug)
        if not u:
            print(f"{slug}: MISSING")
            continue
        c = await fetch_row(
            """
            SELECT COUNT(*)::int AS n FROM positions p
            JOIN portfolios port ON port.id = p.portfolio_id
            WHERE port.user_id = $1
            """,
            u["id"],
        )
        print(f"{slug}: {u['email']} — {c['n']} positions")


if __name__ == "__main__":
    asyncio.run(main())
