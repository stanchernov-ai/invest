"""Shared QA + board-matrix helpers used by the deliver phase (and importable by
the standing qa_review team). Extracted from main.py so the split jobs can reuse
the exact same QA logic.

Cost/latency notes (see engineering_playbook 4b):
- Graphics QA: deterministic chart-health gate + multimodal review of the FINAL
  saved/emailed briefing HTML and its embedded images (not templates/code).
- The QA Integrity auditor runs on a configurable model with a hard timeout so
  it can never again blow the per-function 10-minute ceiling.
"""
import json
import logging
import asyncio

from google.genai import types

from src.core.schemas import QAAgentReport
from src.core.agents import call_gemini_async, agent_config, FAST_MODEL, HEAVY_MODEL, FLASH_TOKEN_LIMIT

logger = logging.getLogger(__name__)

# Hard ceiling for the QA-of-the-QA call. On timeout we emit a non-blocking
# WARNING report rather than killing the run or false-failing the QA.
QA_INTEGRITY_TIMEOUT_SECONDS = 90
GRAPHICS_QA_TIMEOUT_SECONDS = 120
# Cap HTML passed to the Graphics Designer — the artifact is the saved blob, not templates.
GRAPHICS_BRIEFING_HTML_CHAR_LIMIT = 45000
INTEGRITY_BRIEFING_HTML_CHAR_LIMIT = 8000
# Dashboard excerpt for LLM context only — section/finding presence is deterministic ground truth.
INTEGRITY_DASHBOARD_HTML_CHAR_LIMIT = 12000


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


def build_board_matrix(
    raw_board_messages: list[dict],
    all_tickers: list[str],
    raw_verdicts: dict | None = None,
) -> dict:
    """Prefer Round 2 structured JSON; fall back to markdown parse."""
    if raw_verdicts:
        from src.core.vote_engine import build_matrix_from_raw_verdicts
        return build_matrix_from_raw_verdicts(raw_verdicts, all_tickers)
    return parse_board_matrix(raw_board_messages, all_tickers)


def parse_board_matrix(raw_messages, all_tickers):
    """Parse Round 2 per-panelist blocks only (not cumulative R1+R2 history)."""
    from src.core.rebuttal import extract_panelist_round2_block, parse_ticker_verdict_from_line
    from src.core.vote_engine import AGENT_KEYS

    matrix = {ticker: {k: "" for k in AGENT_KEYS} for ticker in all_tickers}
    for msg in raw_messages or []:
        for agent_key in AGENT_KEYS:
            block = extract_panelist_round2_block([msg], agent_key)
            if not block:
                continue
            for line in block.split("\n"):
                parsed = parse_ticker_verdict_from_line(line)
                if not parsed:
                    continue
                ticker, verdict = parsed
                if ticker in matrix:
                    matrix[ticker][agent_key] = verdict
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


async def run_post_flight_qa(
    raw_log: str,
    chairman_json: str,
    *,
    raw_board_messages: list[dict] | None = None,
    all_symbols: list[str] | None = None,
    raw_verdicts: dict | None = None,
    portfolio_symbols: set[str] | None = None,
):
    logger.info("Initiating Post Flight QA Audit.")

    post_mortem_task = run_post_mortem_qa(
        raw_log,
        chairman_json,
        raw_verdicts=raw_verdicts,
        all_symbols=all_symbols or [],
        portfolio_symbols=portfolio_symbols,
        raw_board_messages=raw_board_messages,
    )
    architect_task = run_system_architect_qa(
        raw_log,
        chairman_json,
        raw_verdicts=raw_verdicts,
        all_symbols=all_symbols or [],
    )
    persona_task = run_prompt_engineer_qa(
        raw_log,
        chairman_json,
        raw_board_messages or [],
        all_symbols or [],
    )
    results = await asyncio.gather(
        post_mortem_task,
        architect_task,
        persona_task,
        return_exceptions=True,
    )

    role_names = [
        agent_config["board_members"]["post_mortem_qa"]["role"],
        agent_config["board_members"]["system_architect"]["role"],
        agent_config["board_members"]["prompt_engineer"]["role"],
    ]
    qa_reports = []
    for role_name, res in zip(role_names, results):
        if isinstance(res, Exception):
            qa_reports.append(_execution_error_report(role_name, res))
        else:
            qa_reports.append(res)
    return qa_reports


async def run_system_architect_qa(
    raw_log: str,
    chairman_json: str,
    *,
    raw_verdicts: dict | None = None,
    all_symbols: list[str] | None = None,
) -> dict:
    """Structural / bloat audit: deterministic Python gate; LLM skipped on PASS."""
    from src.qa.architect_audit import (
        audit_system_architect_deterministic,
        merge_architect_reports,
    )

    role_name = agent_config["board_members"]["system_architect"]["role"]
    try:
        chairman = json.loads(chairman_json) if chairman_json else {}
    except json.JSONDecodeError:
        chairman = {}

    violations = audit_system_architect_deterministic(
        chairman,
        raw_log,
        raw_verdicts,
        all_symbols=all_symbols or [],
    )
    if not violations:
        merged = merge_architect_reports([], None)
        merged["agent_role"] = role_name
        logger.info("Systems Architect deterministic PASS — skipping LLM audit.")
        return reconcile_compliance(merged)

    merged = merge_architect_reports(violations, None)
    merged["agent_role"] = role_name
    logger.info("Systems Architect deterministic FAIL — skipping LLM audit.")
    return reconcile_compliance(merged)


async def run_post_mortem_qa(
    raw_log: str,
    chairman_json: str,
    *,
    raw_verdicts: dict | None = None,
    all_symbols: list[str] | None = None,
    portfolio_symbols: set[str] | None = None,
    raw_board_messages: list[dict] | None = None,
) -> dict:
    """Post Mortem audit: deterministic vote alignment + procedural LLM pass."""
    from src.qa.post_mortem_audit import (
        audit_post_mortem_deterministic,
        format_post_mortem_digest,
        merge_post_mortem_reports,
    )

    role_name = agent_config["board_members"]["post_mortem_qa"]["role"]
    try:
        chairman = json.loads(chairman_json) if chairman_json else {}
    except json.JSONDecodeError:
        chairman = {}

    violations = audit_post_mortem_deterministic(
        chairman,
        raw_verdicts,
        all_symbols=all_symbols or [],
        portfolio_symbols=portfolio_symbols,
        raw_board_messages=raw_board_messages,
    )
    if not violations:
        merged = merge_post_mortem_reports([], None)
        merged["agent_role"] = role_name
        logger.info("Post Mortem deterministic PASS — skipping LLM audit.")
        return reconcile_compliance(merged)

    digest = format_post_mortem_digest(
        violations,
        raw_verdicts,
        all_symbols=all_symbols or [],
        portfolio_symbols=portfolio_symbols,
    )
    prompt_text = (
        f"{digest}\n\nRAW DEBATE LOG:\n{raw_log}\n\nFINAL CHAIRMAN ALLOCATION:\n{chairman_json}"
    )
    contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt_text)])]
    info = agent_config["board_members"]["post_mortem_qa"]
    config_params = {
        "system_instruction": info["system_instruction"],
        "temperature": 0.15,
        "response_mime_type": "application/json",
        "response_schema": QAAgentReport,
    }

    try:
        res = await call_gemini_async(
            info["model"],
            contents,
            types.GenerateContentConfig(**config_params),
            agent_name="post_mortem_qa",
        )
        parsed = json.loads(res.text)
        parsed["agent_role"] = role_name
        merged = merge_post_mortem_reports(violations, parsed)
        return reconcile_compliance(merged)
    except Exception as exc:
        logger.error(f"QA execution failed for {role_name}: {exc}")
        if violations:
            merged = merge_post_mortem_reports(violations, None)
            merged["agent_role"] = role_name
            return reconcile_compliance(merged)
        return _execution_error_report(role_name, exc)


def _parse_qa_result(role_name: str, res) -> dict:
    if isinstance(res, Exception):
        logger.error(f"QA execution failed for {role_name}: {res}")
        return _execution_error_report(role_name, res)
    try:
        parsed_res = json.loads(res.text)
        parsed_res["agent_role"] = role_name
        return reconcile_compliance(parsed_res)
    except Exception as e:
        logger.error(f"Failed to parse QA report for {role_name}: {e}")
        return {
            "agent_role": role_name,
            "is_compliant": False,
            "findings": [{
                "severity": "CRITICAL",
                "category": "Parsing Error",
                "description": "Agent returned malformed JSON.",
                "recommendation": "Review raw agent output for syntax errors.",
            }],
            "summary": "Failed to parse agent JSON output.",
        }


async def run_prompt_engineer_qa(
    raw_log: str,
    chairman_json: str,
    raw_board_messages: list[dict],
    all_symbols: list[str],
) -> dict:
    """Persona audit: deterministic pre-check (LLM skipped — Python is authoritative)."""
    from src.qa.persona_audit import audit_debate_persona, merge_persona_reports

    role_name = agent_config["board_members"]["prompt_engineer"]["role"]
    violations, _stats = audit_debate_persona(raw_board_messages, all_symbols)
    merged = merge_persona_reports(violations, None)
    merged["agent_role"] = role_name
    if violations:
        logger.info("Persona deterministic FAIL — skipping LLM audit.")
    else:
        logger.info("Persona deterministic PASS — skipping LLM audit.")
    return reconcile_compliance(merged)


def build_graphics_report(chart_health: list[dict]) -> dict:
    """Deterministic chart-health gate. Broken charts are always CRITICAL regardless
    of any LLM visual review."""
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


def _merge_graphics_reports(deterministic: dict, visual: dict | None) -> dict:
    """Combine deterministic chart-health failures with LLM visual findings."""
    if not visual:
        return deterministic
    findings = list(deterministic.get("findings") or []) + list(visual.get("findings") or [])
    is_compliant = bool(deterministic.get("is_compliant")) and bool(visual.get("is_compliant"))
    summaries = [s for s in (deterministic.get("summary"), visual.get("summary")) if s]
    return reconcile_compliance({
        "agent_role": visual.get("agent_role") or "Graphics Designer Visual SME",
        "is_compliant": is_compliant,
        "findings": findings,
        "summary": " | ".join(summaries),
    })


async def run_graphics_designer_qa(
    final_briefing_html: str,
    chart_health: list[dict],
    *,
    model_override: str = None,
    timeout_seconds: int = GRAPHICS_QA_TIMEOUT_SECONDS,
) -> dict:
    """Review the exact executive briefing HTML saved/emailed — not templates or code.

    Flow:
    1. Deterministic chart-health gate (hard fail on broken charts).
    2. Download embedded images from the final HTML artifact.
    3. Multimodal LLM review of rendered charts + email HTML layout."""
    from src.output import reporting

    from src.qa.visual_audit import build_deterministic_visual_report

    deterministic = build_deterministic_visual_report(final_briefing_html, chart_health)
    if not deterministic.get("is_compliant"):
        logger.warning("Graphics QA: deterministic chart-health failed; skipping visual LLM review.")
        return deterministic

    visual_assets = reporting.fetch_briefing_visual_assets(
        final_briefing_html,
        prefetched_by_url=reporting.chart_health_image_cache(chart_health),
    )
    health_text = reporting.format_chart_health(chart_health)
    html_excerpt = (final_briefing_html or "")[:GRAPHICS_BRIEFING_HTML_CHAR_LIMIT]

    intro = (
        "You are reviewing the FINAL Executive Briefing artifact — the exact HTML document "
        "saved to Azure and emailed to the investor. This is NOT Python source, Jinja templates, "
        "or intermediate pipeline code.\n\n"
        "AUDIENCE: Stan, a sophisticated retail portfolio manager — expects institutional-quality "
        "daily briefings comparable to a top-tier sell-side morning note or family-office board pack, "
        "NOT an internal engineering or QA report.\n\n"
        "Also flag if this briefing would feel embarrassing forwarded to an LP, advisor, or C-level peer.\n\n"
        f"DETERMINISTIC CHART HEALTH (ground truth — never override a BROKEN chart to OK):\n{health_text}\n\n"
        f"Images attached below were extracted from this HTML (same URLs the email client loads).\n"
        f"Embedded images fetched: {len(visual_assets)}\n\n"
        f"FINAL EXECUTIVE BRIEFING HTML (exact email body):\n{html_excerpt}"
    )

    parts = [types.Part.from_text(text=intro)]
    for asset in visual_assets:
        parts.append(types.Part.from_text(text=f"[Rendered image from briefing: {asset['name']}]"))
        parts.append(types.Part.from_bytes(data=asset["bytes"], mime_type=asset["mime_type"]))

    if not visual_assets:
        parts.append(types.Part.from_text(
            text="WARNING: No embedded images could be fetched from the briefing HTML. "
                 "Audit layout from the HTML structure and flag missing/broken visuals as CRITICAL."
        ))

    contents = [types.Content(role="user", parts=parts)]
    info = agent_config["board_members"]["graphics_designer_qa"]
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
            call_gemini_async(
                model,
                contents,
                types.GenerateContentConfig(**config_params),
                agent_name="graphics_designer_qa",
            ),
            timeout=timeout_seconds,
        )
        parsed = json.loads(res.text)
        parsed["agent_role"] = info["role"]
        return _merge_graphics_reports(deterministic, reconcile_compliance(parsed))
    except asyncio.TimeoutError:
        logger.warning(f"Graphics Designer QA timed out after {timeout_seconds}s; using deterministic report only.")
        deterministic["findings"] = list(deterministic.get("findings") or []) + [{
            "severity": "WARNING",
            "category": "QA Timeout",
            "description": f"Visual review did not finish within {timeout_seconds}s.",
            "recommendation": "Re-run deliver or inspect the saved executive_briefing HTML manually.",
        }]
        return deterministic
    except Exception as e:
        logger.error(f"Graphics Designer QA failed: {e}")
        deterministic["findings"] = list(deterministic.get("findings") or []) + [{
            "severity": "WARNING",
            "category": "Visual QA Error",
            "description": f"Visual review agent failed: {e}",
            "recommendation": "Check Gemini logs; deterministic chart health still applied.",
        }]
        return deterministic


async def run_qa_integrity_audit(qa_reports, raw_log: str, chairman_json: str,
                                 qa_dashboard_html: str, *,
                                 executive_briefing_html: str = "",
                                 model_override: str = None,
                                 timeout_seconds: int = QA_INTEGRITY_TIMEOUT_SECONDS):
    """The QA-of-the-QA: deterministic pre-checks plus LLM verdict validation.

    Deterministic layer (dashboard fidelity, coverage, self-contradiction) runs
    first via src/qa/integrity_audit.py. The LLM pass adds debate-log accuracy
    checks. Golden fixtures: tests/fixtures/integrity_qa/.

    executive_briefing_html lets the integrity auditor validate Graphics Designer
    findings against the actual investor artifact (avoids false 'missing HTML' claims).
    """
    from src.qa.integrity_audit import (
        build_deterministic_integrity_report,
        build_evidence_context,
        format_evidence_digest,
        merge_integrity_reports,
        sanitize_llm_integrity_findings,
    )

    logger.info("Initiating QA Integrity Audit (QA-of-the-QA).")
    deterministic = build_deterministic_integrity_report(qa_reports, qa_dashboard_html)
    evidence_ctx = build_evidence_context(qa_reports, qa_dashboard_html, executive_briefing_html)
    evidence_digest = format_evidence_digest(evidence_ctx, deterministic)

    reports_digest = json.dumps([
        {
            "agent_role": r.get("agent_role"),
            "is_compliant": r.get("is_compliant"),
            "summary": r.get("summary"),
            "findings": r.get("findings", []),
        }
        for r in qa_reports
    ], default=str)

    briefing_excerpt = (executive_briefing_html or "")[:INTEGRITY_BRIEFING_HTML_CHAR_LIMIT]
    dashboard_excerpt = (qa_dashboard_html or "")[:INTEGRITY_DASHBOARD_HTML_CHAR_LIMIT]
    qa_prompt = (
        f"{evidence_digest}\n\n"
        f"RAW DEBATE LOG (ground truth of what actually happened):\n{raw_log[:25000]}\n\n"
        f"FINAL CHAIRMAN ALLOCATION:\n{chairman_json[:8000]}\n\n"
        f"QA AGENT REPORTS (verdicts to verify — do not re-parse dashboard HTML):\n{reports_digest[:15000]}\n\n"
        f"EXECUTIVE BRIEFING HTML EXCERPT (validate Graphics Designer claims here):\n"
        f"{briefing_excerpt or '[not provided]'}\n\n"
        f"QA DASHBOARD HTML EXCERPT (may be truncated — trust EVIDENCE DIGEST above for fidelity):\n"
        f"{dashboard_excerpt or '[empty]'}"
    )
    contents = [types.Content(role="user", parts=[types.Part.from_text(text=qa_prompt)])]

    info = agent_config["board_members"]["qa_integrity_auditor"]
    model = model_override or info.get("model") or HEAVY_MODEL
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
        if parsed_res.get("findings"):
            parsed_res["findings"] = sanitize_llm_integrity_findings(
                parsed_res["findings"], evidence_ctx
            )
        else:
            parsed_res["findings"] = []
        if not parsed_res["findings"]:
            parsed_res["is_compliant"] = True
            suffix = " LLM pass: no substantiated QA accuracy issues after evidence filter."
            parsed_res["summary"] = (parsed_res.get("summary") or "").strip() + suffix
        return merge_integrity_reports(deterministic, reconcile_compliance(parsed_res))
    except asyncio.TimeoutError:
        logger.warning(f"QA Integrity Audit timed out after {timeout_seconds}s; emitting non-blocking WARNING.")
        timeout_report = {
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
        return merge_integrity_reports(deterministic, timeout_report)
    except Exception as e:
        logger.error(f"Failed to execute or parse QA Integrity Audit: {e}")
        return merge_integrity_reports(deterministic, _execution_error_report(info["role"], e))
