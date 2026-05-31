#!/usr/bin/env python3
"""Sync QA findings from a run into docs/action_tracker.md (single backlog).

Usage (from repo root):
  .venv\\Scripts\\python.exe tools/sync_backlog.py --run-id 20260530_235519
  .venv\\Scripts\\python.exe tools/sync_backlog.py --run-id 20260530_235519 --cache-dir .cache
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.qa.backlog_sync import default_action_tracker_path, merge_run_into_backlog


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Log QA findings into action_tracker.md Open items (deduped)."
    )
    parser.add_argument("--run-id", required=True, help="Run id YYYYMMDD_HHMMSS")
    parser.add_argument("--cache-dir", default=".cache")
    parser.add_argument(
        "--tracker",
        default=None,
        help="Override action_tracker path (default: docs/action_tracker.md)",
    )
    args = parser.parse_args()

    cache = Path(args.cache_dir)
    if not cache.is_absolute():
        cache = REPO_ROOT / cache

    tracker = Path(args.tracker) if args.tracker else default_action_tracker_path()

    try:
        result = merge_run_into_backlog(
            args.run_id,
            tracker_path=tracker,
            cache_dir=cache,
        )
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(
        f"Backlog sync for {result['run_id']}: "
        f"+{result['added']} new · {result['updated']} updated · "
        f"{result['skipped']} skipped (deduped) · {result['total']} total open rows."
    )
    print(f"Updated: {tracker}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
