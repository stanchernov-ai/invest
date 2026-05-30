#!/usr/bin/env python3
"""Deterministic post-job sync — activates Cursor dev-plane agents without Cursor chat.

Reads cached Azure artifacts and writes api_audit, data_insights, and supervisor_summaries
to ecosystem_state.json. Replaces manual API Optimization / Data Insight / Supervisor steps.

Usage (from repo root):
  .venv\\Scripts\\python.exe tools/post_job_sync.py --run-id 20260529_152151
  .venv\\Scripts\\python.exe tools/post_job_sync.py --run-id 20260529_152151 --sync-ecosystem
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

RUN_ID_RE = re.compile(r"^\d{8}_\d{6}$")

# Agents expected on a full successful run (debate + deliver).
EXPECTED_ACTIVE_KEYS = frozenset({
    "buffett", "lynch", "livermore", "huang", "simons", "clerk", "red_teamer",
    "post_mortem_qa", "system_architect", "prompt_engineer", "graphics_designer_qa",
    "qa_integrity_auditor",
})

OPTIONAL_KEYS = frozenset({"chairman", "compliance"})


def _count_severity(reports: list[dict], severity: str) -> int:
    total = 0
    for report in reports or []:
        for finding in report.get("findings") or []:
            if str(finding.get("severity", "")).upper() == severity.upper():
                total += 1
    return total


def _already_post_job(bucket: list, run_id: str, agent: str) -> bool:
    return any(
        isinstance(e, dict)
        and e.get("run_id") == run_id
        and e.get("agent") == agent
        and e.get("phase") == "post_job"
        for e in bucket
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

    telemetry_path = cache / "state" / f"api_telemetry_{run_id}.json"
    if not telemetry_path.exists():
        raise FileNotFoundError(f"Missing {telemetry_path} — run fetch_azure_reports first.")

    telemetry = json.loads(telemetry_path.read_text(encoding="utf-8"))
    activity = telemetry.get("AGENT_ACTIVITY") or {}

    qa_reports_path = cache / "state" / f"qa_reports_{run_id}.json"
    qa_reports = []
    if qa_reports_path.exists():
        qa_reports = json.loads(qa_reports_path.read_text(encoding="utf-8"))

    from src.hr_review import build_utilization
    from tools.ecosystem_state import append_entry, load_state

    state = load_state()
    rows = build_utilization(activity)
    idle = [r["agent"] for r in rows if r.get("idle") and r["agent"] in EXPECTED_ACTIVE_KEYS]
    unexpected_idle = [k for k in OPTIONAL_KEYS if activity.get(k, {}).get("invocations", 0) == 0]
    token_ranking = [
        {"agent": r["agent"], "total_tokens": r["total_tokens"], "est_cost_usd": r["est_cost_usd"]}
        for r in rows[:8]
        if r.get("total_tokens", 0) > 0
    ]
    total_tokens = sum(r.get("total_tokens", 0) for r in rows)
    total_cost = round(sum(r.get("est_cost_usd", 0) for r in rows), 4)

    crit = _count_severity(qa_reports, "CRITICAL")
    warn = _count_severity(qa_reports, "WARNING")
    chairman_bypassed = telemetry.get("chairman_bypassed")
    munger_skipped = telemetry.get("munger_skipped")

    api_findings: list[str] = []
    if idle:
        api_findings.append(
            f"Idle expected agents ({len(idle)}): {', '.join(idle)} — verify pipeline wiring."
        )
    if chairman_bypassed and not unexpected_idle:
        api_findings.append(
            "Chairman bypass active — chairman/compliance LLM idle is expected on vote_engine days."
        )
    elif unexpected_idle:
        api_findings.append(
            f"Optional agents with zero invocations: {', '.join(unexpected_idle)}."
        )
    if munger_skipped:
        api_findings.append("Munger concentration pass skipped (vote_engine bypass day).")
    if token_ranking:
        top = token_ranking[0]
        api_findings.append(
            f"Top token spend: {top['agent']} (~{top['total_tokens']:,} tokens, "
            f"~${top['est_cost_usd']:.4f})."
        )
    if not api_findings:
        api_findings.append("No idle-agent or token anomalies detected.")

    insight_findings: list[str] = []
    if crit:
        insight_findings.append(f"{crit} CRITICAL QA finding(s) — review qa_reports_{run_id}.json.")
    if warn:
        insight_findings.append(f"{warn} WARNING QA finding(s) in deliver QA stack.")
    scorecard = telemetry.get("QA_SCORECARD") or {}
    if scorecard.get("totals", {}).get("non_compliant_count", 0):
        insight_findings.append(
            f"QA scorecard: {scorecard.get('summary', 'non-compliant agents reported')}."
        )
    if not insight_findings:
        insight_findings.append("No CRITICAL/WARNING QA themes flagged for backlog promotion.")

    if not _already_post_job(state.get("api_audit", []), run_id, "api_optimization"):
        append_entry("api_audit", {
            "agent": "api_optimization",
            "phase": "post_job",
            "run_id": run_id,
            "findings": api_findings,
            "idle_agents": idle,
            "token_ranking": token_ranking,
            "total_tokens": total_tokens,
            "est_cost_usd": total_cost,
            "evidence_ref": f"api_telemetry_{run_id}.json",
        })

    if not _already_post_job(state.get("data_insights", []), run_id, "data_insight"):
        append_entry("data_insights", {
            "agent": "data_insight",
            "phase": "post_job",
            "run_id": run_id,
            "findings": insight_findings,
            "qa_critical_count": crit,
            "qa_warning_count": warn,
            "evidence_ref": f"qa_reports_{run_id}.json",
        })

    if not _already_post_job(state.get("supervisor_summaries", []), run_id, "supervisor"):
        if crit >= 3:
            verdict = "BLOCKED"
        elif crit or idle:
            verdict = "PASS_WITH_WARNINGS"
        else:
            verdict = "PASS"

        human_actions: list[str] = []
        if crit:
            human_actions.append(
                f"Review {crit} CRITICAL QA finding(s) in qa_dashboard_{run_id}.html before promoting backlog items."
            )
        if idle and not (chairman_bypassed and set(idle) <= OPTIONAL_KEYS):
            human_actions.append(f"Confirm idle agents are intentional: {', '.join(idle[:5])}.")
        if not human_actions:
            human_actions.append("No immediate human action — spot-check briefing if desired.")

        append_entry("supervisor_summaries", {
            "agent": "supervisor",
            "phase": "post_job",
            "run_id": run_id,
            "agents_reviewed": ["api_optimization", "data_insight"],
            "verdict": verdict,
            "conflicts_resolved": [],
            "human_actions": human_actions,
            "summary": (
                f"Post-job sync for {run_id}: {verdict}. "
                f"~{total_tokens:,} tokens (~${total_cost:.4f}). "
                f"QA {crit} CRITICAL / {warn} WARNING."
            ),
            "evidence_ref": f"api_telemetry_{run_id}.json, qa_reports_{run_id}.json",
        })

    return {
        "run_id": run_id,
        "idle_agents": idle,
        "qa_critical_count": crit,
        "total_tokens": total_tokens,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic post-job ecosystem sync.")
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
        f"Post-job sync complete for {result['run_id']}: "
        f"{len(result['idle_agents'])} idle, {result['qa_critical_count']} QA CRITICAL, "
        f"~{result['total_tokens']:,} tokens."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
