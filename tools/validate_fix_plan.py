#!/usr/bin/env python3
"""Validate fix_plan.md for overnight flywheel.

Usage:
  .venv\\Scripts\\python.exe tools/validate_fix_plan.py --issue QA-090637-02
  .venv\\Scripts\\python.exe tools/validate_fix_plan.py --path .cursor/agent_state/overnight/runs/QA-090637-02/fix_plan.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.overnight.constants import DEFAULT_DENYLIST_GLOBS
from src.overnight.fix_plan import parse_fix_plan, validate_fix_plan
from src.overnight.manifest import load_manifest
from src.overnight.paths import fix_plan_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate overnight fix_plan.md")
    parser.add_argument("--issue", help="Issue id (loads manifest policy)")
    parser.add_argument("--path", help="Direct path to fix_plan.md")
    args = parser.parse_args()

    if args.path:
        plan_path = Path(args.path)
        issue_id = args.issue
        denylist = None
        max_files = 5
        requires_approval = False
        approved_by = None
    elif args.issue:
        plan_path = fix_plan_path(args.issue)
        issue_id = args.issue
        try:
            manifest = load_manifest(args.issue)
            denylist = tuple(manifest["policy"]["denylist_globs"])
            max_files = int(manifest["policy"]["max_files_touched"])
            requires_approval = bool(manifest["policy"]["requires_human_plan_approval"])
            approved_by = manifest.get("approved_by")
        except FileNotFoundError:
            denylist = None
            max_files = 5
            requires_approval = False
            approved_by = None
    else:
        print("Provide --issue or --path", file=sys.stderr)
        return 2

    if not plan_path.exists():
        print(f"ERROR: not found: {plan_path}", file=sys.stderr)
        return 3

    plan = parse_fix_plan(plan_path)
    ok, errors = validate_fix_plan(
        plan,
        issue_id=issue_id,
        denylist=denylist or DEFAULT_DENYLIST_GLOBS,
        max_files=max_files,
        requires_human_approval=requires_approval,
        approved_by=approved_by,
    )
    if ok:
        print(f"VALID: {plan_path}")
        return 0
    print(f"INVALID: {plan_path}", file=sys.stderr)
    for err in errors:
        print(f"  - {err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
