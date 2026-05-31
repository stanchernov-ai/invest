#!/usr/bin/env python3
"""Overnight self-healing flywheel — Tier 1 skeleton (PR-D).

Usage (from repo root):
  .venv\\Scripts\\python.exe tools/overnight_fix.py score
  .venv\\Scripts\\python.exe tools/overnight_fix.py init --issue QA-090637-02
  .venv\\Scripts\\python.exe tools/overnight_fix.py validate-plan --issue QA-090637-02
  .venv\\Scripts\\python.exe tools/overnight_fix.py approve-plan --issue QA-090637-03 --by stan
  .venv\\Scripts\\python.exe tools/overnight_fix.py test --issue QA-090637-02 --iteration 1
  .venv\\Scripts\\python.exe tools/overnight_fix.py dry-run --issue QA-090637-02

Does NOT invoke Cursor SDK, auto-deploy, or /api/prepare. See docs/overnight_flywheel_review.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.overnight.lock import clear_lock, is_locked, write_lock
from src.overnight.orchestrator import (
    approve_plan,
    dry_run_report,
    init_run,
    run_tester_step,
    validate_plan_step,
)
from src.overnight.paths import ensure_overnight_dirs
from src.overnight.roi import rank_open_items


def cmd_score(args: argparse.Namespace) -> int:
    items = rank_open_items(fix_type=args.fix_type, limit=args.limit)
    if not items:
        print("No eligible open items.")
        return 0
    print(f"Top {len(items)} by ROI (fix={args.fix_type or 'any'}):")
    for row in items:
        print(
            f"  {row['roi_score']:6.1f}  {row.get('priority')}  {row.get('item_id')}  "
            f"fix={row.get('fix')}  {(row.get('item') or '')[:70]}"
        )
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    locked, msg = is_locked()
    if locked and not args.force:
        print(f"BLOCKED: {msg}", file=sys.stderr)
        print("Use --force to init anyway, or clear LOCK after human architect finishes.", file=sys.stderr)
        return 4
    try:
        manifest = init_run(args.issue, max_iterations=args.max_iterations)
    except LookupError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3
    print(json.dumps(manifest, indent=2))
    print(f"\nNext: edit {REPO_ROOT / '.cursor/agent_state/overnight/runs' / args.issue / 'fix_plan.md'}")
    return 0


def cmd_validate_plan(args: argparse.Namespace) -> int:
    try:
        ok, errors = validate_plan_step(args.issue)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3
    if ok:
        print(f"fix_plan.md VALID for {args.issue}")
        return 0
    print(f"fix_plan.md INVALID for {args.issue}:", file=sys.stderr)
    for err in errors:
        print(f"  - {err}", file=sys.stderr)
    return 2


def cmd_approve_plan(args: argparse.Namespace) -> int:
    try:
        manifest = approve_plan(args.issue, args.by)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3
    print(f"Plan approved by {args.by} for {args.issue}")
    print(json.dumps(manifest, indent=2))
    return 0


def cmd_test(args: argparse.Namespace) -> int:
    locked, msg = is_locked()
    if locked:
        print(f"BLOCKED: {msg}", file=sys.stderr)
        return 4
    try:
        result = run_tester_step(args.issue, iteration=args.iteration)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 4
    print(json.dumps(result, indent=2))
    return 0 if result["verdict"] == "PASS" else 1


def cmd_dry_run(args: argparse.Namespace) -> int:
    try:
        print(dry_run_report(args.issue))
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3
    return 0


def cmd_lock(args: argparse.Namespace) -> int:
    ensure_overnight_dirs()
    write_lock(args.owner, args.reason, until=args.until)
    print(f"LOCK written for {args.owner!r}")
    return 0


def cmd_unlock(_: argparse.Namespace) -> int:
    clear_lock()
    print("LOCK cleared")
    return 0


def cmd_lock_status(_: argparse.Namespace) -> int:
    locked, msg = is_locked()
    if locked:
        print(f"LOCKED: {msg}")
        return 1
    print("No active LOCK")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Overnight self-healing flywheel (skeleton).")
    sub = parser.add_subparsers(dest="command", required=True)

    score_p = sub.add_parser("score", help="Rank Open items by deterministic ROI.")
    score_p.add_argument("--fix-type", default="code", help="Filter fix column (default: code).")
    score_p.add_argument("--limit", type=int, default=10)
    score_p.set_defaults(func=cmd_score)

    init_p = sub.add_parser("init", help="Create manifest + fix_plan template for an issue.")
    init_p.add_argument("--issue", required=True)
    init_p.add_argument("--max-iterations", type=int, default=3)
    init_p.add_argument("--force", action="store_true", help="Init even when LOCK is held.")
    init_p.set_defaults(func=cmd_init)

    val_p = sub.add_parser("validate-plan", help="Validate fix_plan.md frontmatter and scope.")
    val_p.add_argument("--issue", required=True)
    val_p.set_defaults(func=cmd_validate_plan)

    appr_p = sub.add_parser("approve-plan", help="Human approval marker for fix_type=agent.")
    appr_p.add_argument("--issue", required=True)
    appr_p.add_argument("--by", required=True, help="Approver id (e.g. stan).")
    appr_p.set_defaults(func=cmd_approve_plan)

    test_p = sub.add_parser("test", help="Run test commands from fix_plan → test_result.json.")
    test_p.add_argument("--issue", required=True)
    test_p.add_argument("--iteration", type=int, default=1)
    test_p.set_defaults(func=cmd_test)

    dry_p = sub.add_parser("dry-run", help="Print manual flywheel steps (no SDK).")
    dry_p.add_argument("--issue", required=True)
    dry_p.set_defaults(func=cmd_dry_run)

    lock_p = sub.add_parser("lock", help="Reserve repo for human architect.")
    lock_p.add_argument("--owner", required=True)
    lock_p.add_argument("--reason", default="active development session")
    lock_p.add_argument("--until", default=None, help="ISO8601 expiry (optional).")
    lock_p.set_defaults(func=cmd_lock)

    sub.add_parser("unlock", help="Clear human architect LOCK.").set_defaults(func=cmd_unlock)
    sub.add_parser("lock-status", help="Check LOCK state.").set_defaults(func=cmd_lock_status)

    return parser


def main() -> int:
    ensure_overnight_dirs()
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
