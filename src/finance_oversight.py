"""Finance & Subscription Oversight (subscription/plan-fit governance).

Distinct from HR Efficiency (5.4) which optimizes agent/token utilization *within*
a run, and from qa_review's finance_cost which nudges per-run duration — this
consultant answers: "Are we on the right plan, right tool, and spending wisely
across the whole ecosystem?"

Reads the living registry at docs/subscriptions_registry.json (+ narrative in
docs/tech_stack_and_subscriptions.md), optionally enriches with latest telemetry
(AGENT_ACTIVITY, run duration, FMP call patterns), and produces a structured
oversight report (HTML + JSON).

Future: pull live Azure Cost Management + Google API billing; hooks documented
in the registry's future_automation list.

Standalone:
  .venv\\Scripts\\python.exe -m src.finance_oversight
  .venv\\Scripts\\python.exe -m src.finance_oversight --telemetry .cache/state/api_telemetry_*.json
  .venv\\Scripts\\python.exe -m src.finance_oversight --email
"""
import os
import sys
import json
import asyncio
import logging
import argparse
from typing import Literal, Optional

from pydantic import BaseModel, Field
from google.genai import types

from src.core.agents import call_gemini_async, HEAVY_MODEL
from src.config.settings import settings, now_local
from src import hr_review

logger = logging.getLogger(__name__)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY_PATH = os.path.join(REPO_ROOT, "docs", "subscriptions_registry.json")
STACK_DOC_PATH = os.path.join(REPO_ROOT, "docs", "tech_stack_and_subscriptions.md")
OUTPUT_DIR = os.path.join(REPO_ROOT, "docs", "finance_oversight")


class ServiceVerdict(BaseModel):
    service_id: str = Field(description="Registry id, e.g. google_ai_ultra, fmp, azure_platform.")
    recommendation: Literal["RIGHT_PLAN", "UPGRADE", "DOWNGRADE", "CUT", "WATCH", "FILL_IN_DATA"] = Field(
        description="Plan-fit verdict for this subscription."
    )
    rationale: str = Field(description="1-2 sentences citing cost, usage, or architecture fit.")


class FinanceOversightReport(BaseModel):
    summary: str = Field(description="Executive summary of subscription health and biggest savings or quality win.")
    tco_health_score: int = Field(description="1 (wasteful/misaligned) to 5 (lean and well-matched plans).")
    known_monthly_usd: Optional[float] = Field(description="Sum of confirmed monthly costs in registry.")
    estimated_monthly_usd: Optional[float] = Field(description="Best estimate including unknowns, clearly labeled.")
    service_verdicts: list[ServiceVerdict] = Field(description="Verdict for every registry entry.")
    alternatives: list[str] = Field(default_factory=list, description="Cheaper or higher-quality options with tradeoffs.")
    billing_gaps: list[str] = Field(default_factory=list, description="Missing or unvalidated billing data.")
    questions_for_stan: list[str] = Field(default_factory=list, description="Direct questions Stan must answer to complete the TCO picture.")
    possible_hidden_costs: list[str] = Field(default_factory=list, description="Services Stan may be paying for based on tech stack but not yet in registry.")
    validation_actions: list[str] = Field(default_factory=list, description="Concrete steps to validate invoices (where to look, what to confirm).")
    automation_next_steps: list[str] = Field(default_factory=list, description="Concrete steps to pull live billing automatically.")


FINANCE_OVERSIGHT_INSTRUCTION = (
    "You are the Finance & Subscription Oversight Consultant for Invest AI Boardroom. "
    "Your job is subscription and plan-fit governance AND billing completeness — finding missing invoices, "
    "validating assumptions, and asking Stan directly for anything unknown. "
    "You are NOT optimizing per-agent tokens (HR Efficiency) or per-run duration (qa_review finance_cost). "
    "You receive: SUBSCRIPTIONS REGISTRY, a DETERMINISTIC VALIDATION AUDIT (missing data, unvalidated assumptions, "
    "possible hidden costs from the tech stack), and optional RUN TELEMETRY. "
    "For EVERY service in the registry, issue a verdict: RIGHT_PLAN, UPGRADE, DOWNGRADE, CUT, WATCH, or FILL_IN_DATA. "
    "Judge on: (1) PLAN FIT for ~22 weekday runs/month; (2) TOOL FIT vs alternatives; "
    "(3) VALUE — using what we pay for; (4) WASTE — unused keys, duplicate billing. "
    "CRITICAL: Stan believes Gemini API is bundled in Google AI Ultra ($199.99) — treat as UNVALIDATED until invoices confirm. "
    "Do NOT double-count Gemini API in TCO if bundled_in=google_ai_ultra. "
    "You MUST populate questions_for_stan with specific asks for every registry gap and unvalidated assumption. "
    "You MUST populate possible_hidden_costs from the audit list PLUS any others you infer from code_refs/env_keys. "
    "You MUST populate validation_actions telling Stan exactly where to check (Google Subscriptions, Azure Cost Management, etc.). "
    "Be blunt. Cite dollar amounts. Flag when Stan said 'I might be missing bills' — your job is to hunt those down."
)


def load_registry() -> dict:
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_stack_doc_excerpt(max_chars: int = 8000) -> str:
    try:
        with open(STACK_DOC_PATH, "r", encoding="utf-8") as f:
            return f.read()[:max_chars]
    except Exception:
        return ""


def compute_known_monthly(registry: dict) -> tuple[float, list[str]]:
    """Sum confirmed monthly costs; skip bundled children (tcoe_include=false)."""
    total = 0.0
    lines = []
    for svc in registry.get("services", []):
        if svc.get("tcoe_include") is False:
            bundled = svc.get("bundled_in", "")
            lines.append(f"  {svc['name']}: $0 (bundled in {bundled})")
            continue
        conf = svc.get("cost_confidence", "")
        monthly = svc.get("cost_usd")
        if monthly is None and svc.get("cost_annual_usd"):
            monthly = svc["cost_annual_usd"] / 12.0
        if monthly is None:
            if conf in ("unknown",) or svc.get("validation_status") == "unvalidated":
                lines.append(f"  {svc['name']}: MISSING — need Stan input")
            continue
        if conf not in ("confirmed", "confirmed_portal", "assumed", "assumed_bundled"):
            continue
        total += float(monthly)
        tag = f" ({conf})"
        if svc.get("validation_status", "").startswith("confirmed_price"):
            tag += " [price ok, bundle unvalidated]"
        lines.append(f"  {svc['name']}: ${monthly:.2f}/mo{tag}")
    return round(total, 2), lines


def build_validation_audit(registry: dict) -> dict:
    """Deterministic pre-LLM audit: gaps, unvalidated assumptions, hidden-cost hunt list."""
    missing = []
    unvalidated = []
    for svc in registry.get("services", []):
        sid = svc.get("id", svc.get("name"))
        if svc.get("cost_usd") is None and svc.get("cost_annual_usd") is None and svc.get("tcoe_include") is not False:
            missing.append(f"{svc['name']} ({sid}): no monthly cost in registry")
        vs = svc.get("validation_status", "")
        if vs in ("unvalidated", "confirmed_price_unvalidated_bundle"):
            unvalidated.append(
                f"{svc['name']}: {svc.get('notes', vs)}"
            )
        if svc.get("cost_confidence") == "assumed":
            unvalidated.append(f"{svc['name']}: cost/plan marked 'assumed' — confirm with invoice")
    hidden = registry.get("possible_hidden_costs", [])
    hidden_lines = [
        f"{h['name']}: {h['why']} → Check: {h['where_to_check']}"
        for h in hidden
    ]
    billing_notes = registry.get("billing_notes", {})
    note_lines = [f"{k}: {v}" for k, v in billing_notes.items()]
    return {
        "missing_cost_data": missing,
        "unvalidated_assumptions": unvalidated,
        "possible_hidden_costs": hidden_lines,
        "billing_notes": note_lines,
    }


def format_validation_audit(audit: dict) -> str:
    parts = []
    if audit.get("billing_notes"):
        parts.append("BILLING NOTES:\n" + "\n".join(f"  - {n}" for n in audit["billing_notes"]))
    if audit.get("missing_cost_data"):
        parts.append("MISSING COST DATA (ask Stan):\n" + "\n".join(f"  - {m}" for m in audit["missing_cost_data"]))
    if audit.get("unvalidated_assumptions"):
        parts.append("UNVALIDATED ASSUMPTIONS (must verify):\n" + "\n".join(f"  - {u}" for u in audit["unvalidated_assumptions"]))
    if audit.get("possible_hidden_costs"):
        parts.append("POSSIBLE HIDDEN COSTS (from tech stack — hunt on invoices):\n" + "\n".join(f"  - {p}" for p in audit["possible_hidden_costs"]))
    return "\n\n".join(parts) if parts else "Registry appears complete (still verify invoices)."


def build_telemetry_context(telemetry: dict) -> str:
    if not telemetry:
        return "No telemetry provided."
    parts = []
    activity = telemetry.get("AGENT_ACTIVITY", {})
    if activity:
        rows = hr_review.build_utilization(activity, telemetry=telemetry)
        parts.append("AGENT_ACTIVITY (per-run Gemini usage estimate):\n" + hr_review.format_utilization_text(rows))
    duration = None
    for key in ("run_duration_seconds", "duration_seconds"):
        if key in telemetry:
            duration = telemetry[key]
            break
    if duration is None and isinstance(telemetry.get("MACRO_TLT_VXX"), dict):
        pass  # telemetry file is api_telemetry blob, not run_status
    macro = telemetry.get("MACRO_TLT_VXX")
    if macro:
        parts.append(f"Sample telemetry keys present: MACRO, FUNDAMENTAL_NEWS, etc. (full blob ~{len(json.dumps(telemetry)):,} chars)")
    return "\n\n".join(parts) if parts else "Telemetry provided but no AGENT_ACTIVITY ledger (run predates 5.4 logging)."


def render_report_html(report: dict, registry: dict, known_total: float, known_lines: list[str], audit: dict = None) -> str:
    verdict_colors = {
        "RIGHT_PLAN": "#16a34a", "UPGRADE": "#7c3aed", "WATCH": "#2563eb",
        "DOWNGRADE": "#d97706", "CUT": "#dc2626", "FILL_IN_DATA": "#6b7280",
    }
    ts = now_local().strftime("%Y-%m-%d %H:%M %Z")
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body {{ font-family: 'Segoe UI', sans-serif; background: #f3f4f6; color: #1f2937; padding: 20px; }}
  .container {{ max-width: 900px; margin: 0 auto; background: #fff; padding: 30px; border-radius: 8px; box-shadow: 0 2px 6px rgba(0,0,0,0.06); }}
  h1 {{ border-bottom: 2px solid #e5e7eb; padding-bottom: 10px; }}
  h2 {{ color: #2563eb; margin-top: 28px; font-size: 1.1em; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; margin-top: 10px; }}
  th, td {{ padding: 10px; border-bottom: 1px solid #f3f4f6; text-align: left; vertical-align: top; }}
  th {{ background: #f8fafc; color: #4b5563; }}
  .score {{ color: #6366f1; font-weight: normal; }}
  .summary {{ background: #f8fafc; padding: 15px; border-left: 4px solid #6366f1; border-radius: 4px; margin: 15px 0; }}
  ul {{ margin: 8px 0; padding-left: 20px; }}
  .ask-box {{ background: #fffbeb; padding: 15px; border-left: 4px solid #d97706; border-radius: 4px; margin: 15px 0; }}
  .hunt-box {{ background: #fef2f2; padding: 15px; border-left: 4px solid #dc2626; border-radius: 4px; margin: 15px 0; }}
</style></head><body><div class="container">
<h1>Finance &amp; Subscription Oversight</h1>
<p style="color:#6b7280;">Generated {ts} &mdash; registry {registry.get('last_updated', 'unknown')}</p>
<div class="summary"><strong>Summary:</strong> {report.get('summary', '')}</div>
<p><strong>TCO health:</strong> <span class="score">{report.get('tco_health_score', 'N/A')}/5</span>
 &nbsp;|&nbsp; <strong>Known monthly (registry):</strong> ${known_total:.2f}
 &nbsp;|&nbsp; <strong>Agent estimate:</strong> ${report.get('estimated_monthly_usd') or 'N/A'}</p>
<h2>Confirmed line items (registry math)</h2><ul>"""
    for line in known_lines:
        html += f"<li>{line.strip()}</li>"
    html += "</ul>"

    if audit and (audit.get("unvalidated_assumptions") or audit.get("missing_cost_data")):
        html += "<h2>Validation status (deterministic)</h2><div class='ask-box'><ul>"
        for u in audit.get("unvalidated_assumptions", []):
            html += f"<li><strong>Unvalidated:</strong> {u}</li>"
        for m in audit.get("missing_cost_data", []):
            html += f"<li><strong>Missing:</strong> {m}</li>"
        html += "</ul></div>"

    qs = report.get("questions_for_stan") or []
    if qs:
        html += "<h2>Questions for Stan</h2><div class='ask-box'><ul>"
        for q in qs:
            html += f"<li>{q}</li>"
        html += "</ul></div>"

    hidden = report.get("possible_hidden_costs") or audit.get("possible_hidden_costs") if audit else []
    if hidden:
        html += "<h2>Possible hidden costs (check your invoices)</h2><div class='hunt-box'><ul>"
        for h in hidden:
            html += f"<li>{h}</li>"
        html += "</ul></div>"

    if report.get("validation_actions"):
        html += "<h2>Where to validate</h2><ul>"
        for v in report["validation_actions"]:
            html += f"<li>{v}</li>"
        html += "</ul>"

    html += "<h2>Plan-fit verdicts</h2><table><tr><th>Service</th><th>Verdict</th><th>Rationale</th></tr>"
    id_to_name = {s["id"]: s["name"] for s in registry.get("services", [])}
    for v in report.get("service_verdicts", []):
        rec = v.get("recommendation", "WATCH")
        color = verdict_colors.get(rec, "#6b7280")
        name = id_to_name.get(v.get("service_id", ""), v.get("service_id", ""))
        html += f"<tr><td>{name}</td><td style='color:{color};font-weight:bold;'>{rec}</td><td>{v.get('rationale','')}</td></tr>"
    html += "</table>"
    if report.get("alternatives"):
        html += "<h2>Alternatives</h2><ul>"
        for a in report["alternatives"]:
            html += f"<li>{a}</li>"
        html += "</ul>"
    if report.get("billing_gaps"):
        html += "<h2>Billing gaps &amp; open questions</h2><ul>"
        for g in report["billing_gaps"]:
            html += f"<li>{g}</li>"
        html += "</ul>"
    if report.get("automation_next_steps"):
        html += "<h2>Automation next steps</h2><ul>"
        for s in report["automation_next_steps"]:
            html += f"<li>{s}</li>"
        html += "</ul>"
    html += f"""<div class="footer">Source: docs/subscriptions_registry.json &bull; Re-run: python -m src.finance_oversight</div>
</div></body></html>"""
    return html


async def run_finance_oversight(telemetry: dict = None) -> dict:
    registry = load_registry()
    known_total, known_lines = compute_known_monthly(registry)
    audit = build_validation_audit(registry)
    audit_text = format_validation_audit(audit)
    stack_excerpt = load_stack_doc_excerpt()
    telemetry_ctx = build_telemetry_context(telemetry or {})

    prompt = (
        f"SUBSCRIPTIONS REGISTRY (JSON — source of truth):\n{json.dumps(registry, indent=2)}\n\n"
        f"DETERMINISTIC VALIDATION AUDIT (ground truth — expand on this, do not ignore):\n{audit_text}\n\n"
        f"TECH STACK NARRATIVE (excerpt):\n{stack_excerpt}\n\n"
        f"RUN TELEMETRY (optional usage context):\n{telemetry_ctx}\n\n"
        f"REGISTRY MATH — known confirmed monthly sum (excl. bundled children): ${known_total:.2f}\n"
        f"Line items:\n" + "\n".join(known_lines) + "\n\n"
        "Stan says Gemini API is likely included in Ultra but may be wrong and may be missing other bills. "
        "Produce FinanceOversightReport with questions_for_stan, possible_hidden_costs, and validation_actions filled in."
    )
    contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]
    config = types.GenerateContentConfig(
        system_instruction=FINANCE_OVERSIGHT_INSTRUCTION,
        temperature=0.2,
        response_mime_type="application/json",
        response_schema=FinanceOversightReport,
    )
    try:
        res = await call_gemini_async(
            HEAVY_MODEL, contents, config, agent_name="finance_oversight"
        )
        report = json.loads(res.text)
    except Exception as e:
        logger.error(f"Finance oversight LLM failed: {e}")
        report = {
            "summary": f"Oversight review failed: {e}",
            "tco_health_score": 0,
            "known_monthly_usd": known_total,
            "estimated_monthly_usd": None,
            "service_verdicts": [],
            "alternatives": [],
            "billing_gaps": audit.get("missing_cost_data", []) + audit.get("unvalidated_assumptions", []),
            "questions_for_stan": ["LLM review failed — re-run after checking GEMINI_API_KEY."],
            "possible_hidden_costs": audit.get("possible_hidden_costs", []),
            "validation_actions": [],
            "automation_next_steps": registry.get("future_automation", []),
        }
    return {
        "registry": registry,
        "known_monthly_usd": known_total,
        "known_lines": known_lines,
        "validation_audit": audit,
        "report": report,
    }


def save_outputs(result: dict) -> tuple[str, str]:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ts = now_local().strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(OUTPUT_DIR, f"oversight_{ts}.json")
    html_path = os.path.join(OUTPUT_DIR, f"oversight_{ts}.html")
    payload = {
        "generated_at": now_local().isoformat(),
        "known_monthly_usd": result["known_monthly_usd"],
        "validation_audit": result.get("validation_audit"),
        "report": result["report"],
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    html = render_report_html(
        result["report"], result["registry"],
        result["known_monthly_usd"], result["known_lines"],
        audit=result.get("validation_audit"),
    )
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    return json_path, html_path


async def main_async(args) -> int:
    if not settings.validate():
        logger.error("Missing required env vars (need GEMINI_API_KEY at minimum).")
        return 2

    telemetry = None
    if args.telemetry:
        path = args.telemetry
        if not os.path.isfile(path):
            logger.error(f"Telemetry file not found: {path}")
            return 3
        with open(path, "r", encoding="utf-8") as f:
            telemetry = json.load(f)
    elif args.fetch_latest:
        try:
            from src.storage_client import get_blob_service_client, STATE_CONTAINER
            client = get_blob_service_client()
            if client:
                cc = client.get_container_client(STATE_CONTAINER)
                blobs = sorted(
                    [b.name for b in cc.list_blobs() if b.name.startswith("api_telemetry_")],
                    reverse=True,
                )
                if blobs:
                    telemetry = json.loads(cc.download_blob(blobs[0]).readall())
                    logger.info(f"Loaded telemetry: {blobs[0]}")
            else:
                logger.warning("No Azure client; continuing without telemetry.")
        except Exception as e:
            logger.warning(f"Could not fetch telemetry from Azure: {e}")

    result = await run_finance_oversight(telemetry)
    json_path, html_path = save_outputs(result)
    print(f"Known monthly (registry): ${result['known_monthly_usd']:.2f}")
    print(f"TCO health: {result['report'].get('tco_health_score', 'N/A')}/5")
    print(f"JSON: {json_path}")
    print(f"HTML: {html_path}")

    if args.email:
        from src.output.notifier import send_finance_oversight
        with open(html_path, "r", encoding="utf-8") as f:
            send_finance_oversight(f.read())

    return 0


def main():
    parser = argparse.ArgumentParser(description="Finance & Subscription Oversight")
    parser.add_argument("--telemetry", help="Path to api_telemetry_*.json")
    parser.add_argument("--fetch-latest", action="store_true", help="Pull latest telemetry from Azure first")
    parser.add_argument("--email", action="store_true", help="Email the HTML report")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
