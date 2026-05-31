"""Per-run QA agent scorecard — utilization + finding counts for tuning QA personas.

Persisted to api_telemetry as QA_SCORECARD and appended to ecosystem_state.json
as qa_scorecards[] for cross-run tracking.
"""
from __future__ import annotations

import logging
from typing import Any

from src.core.agents import agent_config
from src.hr_review import estimate_cost

logger = logging.getLogger(__name__)

QA_SCORECARD_KEYS = (
    "post_mortem_qa",
    "system_architect",
    "prompt_engineer",
    "graphics_designer_qa",
    "legal_counsel_qa",
    "qa_integrity_auditor",
)


def _role_to_key(agent_role: str) -> str | None:
    """Best-effort map from report agent_role string to agents.py key."""
    norm = (agent_role or "").lower()
    for key in QA_SCORECARD_KEYS:
        info = agent_config["board_members"].get(key, {})
        role = (info.get("role") or "").lower()
        if role and (role in norm or norm in role):
            return key
    if "deterministic" in norm and "visual" in norm:
        return "graphics_designer_qa"
    if "deterministic" in norm and "legal" in norm:
        return "legal_counsel_qa"
    if "legal counsel" in norm:
        return "legal_counsel_qa"
    if "deterministic" in norm and "integrity" in norm:
        return "qa_integrity_auditor"
    if "integrity" in norm:
        return "qa_integrity_auditor"
    return None


def _count_severity(findings: list[dict], severity: str) -> int:
    return sum(1 for f in (findings or []) if str(f.get("severity", "")).upper() == severity.upper())


def build_qa_scorecard(
    run_id: str,
    qa_reports: list[dict],
    agent_activity: dict[str, dict] | None = None,
) -> dict[str, Any]:
    """Build a scorecard row per QA agent report + AGENT_ACTIVITY merge."""
    activity = agent_activity or {}
    agents: list[dict] = []
    totals = {
        "critical_findings": 0,
        "warning_findings": 0,
        "compliant_count": 0,
        "non_compliant_count": 0,
        "total_tokens": 0,
        "est_cost_usd": 0.0,
    }

    for report in qa_reports or []:
        role = report.get("agent_role", "Unknown")
        key = _role_to_key(role)
        act = activity.get(key or "", {})
        model = act.get("model", "n/a")
        findings = report.get("findings") or []
        crit = _count_severity(findings, "CRITICAL")
        warn = _count_severity(findings, "WARNING")
        info = _count_severity(findings, "INFO")
        invocations = act.get("invocations", 0)
        errors = act.get("errors", 0)
        prompt_t = act.get("prompt_tokens", 0)
        out_t = act.get("output_tokens", 0)
        think_t = act.get("thinking_tokens", 0)
        total_t = act.get("total_tokens", 0) or (prompt_t + out_t + think_t)
        cost = estimate_cost(model, prompt_t, out_t, think_t) if invocations else 0.0
        is_compliant = bool(report.get("is_compliant"))

        row = {
            "agent_key": key,
            "agent_role": role,
            "is_compliant": is_compliant,
            "critical_findings": crit,
            "warning_findings": warn,
            "info_findings": info,
            "invocations": invocations,
            "errors": errors,
            "total_tokens": total_t,
            "est_cost_usd": cost,
            "idle": invocations == 0 and key in QA_SCORECARD_KEYS,
            "human_confirmed": None,
            "human_notes": None,
        }
        agents.append(row)

        totals["critical_findings"] += crit
        totals["warning_findings"] += warn
        totals["total_tokens"] += total_t
        totals["est_cost_usd"] += cost
        if is_compliant:
            totals["compliant_count"] += 1
        else:
            totals["non_compliant_count"] += 1

    return {
        "run_id": run_id,
        "agents": agents,
        "totals": totals,
        "summary": (
            f"{totals['compliant_count']} PASS / {totals['non_compliant_count']} FAIL · "
            f"{totals['critical_findings']} CRITICAL · ~${totals['est_cost_usd']:.4f} est."
        ),
    }


def persist_scorecard(scorecard: dict, *, phase: str = "deliver") -> None:
    """Append scorecard summary to ecosystem_state.json (never raises)."""
    try:
        from tools.ecosystem_state import append_entry

        append_entry("qa_scorecards", {
            "phase": phase,
            "run_id": scorecard.get("run_id"),
            "summary": scorecard.get("summary"),
            "agents": scorecard.get("agents"),
            "totals": scorecard.get("totals"),
            "evidence_ref": f"api_telemetry_{scorecard.get('run_id')}.json → QA_SCORECARD",
        })
    except Exception as e:
        logger.warning(f"Could not persist QA scorecard to ecosystem state: {e}")
