#!/usr/bin/env python3
"""CLI wrapper for post-deliver retrospective (see src/qa/retrospective.py).

Usage (from repo root):
  .venv\\Scripts\\python.exe tools/run_retrospective.py --run-id 20260529_095341
  .venv\\Scripts\\python.exe tools/run_retrospective.py --fetch --force
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv()

from src.qa.retrospective import execute_retrospective, default_action_tracker_path
from src.storage_client import load_run_status


def resolve_run_id(explicit: str | None) -> str | None:
    if explicit:
        return explicit.strip()
    status = load_run_status()
    return status.get("run_id") if status else None


def maybe_fetch(run_id: str, cache_dir: Path) -> None:
    fetch_script = REPO_ROOT / "tools" / "fetch_azure_reports.py"
    if fetch_script.exists():
        subprocess.run(
            [sys.executable, str(fetch_script), "--run-id", run_id, "--out", str(cache_dir)],
            check=False,
            cwd=str(REPO_ROOT),
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Post-deliver retrospective CLI.")
    parser.add_argument("--run-id", help="Run id (default: latest run_status.json)")
    parser.add_argument("--fetch", action="store_true", help="Fetch artifacts before analysis")
    parser.add_argument("--force", action="store_true", help="Reprocess even if already completed")
    parser.add_argument("--cache-dir", default=".cache")
    parser.add_argument("--no-local-insights", action="store_true",
                        help="Skip append to local ecosystem_state.json")
    args = parser.parse_args()

    run_id = resolve_run_id(args.run_id)
    if not run_id:
        print("ERROR: No run_id. Pass --run-id or ensure run_status.json exists.", file=sys.stderr)
        return 2

    cache_dir = Path(args.cache_dir)
    if not cache_dir.is_absolute():
        cache_dir = REPO_ROOT / cache_dir
    if args.fetch:
        maybe_fetch(run_id, cache_dir)

    try:
        result = execute_retrospective(
            run_id,
            action_tracker_path=default_action_tracker_path(),
            force=args.force,
            write_local_insights=not args.no_local_insights,
        )
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3

    print(
        f"{result['status']}: run {run_id} — "
        f"{result.get('candidate_count', 0)} candidates, "
        f"{result.get('flag_count', 0)} flags"
    )
    if result.get("markdown_blob"):
        print(f"Artifact: {result['markdown_blob']}")
    if result.get("reason"):
        print(f"Reason: {result['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
