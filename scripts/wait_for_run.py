#!/usr/bin/env python3
"""Poll boardroom-state/run_status.json until a pipeline run finishes.

Usage (from repo root, with AZURE_STORAGE_CONNECTION_STRING set):
  .venv\\Scripts\\python.exe scripts/wait_for_run.py --run-id 20260528_153355
  .venv\\Scripts\\python.exe scripts/wait_for_run.py --timeout 660

Exit codes: 0=success, 1=failed/aborted, 2=timeout, 3=run_id mismatch at terminal.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import src.config.settings  # noqa: F401 — loads .env via settings SSOT

from src.storage_client import load_run_status

TERMINAL = frozenset({"success", "failed", "aborted"})


def main() -> None:
    parser = argparse.ArgumentParser(description="Wait for boardroom pipeline run completion.")
    parser.add_argument(
        "--run-id",
        help="Expected run_id (YYYYMMDD_HHMMSS local). Waits until this run reaches a terminal state.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=660,
        help="Max seconds to wait (default 660, slightly above the 10-min Azure ceiling).",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=15,
        help="Initial poll interval in seconds (backs off to 60s).",
    )
    args = parser.parse_args()

    deadline = time.time() + args.timeout
    interval = args.interval
    last_printed = None

    if not os.getenv("AZURE_STORAGE_CONNECTION_STRING"):
        print(
            "WARNING: AZURE_STORAGE_CONNECTION_STRING not set — cannot read run_status.json from Azure.\n"
            "Set it in .env or export it before running this script.",
            file=sys.stderr,
        )

    label = args.run_id or "latest"
    print(f"Monitoring run_status.json for {label} (timeout {args.timeout}s)...")

    while time.time() < deadline:
        status = load_run_status()
        if status:
            run_id = status.get("run_id")
            state = status.get("status")

            if args.run_id and run_id != args.run_id:
                if last_printed != "waiting_for_run":
                    print(f"  … stale status for run_id={run_id}; waiting for {args.run_id}")
                    last_printed = "waiting_for_run"
            else:
                snapshot = f"{run_id}:{state}"
                if snapshot != last_printed:
                    print(json.dumps(status, indent=2))
                    last_printed = snapshot

                if state in TERMINAL:
                    if args.run_id and run_id != args.run_id:
                        print(
                            f"ERROR: terminal status for run_id={run_id}, expected {args.run_id}",
                            file=sys.stderr,
                        )
                        raise SystemExit(3)
                    if state == "success":
                        print(f"SUCCESS — {status.get('duration_seconds')}s")
                        raise SystemExit(0)
                    err = status.get("error") or "no error detail"
                    print(f"RUN {state.upper()}: {err}", file=sys.stderr)
                    raise SystemExit(1)

        time.sleep(interval)
        interval = min(interval * 1.5, 60)

    print("TIMEOUT waiting for run completion", file=sys.stderr)
    raise SystemExit(2)


if __name__ == "__main__":
    main()
