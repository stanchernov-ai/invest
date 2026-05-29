#!/usr/bin/env python3
"""Pre-commit gate: tests + lightweight refactoring checks.

Invoked by .githooks/pre-commit. Logs results to ecosystem_state.json.
Exit 0 = allow commit, 1 = block commit.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.ecosystem_state import append_entry

VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
if not VENV_PYTHON.exists():
    VENV_PYTHON = ROOT / ".venv" / "bin" / "python"

DEAD_FMP_PATTERNS = (
    "/stable/rating",
    "/stable/earning_calendar",
    "stable/earning_calendar",
)

# Starter-tier blocked in production data layer only (probe scripts may reference it).
BATCH_QUOTE_PATTERN = "batch-quote"


def _is_production_path(rel: str) -> bool:
    return rel.startswith("src/data/") or rel.startswith("src/jobs/") or rel == "src/main.py"


def _run_tests() -> tuple[bool, str]:
    cmd = [
        str(VENV_PYTHON),
        "-m",
        "unittest",
        "discover",
        "-s",
        "tests",
        "-v",
    ]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, output.strip()


def _staged_python_files() -> list[Path]:
    proc = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return []
    files = []
    for line in proc.stdout.splitlines():
        path = ROOT / line.strip()
        if path.suffix == ".py" and path.exists():
            files.append(path)
    return files


def _refactoring_violations(staged_files: list[Path]) -> list[str]:
    violations: list[str] = []
    for path in staged_files:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            violations.append(f"{path.relative_to(ROOT)}: unreadable ({exc})")
            continue
        rel = path.relative_to(ROOT).as_posix()
        if not rel.startswith("src/"):
            continue
        for pattern in DEAD_FMP_PATTERNS:
            if pattern in text:
                violations.append(f"{rel}: contains forbidden API pattern {pattern!r}")
        if _is_production_path(rel) and BATCH_QUOTE_PATTERN in text:
            violations.append(
                f"{rel}: contains {BATCH_QUOTE_PATTERN!r} (HTTP 402 on Starter — use parallel /stable/quote)"
            )
    return violations


def main() -> int:
    if not VENV_PYTHON.exists():
        print("pre-commit: .venv python not found. Run: python -m venv .venv && pip install -r requirements.txt")
        return 1

    staged = _staged_python_files()
    refactor_violations = _refactoring_violations(staged)
    tests_ok, test_output = _run_tests()

    verdict = "PASS"
    if refactor_violations or not tests_ok:
        verdict = "BLOCK"

    append_entry(
        "qa_flags",
        {
            "agent": "qa_validation",
            "phase": "pre_commit",
            "verdict": verdict,
            "tests_passed": tests_ok,
            "staged_python_files": [p.relative_to(ROOT).as_posix() for p in staged],
            "refactoring_violations": refactor_violations,
            "evidence_ref": "scripts/pre_commit_check.py",
        },
    )

    if refactor_violations:
        print("pre-commit BLOCKED — Refactoring Agent findings:")
        for item in refactor_violations:
            print(f"  - {item}")
        print("See docs/fmp_data_dictionary.md for replacements.")
        return 1

    if not tests_ok:
        print("pre-commit BLOCKED — tests failed:")
        print(test_output[-4000:] if len(test_output) > 4000 else test_output)
        return 1

    print("pre-commit PASS — tests green, no forbidden API patterns in staged files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
