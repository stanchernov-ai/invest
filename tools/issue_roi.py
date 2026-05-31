#!/usr/bin/env python3
"""Rank action_tracker Open items by deterministic ROI (Analyst input).

Usage:
  .venv\\Scripts\\python.exe tools/issue_roi.py
  .venv\\Scripts\\python.exe tools/issue_roi.py --fix-type code --limit 5 --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.overnight.roi import rank_open_items


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic ROI rank for Open items.")
    parser.add_argument("--fix-type", default="code")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    fix_filter = None if args.fix_type.lower() == "any" else args.fix_type
    items = rank_open_items(fix_type=fix_filter, limit=args.limit)

    if args.json:
        print(json.dumps(items, indent=2))
        return 0

    if not items:
        print("No eligible items.")
        return 0

    for row in items:
        print(
            f"{row['roi_score']:6.1f}  {row.get('priority')}  {row.get('item_id')}  "
            f"{row.get('fix')}  {(row.get('item') or '')[:80]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
