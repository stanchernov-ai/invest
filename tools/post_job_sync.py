#!/usr/bin/env python3
"""Local post-job sync — pulls Azure oversight blob or rebuilds from cache.

Usage (from repo root):
  .venv\\Scripts\\python.exe tools/post_job_sync.py --run-id 20260529_152151
  .venv\\Scripts\\python.exe tools/post_job_sync.py --run-id 20260529_152151 --sync-ecosystem
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.qa.post_job_audit import (
    RUN_ID_RE,
    append_oversight_to_ecosystem,
    build_post_job_oversight,
    load_oversight_from_cache,
)


def run_post_job_sync(
    run_id: str,
    cache_dir: Path | str = ".cache",
    *,
    sync_ecosystem: bool = False,
) -> dict:
    if not RUN_ID_RE.match(run_id):
        raise ValueError(f"Invalid run_id: {run_id!r}")

    cache = Path(cache_dir)
    if not cache.is_absolute():
        cache = REPO_ROOT / cache

    if sync_ecosystem:
        from tools.sync_ecosystem import sync_ecosystem_from_cache

        sync_ecosystem_from_cache(run_id, cache)

    bundle = load_oversight_from_cache(cache, run_id)
    if not bundle:
        telemetry_path = cache / "state" / f"api_telemetry_{run_id}.json"
        if not telemetry_path.exists():
            raise FileNotFoundError(
                f"Missing {telemetry_path} and post_job_oversight_{run_id}.json — fetch first."
            )
        telemetry = json.loads(telemetry_path.read_text(encoding="utf-8"))
        qa_reports_path = cache / "state" / f"qa_reports_{run_id}.json"
        qa_reports = []
        if qa_reports_path.exists():
            qa_reports = json.loads(qa_reports_path.read_text(encoding="utf-8"))
        run_status = None
        status_path = cache / "state" / f"run_status_{run_id}.json"
        if status_path.exists():
            run_status = json.loads(status_path.read_text(encoding="utf-8"))
        bundle = build_post_job_oversight(run_id, telemetry, qa_reports, run_status=run_status)

    append_oversight_to_ecosystem(bundle)
    metrics = bundle.get("metrics") or {}
    return {
        "run_id": run_id,
        "idle_agents": metrics.get("idle_agents", []),
        "qa_critical_count": metrics.get("qa_critical_count", 0),
        "total_tokens": metrics.get("total_tokens", 0),
        "verdict": metrics.get("verdict"),
        "source": "azure_blob" if load_oversight_from_cache(cache, run_id) else "rebuilt",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync post-job oversight into ecosystem_state.json.")
    parser.add_argument("--run-id", required=True, help="Run id YYYYMMDD_HHMMSS")
    parser.add_argument("--cache-dir", default=".cache")
    parser.add_argument(
        "--sync-ecosystem",
        action="store_true",
        help="Also sync qa_scorecards / retrospective / human review from cache",
    )
    args = parser.parse_args()

    try:
        result = run_post_job_sync(
            args.run_id,
            args.cache_dir,
            sync_ecosystem=args.sync_ecosystem,
        )
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(
        f"Post-job sync ({result['source']}) for {result['run_id']}: "
        f"verdict={result.get('verdict')} · "
        f"{len(result['idle_agents'])} idle · {result['qa_critical_count']} QA CRITICAL · "
        f"~{result['total_tokens']:,} tokens."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
