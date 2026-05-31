"""HR Efficiency Consultant (Action Tracker 5.4).

Keeps the agent roster lean as we keep adding agents. It pairs a *deterministic*
utilization report (built from the per-agent activity ledger captured in
`agent_activity` and persisted into telemetry as `AGENT_ACTIVITY`) with an LLM
reviewer that issues keep / merge / cut verdicts and proposes new roles.

The deterministic table is the ground truth (invocations, tokens, est. cost,
execution status); the LLM reasons about redundancy, impact, and prompt gaps on
top of it — it never has to guess who fired.

Standalone usage (reads AGENT_ACTIVITY from a telemetry JSON, prints the table):
  .venv\\Scripts\\python.exe -m src.hr_review .cache/state/api_telemetry_YYYYMMDD_HHMMSS.json
"""
import os
import sys
import json
import asyncio
import logging
from typing import Literal

from pydantic import BaseModel, Field
from google.genai import types

from src.core.agents import (
    agent_config, call_gemini_async, HEAVY_MODEL, FAST_MODEL, FLASH_TOKEN_LIMIT,
)
from src.qa.qa_augmentation import execution_mode_display

logger = logging.getLogger(__name__)

# Rough Gemini 2.5 pricing, USD per 1M tokens. ESTIMATE ONLY - verify against the
# current Google AI pricing page and update here if it changes. Thinking tokens
# are billed as output. Tokens (not dollars) are the source of truth; cost is a
# convenience proxy for the keep/merge/cut conversation.
PRICING = {
    FAST_MODEL: {"input": 0.30, "output": 2.50},
    HEAVY_MODEL: {"input": 1.25, "output": 10.00},
}

INFRA_AGENTS = frozenset({"data_oracle"})
ON_DEMAND_AGENTS = frozenset({"legal_counsel_code"})

PIPELINE_DATAFLOW_NOTE = (
    "Pipeline data flow (for consumed-by reasoning):\n"
    "- Panel (hypatia, davinci, suntzu, tesla, aurelius): two-round debate; primary token spend.\n"
    "- clerk: synthesizes debate for downstream consumers.\n"
    "- chairman: final allocations — often VOTE_ENGINE (Python) when board majority is clear; "
    "Pro LLM chairman reserved for ambiguous days and future per-user investment-style personas.\n"
    "- compliance: audits chairman; PYTHON_GATE when vote_engine ran (no LLM).\n"
    "- red_teamer (The Crucible): adversarial rebuttals — consumed in investor briefing (Alpha Pick, "
    "Unicorn Protocol); does not change allocation math.\n"
    "- data_oracle: INFRA — deterministic price gate in prepare (not an LLM roster seat).\n"
    "- Post-flight QA: Python pre-checks first; LLM augments on FAIL, borderline persona, "
    "architect structural FAIL, or post-mortem spot-check (see QA_EXECUTION / STATUS column).\n"
    "- legal_counsel_qa: briefing HTML review in deliver; legal_counsel_code is on-demand codebase audit.\n"
    "Prefer KEEP + prompt/configuration improvements over CUT unless an agent has no downstream consumer."
)


class AgentVerdict(BaseModel):
    agent: str = Field(description="The agent key/role being judged.")
    recommendation: Literal["KEEP", "MERGE", "CUT", "ADD_BUDGET", "WATCH", "IMPROVE"] = Field(
        description="KEEP=earning its seat; MERGE=fold into another agent; CUT=remove; "
                    "ADD_BUDGET=under-resourced/high-value; WATCH=monitor; "
                    "IMPROVE=retain but upgrade prompts/config (preferred over CUT)."
    )
    rationale: str = Field(description="One or two sentences citing utilization, redundancy, or impact.")


class HRReport(BaseModel):
    summary: str = Field(description="High-level read on roster health and the biggest efficiency win.")
    roster_health_score: int = Field(description="1 (bloated/wasteful) to 5 (lean and fully utilized).")
    agent_verdicts: list[AgentVerdict] = Field(description="A verdict for every agent in the roster.")
    redundancies: list[str] = Field(default_factory=list, description="Specific overlaps or discarded/unconsumed outputs.")
    proposed_new_roles: list[str] = Field(default_factory=list, description="Missing roles that would add clear value.")


def roster() -> dict[str, dict]:
    """The pipeline agent roster: key -> {role, model, instruction excerpt}."""
    out = {}
    for key, info in agent_config.get("board_members", {}).items():
        instr = info.get("system_instruction", "")
        out[key] = {
            "role": info.get("role", key),
            "model": info.get("model", "unknown"),
            "summary": (instr[:200] + "...") if len(instr) > 200 else instr,
            "infra": key in INFRA_AGENTS,
        }
    return out


def estimate_cost(model: str, prompt_tokens: int, output_tokens: int, thinking_tokens: int) -> float:
    price = PRICING.get(model)
    if not price:
        return 0.0
    inp = (prompt_tokens / 1_000_000) * price["input"]
    out = ((output_tokens + thinking_tokens) / 1_000_000) * price["output"]
    return round(inp + out, 4)


def resolve_execution_status(agent: str, row: dict, telemetry: dict | None) -> str:
    """Human-readable status: distinguish idle vs deterministic vs vote-engine paths."""
    tel = telemetry or {}
    qa_exec = tel.get("QA_EXECUTION") or {}
    if agent in qa_exec:
        return execution_mode_display(qa_exec[agent])

    inv = row.get("invocations", 0) or 0
    if inv > 0:
        return "OK" if not row.get("errors") else "ERRORS"

    if agent in INFRA_AGENTS:
        return "INFRA"
    if agent in ON_DEMAND_AGENTS:
        return "ON_DEMAND"
    if agent == "chairman" and tel.get("chairman_bypassed"):
        return "VOTE_ENGINE"
    if agent == "compliance" and tel.get("compliance_source") == "python_only":
        return "PYTHON_GATE"
    if agent in {"post_mortem_qa", "prompt_engineer", "system_architect"}:
        return "DET_PASS"
    return "NOT_INVOKED"


def build_utilization(activity: dict, telemetry: dict | None = None) -> list[dict]:
    """Merge roster + activity ledger; attach execution status from telemetry."""
    activity = activity or {}
    r = roster()
    keys = set(r.keys()) | set(activity.keys())
    rows = []
    for key in keys:
        act = activity.get(key, {})
        meta = r.get(key, {})
        model = act.get("model") or meta.get("model", "unknown")
        prompt_t = act.get("prompt_tokens", 0)
        out_t = act.get("output_tokens", 0)
        think_t = act.get("thinking_tokens", 0)
        total_t = act.get("total_tokens", 0) or (prompt_t + out_t + think_t)
        invs = act.get("invocations", 0)
        status = resolve_execution_status(key, {"invocations": invs, "errors": act.get("errors", 0)}, telemetry)
        rows.append({
            "agent": key,
            "role": meta.get("role", key),
            "model": model,
            "invocations": invs,
            "errors": act.get("errors", 0),
            "prompt_tokens": prompt_t,
            "output_tokens": out_t,
            "thinking_tokens": think_t,
            "total_tokens": total_t,
            "est_cost_usd": estimate_cost(model, prompt_t, out_t, think_t),
            "status": status,
            "idle": status == "NOT_INVOKED",
            "in_roster": key in r,
            "infra": meta.get("infra", key in INFRA_AGENTS),
        })
    rows.sort(key=lambda x: (x["est_cost_usd"], x["total_tokens"]), reverse=True)
    return rows


def format_utilization_text(rows: list[dict]) -> str:
    if not rows:
        return "No agent activity recorded for this run."
    lines = [
        f"{'AGENT':<22}{'MODEL':<18}{'CALLS':>6}{'ERR':>5}{'TOToks':>10}{'~USD':>9}  STATUS",
    ]
    tot_calls = tot_tokens = 0
    tot_cost = 0.0
    for r in rows:
        lines.append(
            f"{r['agent']:<22}{r['model']:<18}{r['invocations']:>6}{r['errors']:>5}"
            f"{r['total_tokens']:>10,}{r['est_cost_usd']:>9.4f}  {r['status']}"
        )
        tot_calls += r["invocations"]
        tot_tokens += r["total_tokens"]
        tot_cost += r["est_cost_usd"]
    lines.append(f"{'TOTAL':<22}{'':<18}{tot_calls:>6}{'':>5}{tot_tokens:>10,}{tot_cost:>9.4f}")
    run_meta = []
    if rows and any(r.get("status") == "VOTE_ENGINE" for r in rows):
        run_meta.append("Run note: chairman_bypassed=true (vote_engine allocation).")
    idle_count = sum(1 for r in rows if r.get("idle") and r.get("in_roster"))
    if idle_count:
        run_meta.append(f"True NOT_INVOKED roster agents: {idle_count}.")
    if run_meta:
        lines.append("")
        lines.extend(run_meta)
    return "\n".join(lines)


def render_utilization_html(rows: list[dict]) -> str:
    if not rows:
        return "<p style='color:#6b7280;'>No agent activity recorded for this run.</p>"
    head = (
        "<table style='width:100%; border-collapse:collapse; font-size:13px; margin-top:10px;'>"
        "<tr style='text-align:left; color:#4b5563; background:#f8fafc;'>"
        "<th style='padding:8px; border-bottom:2px solid #e5e7eb;'>Agent</th>"
        "<th style='padding:8px; border-bottom:2px solid #e5e7eb;'>Model</th>"
        "<th style='padding:8px; border-bottom:2px solid #e5e7eb; text-align:right;'>Calls</th>"
        "<th style='padding:8px; border-bottom:2px solid #e5e7eb; text-align:right;'>Total Tokens</th>"
        "<th style='padding:8px; border-bottom:2px solid #e5e7eb; text-align:right;'>~USD</th>"
        "<th style='padding:8px; border-bottom:2px solid #e5e7eb;'>Status</th></tr>"
    )
    status_colors = {
        "OK": "#16a34a", "LLM_OK": "#16a34a", "DET_PASS": "#2563eb", "VOTE_ENGINE": "#2563eb",
        "PYTHON_GATE": "#2563eb", "INFRA": "#6b7280", "ON_DEMAND": "#6b7280",
        "NOT_INVOKED": "#dc2626", "ERRORS": "#d97706",
    }
    body = []
    tot_cost = 0.0
    for r in rows:
        status = r.get("status", "NOT_INVOKED")
        color = status_colors.get(status.split()[0], "#6b7280")
        if status.startswith("LLM"):
            color = "#16a34a"
        body.append(
            "<tr>"
            f"<td style='padding:8px; border-bottom:1px solid #f3f4f6;'>{r['role']} <span style='color:#9ca3af;'>({r['agent']})</span></td>"
            f"<td style='padding:8px; border-bottom:1px solid #f3f4f6;'>{r['model']}</td>"
            f"<td style='padding:8px; border-bottom:1px solid #f3f4f6; text-align:right;'>{r['invocations']}</td>"
            f"<td style='padding:8px; border-bottom:1px solid #f3f4f6; text-align:right;'>{r['total_tokens']:,}</td>"
            f"<td style='padding:8px; border-bottom:1px solid #f3f4f6; text-align:right;'>${r['est_cost_usd']:.4f}</td>"
            f"<td style='padding:8px; border-bottom:1px solid #f3f4f6; color:{color}; font-weight:bold;'>{status}</td>"
            "</tr>"
        )
        tot_cost += r["est_cost_usd"]
    foot = (
        f"<tr><td colspan='4' style='padding:8px; text-align:right; font-weight:bold;'>Estimated run cost</td>"
        f"<td style='padding:8px; text-align:right; font-weight:bold;'>${tot_cost:.4f}</td><td></td></tr>"
    )
    return head + "".join(body) + foot + "</table>"


HR_SYSTEM_INSTRUCTION = (
    "You are the HR Efficiency Consultant for a multi-agent AI investment boardroom. "
    "Stan's policy: IMPROVE agent prompts and configuration before CUT or MERGE. Agents stood up "
    "quickly — WATCH and IMPROVE are preferred when STATUS shows DET_PASS, VOTE_ENGINE, PYTHON_GATE, "
    "or INFRA (those often mean Python did the work, not that the role is useless). "
    "Only recommend CUT when an agent has no downstream consumer and no planned product use. "
    "red_teamer (The Crucible) is consumed in the executive briefing (Alpha Pick rebuttal, Unicorn Protocol). "
    "chairman may show VOTE_ENGINE on clear-majority days; Pro chairman is kept for ambiguous runs "
    "and future per-user investment-style selection. data_oracle is INFRA (Python), not LLM headcount. "
    "You are given a DETERMINISTIC UTILIZATION TABLE (invocations, tokens, est. cost, STATUS) as ground truth. "
    "For every roster agent issue a verdict: KEEP, IMPROVE (retain + upgrade prompts/config), WATCH, "
    "MERGE (only with clear duplicate), ADD_BUDGET, or CUT (last resort). "
    "Judge on UTILIZATION, REDUNDANCY, and IMPACT (including investor-facing briefing consumption). "
    "Be specific; cite STATUS and token numbers."
)


async def run_hr_efficiency_review(
    activity: dict,
    raw_log: str = "",
    telemetry: dict | None = None,
) -> dict:
    """Run the HR Efficiency Consultant over the run's activity ledger."""
    rows = build_utilization(activity, telemetry=telemetry)
    util_text = format_utilization_text(rows)
    roster_text = "\n".join(
        f"- {k} | role={v['role']} | model={v['model']} | infra={v.get('infra', False)} | does: {v['summary']}"
        for k, v in roster().items()
    )
    run_ctx = ""
    if telemetry:
        run_ctx = (
            f"\nRUN CONTEXT: chairman_bypassed={telemetry.get('chairman_bypassed')!r}, "
            f"allocation_source={telemetry.get('allocation_source')!r}, "
            f"compliance_source={telemetry.get('compliance_source')!r}, "
            f"QA_EXECUTION={json.dumps(telemetry.get('QA_EXECUTION') or {}, sort_keys=True)}\n"
        )

    prompt = (
        f"{PIPELINE_DATAFLOW_NOTE}\n{run_ctx}\n"
        f"DETERMINISTIC UTILIZATION TABLE (ground truth for this run):\n{util_text}\n\n"
        f"FULL CONFIGURED ROSTER (role, model, what each does):\n{roster_text}\n\n"
        f"RAW DEBATE LOG (optional evidence of impact / who actually contributed):\n{raw_log[:15000]}"
    )
    contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]
    config_params = {
        "system_instruction": HR_SYSTEM_INSTRUCTION,
        "temperature": 0.2,
        "response_mime_type": "application/json",
        "response_schema": HRReport,
    }
    try:
        res = await call_gemini_async(
            HEAVY_MODEL, contents, types.GenerateContentConfig(**config_params),
            agent_name="hr_efficiency_consultant",
        )
        report = json.loads(res.text)
    except Exception as e:
        logger.error(f"HR Efficiency review failed: {e}")
        report = {
            "summary": f"HR Efficiency review failed to execute: {e}",
            "roster_health_score": 0,
            "agent_verdicts": [],
            "redundancies": [],
            "proposed_new_roles": [],
        }
    return {"utilization": rows, "report": report}


def generate_hr_section_html(rows: list[dict], report: dict) -> str:
    """Render the HR section (deterministic table + LLM verdicts) for the digest."""
    verdict_colors = {
        "KEEP": "#16a34a", "IMPROVE": "#7c3aed", "WATCH": "#2563eb", "ADD_BUDGET": "#7c3aed",
        "MERGE": "#d97706", "CUT": "#dc2626",
    }
    html = ["<div style='background:#ffffff; padding:20px; margin-bottom:20px; border-radius:8px; box-shadow:0 2px 4px rgba(0,0,0,0.1); border-left:5px solid #6366f1;'>"]
    score = report.get("roster_health_score", 0)
    html.append(f"<h3 style='margin-top:0; color:#34495e;'>HR Efficiency Consultant <span style='font-weight:normal; color:#6366f1;'>(Roster Health: {score}/5)</span></h3>")
    html.append(f"<p style='color:#2c3e50;'>{report.get('summary', '')}</p>")
    html.append("<strong style='color:#7f8c8d;'>Agent Utilization &amp; Cost:</strong>")
    html.append(render_utilization_html(rows))

    verdicts = report.get("agent_verdicts", [])
    if verdicts:
        html.append("<strong style='color:#7f8c8d; display:block; margin-top:15px;'>Right-Sizing Verdicts:</strong><ul style='margin-top:5px; color:#2c3e50;'>")
        for v in verdicts:
            rec = v.get("recommendation", "WATCH")
            color = verdict_colors.get(rec, "#6b7280")
            html.append(f"<li><strong style='color:{color};'>{rec}</strong> &mdash; <strong>{v.get('agent','')}</strong>: {v.get('rationale','')}</li>")
        html.append("</ul>")

    redundancies = report.get("redundancies", [])
    if redundancies:
        html.append("<strong style='color:#7f8c8d; display:block; margin-top:10px;'>Redundancies / Discarded Outputs:</strong><ul style='margin-top:5px; color:#2c3e50;'>")
        for item in redundancies:
            html.append(f"<li>{item}</li>")
        html.append("</ul>")

    new_roles = report.get("proposed_new_roles", [])
    if new_roles:
        html.append("<strong style='color:#7f8c8d; display:block; margin-top:10px;'>Proposed New Roles:</strong><ul style='margin-top:5px; color:#2c3e50;'>")
        for item in new_roles:
            html.append(f"<li>{item}</li>")
        html.append("</ul>")

    html.append("</div>")
    return "".join(html)


def _standalone(telemetry_path: str) -> int:
    try:
        with open(telemetry_path, "r", encoding="utf-8") as f:
            telemetry = json.load(f)
    except Exception as e:
        print(f"ERROR: could not read telemetry file {telemetry_path}: {e}", file=sys.stderr)
        return 2
    activity = telemetry.get("AGENT_ACTIVITY", {})
    if not activity:
        print("No AGENT_ACTIVITY found in telemetry. Run a pipeline build first (activity logging landed with 5.4).", file=sys.stderr)
        return 3
    rows = build_utilization(activity, telemetry=telemetry)
    print(format_utilization_text(rows))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    if len(sys.argv) < 2:
        print("Usage: python -m src.hr_review <path_to_api_telemetry.json>", file=sys.stderr)
        sys.exit(1)
    sys.exit(_standalone(sys.argv[1]))
