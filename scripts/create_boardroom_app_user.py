#!/usr/bin/env python3
"""
Create boardroom_app role and grants on Azure/local Postgres.

Uses DATABASE_URL (admin user recommended for CREATE USER).

Usage:
  set DATABASE_URL=postgresql://boardroom_admin:...@host:5432/boardroom?sslmode=require
  set BOARDROOM_APP_PASSWORD=your-app-password
  python scripts/create_boardroom_app_user.py
"""
from __future__ import annotations

import asyncio
import os
import sys


async def main() -> int:
    db_url = os.environ.get("DATABASE_URL")
    app_password = os.environ.get("BOARDROOM_APP_PASSWORD")
    if not db_url:
        print("ERROR: Set DATABASE_URL (admin connection to database boardroom).")
        return 1
    if not app_password:
        print("ERROR: Set BOARDROOM_APP_PASSWORD (new password for boardroom_app).")
        return 1

    try:
        import asyncpg
    except ImportError:
        print("ERROR: pip install asyncpg (or use requirements.txt).")
        return 1

    # Escape single quotes in password for SQL literal
    safe_pw = app_password.replace("'", "''")

    statements = [
        f"CREATE USER boardroom_app WITH PASSWORD '{safe_pw}'",
        "GRANT CONNECT ON DATABASE boardroom TO boardroom_app",
        "GRANT USAGE ON SCHEMA public TO boardroom_app",
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO boardroom_app",
        "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO boardroom_app",
        """ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO boardroom_app""",
        """ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO boardroom_app""",
    ]

    conn = await asyncpg.connect(db_url)
    try:
        for sql in statements:
            try:
                await conn.execute(sql)
                print(f"OK: {sql.split(chr(10))[0][:72]}...")
            except asyncpg.DuplicateObjectError:
                print("SKIP (already exists): CREATE USER boardroom_app")
            except Exception as exc:
                if "already exists" in str(exc).lower():
                    print(f"SKIP: {exc}")
                else:
                    raise
    finally:
        await conn.close()

    print("\nboardroom_app is ready. Update .env to use boardroom_app in DATABASE_URL.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
