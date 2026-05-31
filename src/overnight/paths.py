"""Path helpers for overnight run directories."""
from __future__ import annotations

from pathlib import Path

from src.overnight.constants import OVERNIGHT_ROOT, RUNS_DIR, WORKTREES_DIR


def ensure_overnight_dirs() -> None:
    OVERNIGHT_ROOT.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    WORKTREES_DIR.mkdir(parents=True, exist_ok=True)
    (OVERNIGHT_ROOT / "templates").mkdir(parents=True, exist_ok=True)


def run_dir(issue_id: str) -> Path:
    return RUNS_DIR / issue_id


def manifest_path(issue_id: str) -> Path:
    return run_dir(issue_id) / "manifest.json"


def fix_plan_path(issue_id: str) -> Path:
    return run_dir(issue_id) / "fix_plan.md"


def iteration_dir(issue_id: str, iteration: int) -> Path:
    return run_dir(issue_id) / "iterations" / f"{iteration:02d}"


def test_result_path(issue_id: str, iteration: int) -> Path:
    return iteration_dir(issue_id, iteration) / "test_result.json"


def supervisor_summary_path(issue_id: str) -> Path:
    return run_dir(issue_id) / "supervisor_summary.json"


def worktree_path(issue_id: str) -> Path:
    safe = issue_id.replace("/", "-").lower()
    return WORKTREES_DIR / f"ai-fix-{safe}"


def branch_name(issue_id: str) -> str:
    safe = issue_id.replace("/", "-").lower()
    return f"ai/fix-{safe}"
