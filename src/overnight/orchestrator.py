"""Tier 1 overnight flywheel orchestrator — skeleton (no Cursor SDK)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from src.overnight.constants import TEMPLATE_PATH
from src.overnight.fix_plan import parse_fix_plan, validate_fix_plan
from src.overnight.lock import is_locked
from src.overnight.manifest import (
    build_supervisor_summary,
    create_manifest,
    load_manifest,
    save_manifest,
)
from src.overnight.paths import (
    ensure_overnight_dirs,
    fix_plan_path,
    run_dir,
    supervisor_summary_path,
)
from src.overnight.roi import rank_open_items
from src.overnight.test_result import run_test_suite


def _find_backlog_item(issue_id: str) -> dict[str, Any]:
    for item in rank_open_items(fix_type=None, limit=500):
        if item.get("item_id") == issue_id:
            return item
    raise LookupError(f"Issue {issue_id!r} not found in action_tracker Open items")


def init_run(
    issue_id: str,
    *,
    max_iterations: int = 3,
    base_ref: str = "origin/main",
) -> dict[str, Any]:
    locked, msg = is_locked()
    if locked:
        raise RuntimeError(msg)

    item = _find_backlog_item(issue_id)
    manifest = create_manifest(item, base_ref=base_ref, max_iterations=max_iterations)

    rd = run_dir(issue_id)
    rd.mkdir(parents=True, exist_ok=True)
    plan_dest = fix_plan_path(issue_id)
    if not plan_dest.exists() and TEMPLATE_PATH.exists():
        text = TEMPLATE_PATH.read_text(encoding="utf-8")
        text = text.replace("{{ISSUE_ID}}", issue_id)
        text = text.replace("{{FIX_TYPE}}", str(item.get("fix") or "code"))
        text = text.replace("{{DESCRIPTION}}", str(item.get("item") or ""))
        plan_dest.write_text(text, encoding="utf-8")

    return manifest


def validate_plan_step(issue_id: str) -> tuple[bool, list[str]]:
    manifest = load_manifest(issue_id)
    plan_path = fix_plan_path(issue_id)
    if not plan_path.exists():
        return False, [f"missing fix_plan.md at {plan_path}"]

    plan = parse_fix_plan(plan_path)
    ok, errors = validate_fix_plan(
        plan,
        issue_id=issue_id,
        denylist=tuple(manifest["policy"]["denylist_globs"]),
        max_files=int(manifest["policy"]["max_files_touched"]),
        requires_human_approval=bool(manifest["policy"]["requires_human_plan_approval"]),
        approved_by=manifest.get("approved_by"),
    )
    if ok:
        manifest["status"] = "plan_ready"
        save_manifest(issue_id, manifest)
    return ok, errors


def approve_plan(issue_id: str, approver: str) -> dict[str, Any]:
    manifest = load_manifest(issue_id)
    manifest["approved_by"] = approver
    manifest["status"] = "plan_ready"
    save_manifest(issue_id, manifest)
    return manifest


def run_tester_step(issue_id: str, iteration: int = 1) -> dict[str, Any]:
    locked, msg = is_locked()
    if locked:
        raise RuntimeError(msg)

    manifest = load_manifest(issue_id)
    plan = parse_fix_plan(fix_plan_path(issue_id))
    manifest["status"] = "testing"
    save_manifest(issue_id, manifest)

    result = run_test_suite(
        issue_id,
        plan,
        iteration,
        denylist=tuple(manifest["policy"]["denylist_globs"]),
    )

    if result["verdict"] == "PASS":
        manifest["status"] = "passed"
        summary = build_supervisor_summary(
            issue_id,
            verdict="PASS",
            iterations_used=iteration,
            human_actions=[
                f"Review branch {manifest['git']['branch']} — tests passed.",
                f"Open PR (never auto-merge); mark {issue_id} done after prod validation.",
            ],
        )
        supervisor_summary_path(issue_id).write_text(
            json.dumps(summary, indent=2) + "\n",
            encoding="utf-8",
        )
        _append_supervisor_state(summary)
    elif iteration >= int(manifest["policy"]["max_iterations"]):
        manifest["status"] = "escalated"
        summary = build_supervisor_summary(
            issue_id,
            verdict="ESCALATE",
            iterations_used=iteration,
            human_actions=[
                f"Max iterations ({iteration}) reached for {issue_id}.",
                f"Inspect {run_dir(issue_id)} and fix manually.",
            ],
        )
        supervisor_summary_path(issue_id).write_text(
            json.dumps(summary, indent=2) + "\n",
            encoding="utf-8",
        )
        _append_supervisor_state(summary)
    else:
        manifest["status"] = "developing"

    save_manifest(issue_id, manifest)
    return result


def _append_supervisor_state(summary: dict[str, Any]) -> None:
    try:
        from tools.ecosystem_state import append_entry

        append_entry("supervisor_summaries", summary)
        append_entry("overnight_runs", {
            "issue_id": summary.get("issue_id"),
            "verdict": summary.get("verdict"),
            "run_kind": summary.get("run_kind"),
            "evidence_ref": summary.get("evidence_ref"),
        })
    except Exception:
        pass


def dry_run_report(issue_id: str) -> str:
    """Human-readable steps — no Cursor SDK in skeleton v1."""
    manifest = load_manifest(issue_id)
    plan_exists = fix_plan_path(issue_id).exists()
    lines = [
        f"Overnight flywheel dry-run: {issue_id}",
        f"  status: {manifest.get('status')}",
        f"  branch: {manifest['git']['branch']}",
        f"  worktree: {manifest['git']['worktree_path']}",
        f"  fix_plan.md: {'present' if plan_exists else 'MISSING — copy from template'}",
        f"  requires_human_plan_approval: {manifest['policy']['requires_human_plan_approval']}",
        "",
        "Manual steps (Cursor SDK not wired in skeleton):",
        "  1. git worktree add <worktree> -b <branch> <base_ref>",
        "  2. Architect: edit fix_plan.md → verdict READY",
        f"  3. tools/overnight_fix.py validate-plan --issue {issue_id}",
        "  4. Developer: implement in worktree (Cursor Agent)",
        f"  5. tools/overnight_fix.py test --issue {issue_id} --iteration 1",
        "  6. On PASS: gh pr create — never push main",
        "",
        "Forbidden: auto-merge, auto-deploy, auto /api/prepare",
    ]
    return "\n".join(lines)
