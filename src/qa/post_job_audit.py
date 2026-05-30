"""Deterministic post-job oversight — API Optimization, Data Insight, Supervisor.

Runs on Azure at end of deliver (writes ``post_job_oversight_{run_id}.json`` to
boardroom-state) and locally via ``tools/post_job_sync.py`` → ecosystem_state.json.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

RUN_ID_RE = re.compile(r"^\d{8}_\d{6}$")

EXPECTED_ACTIVE_KEYS = frozenset({
    "buffett", "lynch", "livermore", "huang", "simons", "clerk", "red_teamer",
    "post_mortem_qa", "system_architect", "prompt_engineer", "graphics_designer_qa",
    "qa_integrity_auditor",
})

OPTIONAL_KEYS = frozenset({"chairman", "compliance"})

OVERSIGHT_BLOB_PREFIX = "post_job_oversight_"


def oversight_blob_name(run_id: str) -> str:
    return f"{OVERSIGHT_BLOB_PREFIX}{run_id}.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _count_severity(reports: list[dict], severity: str) -> int:
    total = 0
    for report in reports or []:
        for finding in report.get("findings") or []:
            if str(finding.get("severity", "")).upper() == severity.upper():
                total += 1
    return total


def _qa_failures(qa_reports: list[dict]) -> list[str]:
    failed = []
    for report in qa_reports or []:
        if report.get("is_compliant"):
            continue
        role = report.get("agent_role") or "Unknown QA"
        crit = _count_severity([report], "CRITICAL")
        failed.append(f"{role} ({crit} CRITICAL)")
    return failed


def _agent_errors(activity: dict) -> list[str]:
    errors = []
    for agent, entry in (activity or {}).items():
        err_count = entry.get("errors", 0) or 0
        if err_count:
            errors.append(f"{agent}: {err_count} API error(s)")
    return errors


def build_post_job_oversight(
    run_id: str,
    telemetry: dict,
    qa_reports: list[dict] | None = None,
    *,
    run_status: dict | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build api_audit, data_insight, and supervisor_summary records for one run."""
    if not RUN_ID_RE.match(run_id):
        raise ValueError(f"Invalid run_id: {run_id!r}")

    from src.hr_review import build_utilization

    qa_reports = qa_reports or []
    activity = telemetry.get("AGENT_ACTIVITY") or {}
    rows = build_utilization(activity)
    idle = [r["agent"] for r in rows if r.get("idle") and r["agent"] in EXPECTED_ACTIVE_KEYS]
    unexpected_idle = [k for k in OPTIONAL_KEYS if activity.get(k, {}).get("invocations", 0) == 0]
    token_ranking = [
        {"agent": r["agent"], "total_tokens": r["total_tokens"], "est_cost_usd": r["est_cost_usd"]}
        for r in rows[:10]
        if r.get("total_tokens", 0) > 0
    ]
    total_tokens = sum(r.get("total_tokens", 0) for r in rows)
    total_cost = round(sum(r.get("est_cost_usd", 0) for r in rows), 4)

    crit = _count_severity(qa_reports, "CRITICAL")
    warn = _count_severity(qa_reports, "WARNING")
    chairman_bypassed = telemetry.get("chairman_bypassed")
    munger_skipped = telemetry.get("munger_skipped")
    compliance_source = telemetry.get("compliance_source")
    allocation_source = telemetry.get("allocation_source")
    scorecard = telemetry.get("QA_SCORECARD") or {}

    api_findings: list[str] = []
    if idle:
        api_findings.append(
            f"Idle expected agents ({len(idle)}): {', '.join(idle)} — verify pipeline wiring."
        )
    agent_errors = _agent_errors(activity)
    api_findings.extend(agent_errors)
    if chairman_bypassed:
        api_findings.append(
            f"Vote engine day: allocation_source={allocation_source!r}, "
            f"compliance_source={compliance_source!r}."
        )
        if unexpected_idle:
            api_findings.append(
                f"Chairman/compliance idle expected on bypass: {', '.join(unexpected_idle)}."
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
    eod_cache = telemetry.get("EOD_CACHE")
    if isinstance(eod_cache, dict):
        sym_count = eod_cache.get("symbol_count") or eod_cache.get("symbols_fetched")
        if sym_count:
            api_findings.append(f"EOD prefetch: {sym_count} symbol(s) in prepare cache.")

    qa_failed = _qa_failures(qa_reports)
    if qa_failed:
        api_findings.append(f"Non-compliant QA agents: {'; '.join(qa_failed)}.")

    if not api_findings:
        api_findings.append("No idle-agent, API error, or token anomalies detected.")

    insight_findings: list[str] = []
    if crit:
        insight_findings.append(f"{crit} CRITICAL QA finding(s) — review qa_reports_{run_id}.json.")
    if warn:
        insight_findings.append(f"{warn} WARNING QA finding(s) in deliver QA stack.")
    if scorecard.get("totals", {}).get("non_compliant_count", 0):
        insight_findings.append(
            f"QA scorecard: {scorecard.get('summary', 'non-compliant agents reported')}."
        )
    parsing = [
        f.get("description", "")[:120]
        for report in qa_reports
        for f in (report.get("findings") or [])
        if str(f.get("category", "")).lower() == "parsing error"
    ]
    if parsing:
        insight_findings.append(f"QA parsing failures: {len(parsing)} — check agent JSON output.")
    broken_charts = sum(
        1
        for report in qa_reports
        for f in (report.get("findings") or [])
        if str(f.get("category", "")).lower() == "broken chart"
    )
    if broken_charts:
        insight_findings.append(f"{broken_charts} broken chart finding(s) in Graphics QA.")

    if run_status:
        for phase in ("prepare", "debate", "deliver"):
            pdata = run_status.get(phase) or {}
            if pdata.get("status") == "failed":
                insight_findings.append(
                    f"Phase {phase} failed: {(pdata.get('error') or 'unknown')[:200]}."
                )
            elif pdata.get("requires_expert_review"):
                insight_findings.append(f"Phase {phase} flagged requires_expert_review.")

    if not insight_findings:
        insight_findings.append("No CRITICAL/WARNING QA themes flagged for backlog promotion.")

    if crit >= 3 or any("failed" in f.lower() for f in insight_findings):
        verdict = "BLOCKED"
    elif crit or warn or idle or agent_errors:
        verdict = "PASS_WITH_WARNINGS"
    else:
        verdict = "PASS"

    human_actions: list[str] = []
    if crit:
        human_actions.append(
            f"Review {crit} CRITICAL QA finding(s) in qa_dashboard_{run_id}.html."
        )
    if qa_failed:
        human_actions.append(f"Validate QA failures: {', '.join(qa_failed[:4])}.")
    if idle and not (chairman_bypassed and set(idle) <= {"post_mortem_qa", "prompt_engineer"}):
        human_actions.append(f"Confirm idle agents are intentional: {', '.join(idle[:5])}.")
    if agent_errors:
        human_actions.append("Inspect Gemini API errors in Application Insights.")
    if not human_actions:
        human_actions.append("No immediate human action — spot-check briefing if desired.")

    stamp = generated_at or _utc_now()
    api_audit = {
        "recorded_at": stamp,
        "agent": "api_optimization",
        "phase": "post_job",
        "run_id": run_id,
        "findings": api_findings,
        "idle_agents": idle,
        "agent_errors": agent_errors,
        "token_ranking": token_ranking,
        "total_tokens": total_tokens,
        "est_cost_usd": total_cost,
        "evidence_ref": f"api_telemetry_{run_id}.json",
    }
    data_insight = {
        "recorded_at": stamp,
        "agent": "data_insight",
        "phase": "post_job",
        "run_id": run_id,
        "findings": insight_findings,
        "qa_critical_count": crit,
        "qa_warning_count": warn,
        "qa_failures": qa_failed,
        "evidence_ref": f"qa_reports_{run_id}.json",
    }
    supervisor_summary = {
        "recorded_at": stamp,
        "agent": "supervisor",
        "phase": "post_job",
        "run_id": run_id,
        "agents_reviewed": ["api_optimization", "data_insight"],
        "verdict": verdict,
        "conflicts_resolved": [],
        "human_actions": human_actions,
        "summary": (
            f"Post-job oversight for {run_id}: {verdict}. "
            f"~{total_tokens:,} tokens (~${total_cost:.4f}). "
            f"QA {crit} CRITICAL / {warn} WARNING."
        ),
        "evidence_ref": f"{oversight_blob_name(run_id)}, qa_reports_{run_id}.json",
    }

    return {
        "run_id": run_id,
        "generated_at": stamp,
        "api_audit": api_audit,
        "data_insight": data_insight,
        "supervisor_summary": supervisor_summary,
        "metrics": {
            "idle_agents": idle,
            "qa_critical_count": crit,
            "qa_warning_count": warn,
            "total_tokens": total_tokens,
            "verdict": verdict,
        },
    }


def save_post_job_oversight_blob(bundle: dict) -> str:
    """Persist oversight bundle to boardroom-state (never raises)."""
    run_id = bundle.get("run_id")
    if not run_id:
        raise ValueError("bundle missing run_id")
    blob_name = oversight_blob_name(run_id)
    try:
        from src import storage_client

        storage_client.save_state_blob(blob_name, bundle)
        logger.info("[POST_JOB] Saved %s (verdict=%s).", blob_name, bundle.get("metrics", {}).get("verdict"))
    except Exception as exc:
        logger.warning("[POST_JOB] Could not save oversight blob: %s", exc)
        raise
    return blob_name


def execute_post_job_oversight(
    run_id: str,
    telemetry: dict,
    qa_reports: list[dict] | None = None,
    *,
    run_status: dict | None = None,
) -> dict:
    """Build + persist Azure oversight blob at end of deliver."""
    bundle = build_post_job_oversight(
        run_id, telemetry, qa_reports, run_status=run_status,
    )
    save_post_job_oversight_blob(bundle)
    return bundle


def append_oversight_to_ecosystem(bundle: dict) -> dict[str, bool]:
    """Append oversight records to local ecosystem_state.json (idempotent)."""
    from tools.ecosystem_state import append_entry, load_state

    run_id = bundle["run_id"]
    state = load_state()
    synced = {"api_audit": False, "data_insight": False, "supervisor_summaries": False}

    def _present(bucket: list, *, agent: str) -> bool:
        return any(
            isinstance(e, dict)
            and e.get("run_id") == run_id
            and e.get("agent") == agent
            and e.get("phase") == "post_job"
            for e in bucket
        )

    if not _present(state.get("api_audit", []), agent="api_optimization"):
        append_entry("api_audit", bundle["api_audit"])
        synced["api_audit"] = True
    if not _present(state.get("data_insights", []), agent="data_insight"):
        append_entry("data_insights", bundle["data_insight"])
        synced["data_insight"] = True
    if not _present(state.get("supervisor_summaries", []), agent="supervisor"):
        append_entry("supervisor_summaries", bundle["supervisor_summary"])
        synced["supervisor_summaries"] = True
    return synced


def load_oversight_from_cache(cache_dir, run_id: str) -> dict | None:
    """Load post_job_oversight blob from local fetch cache."""
    from pathlib import Path

    path = Path(cache_dir) / "state" / oversight_blob_name(run_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
