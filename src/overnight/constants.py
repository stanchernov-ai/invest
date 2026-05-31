"""Shared constants for overnight flywheel artifacts."""
from __future__ import annotations

from pathlib import Path

SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parents[2]
OVERNIGHT_ROOT = REPO_ROOT / ".cursor" / "agent_state" / "overnight"
RUNS_DIR = OVERNIGHT_ROOT / "runs"
WORKTREES_DIR = OVERNIGHT_ROOT / "worktrees"
LOCK_PATH = OVERNIGHT_ROOT / "LOCK"
TEMPLATE_PATH = OVERNIGHT_ROOT / "templates" / "fix_plan.template.md"

DEFAULT_MAX_ITERATIONS = 3
DEFAULT_MAX_FILES_TOUCHED = 5

# Tier 1 autonomous denylist — financial / debate arbitration (see overnight_flywheel_review.md).
DEFAULT_DENYLIST_GLOBS = (
    "src/core/vote_engine.py",
    "src/core/guardrails.py",
    "src/core/compliance_audit.py",
    "src/core/engine.py",
    "src/core/chairman_alignment.py",
    "src/verdict_memory.py",
)

FINANCIAL_KEYWORDS = frozenset({
    "vote_engine",
    "liquidation",
    "allocation",
    "funding sell",
    "compliance_audit",
    "chairman",
    "verdict_memory",
})

FIX_TYPE_REQUIRES_APPROVAL = frozenset({"agent"})

VERDICT_READY = "READY"
VERDICT_DRAFT = "DRAFT"
VERDICT_BLOCKED = "BLOCKED"

RUN_STATUSES = frozenset({
    "pending_plan",
    "plan_ready",
    "developing",
    "testing",
    "passed",
    "escalated",
    "aborted",
})
