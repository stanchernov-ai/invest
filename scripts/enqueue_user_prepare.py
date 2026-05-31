#!/usr/bin/env python3
"""
Enqueue one user's prepare phase on Azure (boardroom-prepare-queue).

Requires DATABASE_URL and Azure Storage (AzureWebJobsStorage or
AZURE_STORAGE_CONNECTION_STRING). If storage is unset, tries:
  az functionapp config appsettings list -g rg-boardroom-prod -n app-boardroom-prod

Usage:
  python scripts/enqueue_user_prepare.py --slug tester1
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

PREPARE_QUEUE = "boardroom-prepare-queue"
FUNCTION_APP = "app-boardroom-prod"
RESOURCE_GROUP = "rg-boardroom-prod"


def _storage_connection_string() -> str:
    for key in ("AzureWebJobsStorage", "AZURE_STORAGE_CONNECTION_STRING"):
        val = os.environ.get(key)
        if val:
            return val
    try:
        az_cmd = os.environ.get("AZ_CLI", r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd")
        out = subprocess.run(
            [
                az_cmd,
                "functionapp",
                "config",
                "appsettings",
                "list",
                "-g",
                RESOURCE_GROUP,
                "-n",
                FUNCTION_APP,
                "--query",
                "[?name=='AzureWebJobsStorage'].value | [0]",
                "-o",
                "tsv",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        )
        conn = (out.stdout or "").strip()
        if conn and conn != "null":
            return conn
    except Exception as exc:
        raise SystemExit(f"ERROR: could not resolve AzureWebJobsStorage: {exc}") from exc
    raise SystemExit(
        "ERROR: set AzureWebJobsStorage or AZURE_STORAGE_CONNECTION_STRING, or log in with az cli."
    )


def _enqueue_message(conn: str, body: str) -> None:
    az_cmd = os.environ.get("AZ_CLI", r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd")
    subprocess.run(
        [
            az_cmd,
            "storage",
            "message",
            "put",
            "--queue-name",
            PREPARE_QUEUE,
            "--content",
            body,
            "--connection-string",
            conn,
            "--time-to-live",
            "604800",
        ],
        check=True,
        timeout=120,
    )


async def main() -> int:
    parser = argparse.ArgumentParser(description="Enqueue Azure prepare for one user slug")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--run-id", help="Optional run_id (default: now)")
    args = parser.parse_args()

    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("ERROR: DATABASE_URL not set")

    from src.data.db import fetch_row

    row = await fetch_row(
        "SELECT id::text AS id, slug, email FROM users WHERE slug = $1",
        args.slug,
    )
    if not row:
        raise SystemExit(f"ERROR: no user slug={args.slug!r}")

    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    payload = json.dumps({"run_id": run_id, "user_id": row["id"], "slug": row["slug"]})
    conn = _storage_connection_string()
    _enqueue_message(conn, payload)
    print(f"Enqueued prepare: slug={row['slug']} run_id={run_id} user_id={row['id']}")
    print(f"Email on deliver (Azure): {row['email']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
