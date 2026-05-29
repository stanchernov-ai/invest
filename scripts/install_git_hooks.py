#!/usr/bin/env python3
"""Point this repo at .githooks/ (run once per clone).

  .venv\\Scripts\\python.exe scripts\\install_git_hooks.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOKS_DIR = ROOT / ".githooks"
PRE_COMMIT = HOOKS_DIR / "pre-commit"


def main() -> int:
    if not PRE_COMMIT.is_file():
        print(f"Missing {PRE_COMMIT}", file=sys.stderr)
        return 1

    rel_hooks = ".githooks"
    proc = subprocess.run(
        ["git", "config", "core.hooksPath", rel_hooks],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        return proc.returncode

    print(f"Installed git hooks: core.hooksPath = {rel_hooks}")
    print(f"Pre-commit runs: {PRE_COMMIT.name} -> scripts/pre_commit_check.py")
    print("Test with a dry run: git commit --allow-empty -m \"hook test\" (then reset if needed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
