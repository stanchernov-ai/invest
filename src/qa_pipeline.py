"""Shared QA + board-matrix helpers used by the deliver phase (and importable by
the standing qa_review team). Extracted from main.py so the split jobs can reuse
the exact same QA logic.

Cost/latency notes (see engineering_playbook 4b):
- Graphics QA is now DETERMINISTIC (no LLM) — built straight from the chart
  health probe. The LLM graphics reviewer was the first non-crucial QA we cut.
- The QA Integrity auditor runs on a configurable model with a hard timeout so
  it can never again blow the per-function 10-minute ceiling.
"""
import json
import logging
import asyncio

from google.genai import types

from src.core.schemas import QAAgentReport
from src.core.agents import call_gemini_async, agent_config, FAST_MODEL, FLASH_TOKEN_LIMIT

logger = logging.getLogger(__name__)

# Hard ceiling for the QA-of-the-QA call. On timeout we emit a non-blocking
# WARNING report rather than killing the run or false-failing the QA.
QA_INTEGRITY_TIMEOUT_SECONDS = 90


def reconcile_compliance(report: dict) -> dict:
    """A QA agent cannot self-report PASS while logging a CRITICAL finding. The
    PASS/FAIL badge is derived from evidence (findings), not the model's free-form
    boolean, so a contradictory report can't slip through as a green check."""
    try:
        has_critical = any(
            str(f.get("severity", "")).upper() == "CRITICAL"
            for f in report.get("findings", []) or []
        )
        if has_critical and report.get("is_compliant"):
            logger.warning(
                f"Forcing is_compliant False for '{report.get('agent_role')}': "
                f"agent self-reported PASS but logged CRITICAL finding(s)."
            )
            report["is_compliant"] = False
    except Exception as e:
        logger.warning(f"Could not reconcile compliance for a QA report: {e}")
    return report


def parse_board_matrix(raw_messages, all_tickers):
    matrix = {ticker: {"buffett": "", "lynch": "", "livermore": "", "huang": "", "simons": ""} for ticker in all_tickers}
    for msg in raw_messages:
        content = msg.get("content", "")
        agent = None
        if "**Warren Buffett**" in content: agent = "buffett"
        elif "**Peter Lynch**" in content: agent = "lynch"
        elif "**Jesse Livermore**" in content: agent = "livermore"
        elif "**Jensen Huang**" in content: agent = "huang"
        elif "**Jim Simons**" in content: agent = "simons"
        if not agent: continue
        for line in content.split("\n"):
            if line.startswith("* **"):
                parts = line.split("**: ")
                if len(parts) > 1:
                    ticker = parts[0].replace("* **", "").strip()
                    verdict_full = parts[1].split(" ")[0].replace("*", "")
                    if "Strong" in parts[1]: verdict_full = "Strong Buy"
                    if ticker in matrix: matrix[ticker][agent] = verdict_full
    return matrix


def generate_matrix_markdown(matrix):
    md = "| Ticker | Buffett | Lynch | Livermore | Huang | Simons |\n|---|---|---|---|---|---|\n"
    for ticker, votes in matrix.items():
        if any(v != "" for v in votes.values()):
            md += f"| **{ticker}** | {votes['buffett']} | {votes['lynch']} | {votes['livermore']} | {votes['huang']} | {votes['simons']} |\n"
    return md


def _execution_error_report(role: str, exc: Exception) -> dict:
    return {
        "agent_role": role,
        "is_compliant": False,
        "findings": [{
            "severity": "CRITICAL",
            "category": "Execution Error",
            "description": f"Agent failed to execute: {str(exc)}",
            "recommendation": "Check API logs and retry.",
        }],
        "summary": "Agent execution encountered a fatal error.",
    }


async def run_post_flight_qa(raw_log: str, chairman_json: str):
    logger.info("Initiating Post Flight QA Audit.")
    qa_prompt = f"RAW DEBATE LOG:\n{raw_log}\n\nFINAL CHAIRMAN ALLOCATION:\n{chairman_json}"
    contents = [types.Content(role="user", parts=[types.Part.from_text(text=qa_prompt)])]

    tasks = []
    agent_keys = ["post_mortem_qa", "system_architect", "prompt_engineer"]
    for key in agent_keys:
        info = agent_config["board_members"][key]
        config_params = {
            "system_instruction": info["system_instruction"],
            "temperature": 0.15,
            "response_mime_type": "application/json",
            "response_schema": QAAgentReport,
        }
        if info["model"] == FAST_MODEL:
            config_params["max_output_tokens"] = FLASH_TOKEN_LIMIT
        tasks.append(call_gemini_async(info["model"], contents, types.GenerateContentConfig(**config_params), agent_name=key))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    qa_reports = []
    for key, res in zip(agent_keys, results):
        role_name = agent_config["board_members"][key]["role"]
        if isinstance(res, Exception):
            logger.error(f"QA execution failed for {role_name}: {res}")
            qa_reports.append(_execution_error_report(role_name, res))
        else:
            try:
                parsed_res = json.loads(res.text)
                parsed_res["agent_role"] = role_name
                qa_reports.append(reconcile_compliance(parsed_res))
            except Exception as e:
                logger.error(f"Failed to parse QA report for {role_name}: {e}")
                qa_reports.append({
                    "agent_role": role_name,
                    "is_compliant": False,
                    "findings": [{
                        "severity": "CRITICAL",
                        "category": "Parsing Error",
                        "description": "Agent returned malformed JSON.",
                        "recommendation": "Review raw agent output for syntax errors.",
                    }],
                    "summary": "Failed to parse agent JSON output.",
                })

    return qa_reports


def build_graphics_report(chart_health: list[dict]) -> dict:
    """Deterministic Graphics QA — no LLM. The reviewer could never actually see
    rendered images, so its only reliable signal was the chart-health HTTP probe.
    We now turn that probe directly into the report and skip the model call."""
    findings = []
    broken = [h for h in (chart_health or []) if not h.get("ok")]
    for h in broken:
        findings.append({
            "severity": "CRITICAL",
            "category": "Broken Chart",
            "description": f"Chart '{h.get('name', 'unknown')}' failed its health check "
                           f"(status={h.get('status', 'n/a')}, url={'present' if h.get('url') else 'MISSING'}).",
            "recommendation": "Rebuild the chart URL (POST short-URL + downsample long series) before sending.",
        })

    ok_count = len([h for h in (chart_health or []) if h.get("ok")])
    total = len(chart_health or [])
    summary = (
        f"Deterministic chart-health audit: {ok_count}/{total} charts rendered OK."
        + (f" {len(broken)} broken." if broken else " No broken charts detected.")
    )
    return {
        "agent_role": "Graphics Designer Visual SME (deterministic)",
        "is_compliant": len(broken) == 0,
        "findings": findings,
        "summary": summary,
    }


async def run_qa_integrity_audit(qa_reports, raw_log: str, chairman_json: str,
                                 qa_dashboard_html: str, *,
                                 model_override: str = None,
                                 timeout_seconds: int = QA_INTEGRITY_TIMEOUT_SECONDS):
    """The QA-of-the-QA: validate that the QA team's verdicts are supported by the
    actual run evidence and that the rendered dashboard faithfully reflects them.

    Runs on `model_override` (default FAST_MODEL) with a hard timeout so it can
    never again exceed the per-function ceiling."""
    logger.info("Initiating QA Integrity Audit (QA-of-the-QA).")

    reports_digest = json.dumps([
        {
            "agent_role": r.get("agent_role"),
            "is_compliant": r.get("is_compliant"),
            "summary": r.get("summary"),
            "findings": r.get("findings", []),
        }
        for r in qa_reports
    ], default=str)

    qa_prompt = (
        f"RAW DEBATE LOG (ground truth of what actually happened):\n{raw_log[:25000]}\n\n"
        f"FINAL CHAIRMAN ALLOCATION:\n{chairman_json[:8000]}\n\n"
        f"QA AGENT REPORTS (the conclusions you must independently verify):\n{reports_digest[:15000]}\n\n"
        f"RENDERED QA DASHBOARD HTML (what the human will actually see):\n{qa_dashboard_html[:10000]}"
    )
    contents = [types.Content(role="user", parts=[types.Part.from_text(text=qa_prompt)])]

    info = agent_config["board_members"]["qa_integrity_auditor"]
    model = model_override or FAST_MODEL
    config_params = {
        "system_instruction": info["system_instruction"],
        "temperature": 0.15,
        "response_mime_type": "application/json",
        "response_schema": QAAgentReport,
    }
    if model == FAST_MODEL:
        config_params["max_output_tokens"] = FLASH_TOKEN_LIMIT

    try:
        res = await asyncio.wait_for(
            call_gemini_async(model, contents, types.GenerateContentConfig(**config_params), agent_name="qa_integrity_auditor"),
            timeout=timeout_seconds,
        )
        parsed_res = json.loads(res.text)
        parsed_res["agent_role"] = info["role"]
        return reconcile_compliance(parsed_res)
    except asyncio.TimeoutError:
        logger.warning(f"QA Integrity Audit timed out after {timeout_seconds}s; emitting non-blocking WARNING.")
        return {
            "agent_role": info["role"],
            "is_compliant": True,
            "findings": [{
                "severity": "WARNING",
                "category": "QA Timeout",
                "description": f"Integrity audit did not finish within {timeout_seconds}s and was skipped.",
                "recommendation": "Review the standing QA digest, or lower integrity prompt size / model.",
            }],
            "summary": "QA integrity audit skipped (timeout). Not treated as a violation.",
        }
    except Exception as e:
        logger.error(f"Failed to execute or parse QA Integrity Audit: {e}")
        return _execution_error_report(info["role"], e)
