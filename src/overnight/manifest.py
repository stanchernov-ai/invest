"""Run manifest and supervisor summary for one overnight issue."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.overnight.constants import (
    DEFAULT_DENYLIST_GLOBS,
    DEFAULT_MAX_FILES_TOUCHED,
    DEFAULT_MAX_ITERATIONS,
    FIX_TYPE_REQUIRES_APPROVAL,
    SCHEMA_VERSION,
)
from src.overnight.paths import (
    ensure_overnight_dirs,
    manifest_path,
    run_dir,
    worktree_path,
    branch_name,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_manifest(issue_id: str) -> dict[str, Any]:
    path = manifest_path(issue_id)
    if not path.exists():
        raise FileNotFoundError(f"No manifest for {issue_id!r} at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_manifest(issue_id: str, manifest: dict[str, Any]) -> Path:
    ensure_overnight_dirs()
    rd = run_dir(issue_id)
    rd.mkdir(parents=True, exist_ok=True)
    manifest["updated_at"] = _utc_now()
    path = manifest_path(issue_id)
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return path


def create_manifest(
    backlog_item: dict[str, Any],
    *,
    base_ref: str = "origin/main",
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
) -> dict[str, Any]:
    issue_id = backlog_item["item_id"]
    fix_type = str(backlog_item.get("fix") or "code").lower()
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "issue_id": issue_id,
        "backlog_ref": {
            "tracker_id": issue_id,
            "priority": backlog_item.get("priority"),
            "fix_type": fix_type,
            "source_agent": backlog_item.get("source"),
            "description": backlog_item.get("item"),
            "evidence_refs": [backlog_item.get("evidence")] if backlog_item.get("evidence") else [],
        },
        "git": {
            "base_ref": base_ref,
            "worktree_path": str(worktree_path(issue_id)),
            "branch": branch_name(issue_id),
        },
        "policy": {
            "max_iterations": max_iterations,
            "max_files_touched": DEFAULT_MAX_FILES_TOUCHED,
            "denylist_globs": list(DEFAULT_DENYLIST_GLOBS),
            "allowlist_globs": None,
            "requires_human_plan_approval": fix_type in FIX_TYPE_REQUIRES_APPROVAL,
            "forbid_auto_merge": True,
            "forbid_auto_deploy": True,
            "forbid_auto_prepare": True,
        },
        "status": "pending_plan",
        "approved_by": None,
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
    }
    save_manifest(issue_id, manifest)
    return manifest


def build_supervisor_summary(
    issue_id: str,
    *,
    verdict: str,
    iterations_used: int,
    human_actions: list[str],
    agents_reviewed: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "run_kind": "overnight_fix",
        "phase": "overnight_fix",
        "issue_id": issue_id,
        "verdict": verdict,
        "iterations_used": iterations_used,
        "agents_reviewed": agents_reviewed or ["architect", "developer", "tester"],
        "conflicts_resolved": [],
        "human_actions": human_actions,
        "evidence_ref": str(run_dir(issue_id)),
        "generated_at": _utc_now(),
    }
