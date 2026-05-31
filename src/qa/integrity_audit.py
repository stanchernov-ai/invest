"""Deterministic pre-checks for the QA Integrity Auditor (QA-of-the-QA).

Golden fixtures: tests/fixtures/integrity_qa/
"""
import re
from bs4 import BeautifulSoup

from src.qa_pipeline import reconcile_compliance

# Post-flight agents expected before the integrity auditor runs.
EXPECTED_QA_ROLES = (
    "Post Mortem QA Auditor",
    "Systems Architect QA",
    "Prompt Engineer QA",
    "Graphics Designer Visual SME",
    "Legal Counsel QA",
)


def _normalize_role(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def extract_dashboard_audit_sections(dashboard_html: str) -> list[str]:
    """Return h2 section titles from the QA dashboard (e.g. 'Post Mortem QA Auditor Audit')."""
    if not (dashboard_html or "").strip():
        return []
    soup = BeautifulSoup(dashboard_html, "html.parser")
    return [h2.get_text(strip=True) for h2 in soup.find_all("h2") if h2.get_text(strip=True)]


def _role_in_section_title(role: str, section_title: str) -> bool:
    """Fuzzy match agent role to a dashboard audit section heading."""
    norm_role = _normalize_role(role)
    norm_title = _normalize_role(section_title.replace(" audit", ""))
    if not norm_role or not norm_title:
        return False
    return norm_role in norm_title or norm_title in norm_role


def audit_dashboard_sections(qa_reports: list[dict], dashboard_html: str) -> list[dict]:
    """Verify each QA report has a dedicated audit section in the dashboard HTML."""
    findings: list[dict] = []
    sections = extract_dashboard_audit_sections(dashboard_html)
    if not sections and qa_reports:
        return findings  # handled by audit_dashboard_fidelity

    for report in qa_reports or []:
        role = report.get("agent_role", "")
        if "integrity" in _normalize_role(role):
            continue
        if any(_role_in_section_title(role, sec) for sec in sections):
            continue
        findings.append({
            "severity": "CRITICAL",
            "category": "Dashboard Fidelity",
            "description": (
                f"QA dashboard has no audit section for '{role}'. "
                f"Expected an h2 like '{role} Audit'."
            ),
            "recommendation": "Regenerate the dashboard from the full qa_reports list.",
        })
    return findings


def audit_findings_rendered(qa_reports: list[dict], dashboard_html: str) -> list[dict]:
    """Verify non-trivial finding descriptions appear in the rendered dashboard body."""
    findings: list[dict] = []
    html_norm = re.sub(r"\s+", " ", (dashboard_html or "").lower())

    for report in qa_reports or []:
        role = report.get("agent_role", "")
        if "integrity" in _normalize_role(role):
            continue
        for idx, finding in enumerate(report.get("findings") or []):
            desc = (finding.get("description") or "").strip()
            if len(desc) < 24:
                continue
            needle = re.sub(r"\s+", " ", desc[:72]).lower()
            if needle not in html_norm:
                findings.append({
                    "severity": "CRITICAL",
                    "category": "Dashboard Fidelity",
                    "description": (
                        f"Finding #{idx + 1} for '{role}' is absent from the rendered dashboard HTML "
                        f"(missing text prefix: {desc[:72]!r}…)."
                    ),
                    "recommendation": "Ensure generate_qa_dashboard_html renders all finding descriptions.",
                })
    return findings


def build_evidence_context(
    qa_reports: list[dict],
    dashboard_html: str,
    executive_briefing_html: str,
) -> dict:
    """Structured ground truth passed to the LLM integrity pass."""
    briefing = (executive_briefing_html or "").strip()
    sections = extract_dashboard_audit_sections(dashboard_html)
    agent_sections: dict[str, bool] = {}
    findings_rendered: dict[str, list[bool]] = {}

    for report in qa_reports or []:
        role = report.get("agent_role", "")
        if "integrity" in _normalize_role(role):
            continue
        agent_sections[role] = any(_role_in_section_title(role, sec) for sec in sections)
        flags: list[bool] = []
        html_norm = re.sub(r"\s+", " ", (dashboard_html or "").lower())
        for finding in report.get("findings") or []:
            desc = (finding.get("description") or "").strip()
            if len(desc) < 24:
                flags.append(True)
                continue
            needle = re.sub(r"\s+", " ", desc[:72]).lower()
            flags.append(needle in html_norm)
        findings_rendered[role] = flags

    return {
        "briefing_provided": bool(briefing),
        "briefing_char_count": len(briefing),
        "dashboard_char_count": len(dashboard_html or ""),
        "dashboard_section_titles": sections,
        "agent_sections": agent_sections,
        "findings_rendered": findings_rendered,
    }


def format_evidence_digest(ctx: dict, deterministic: dict) -> str:
    """Human-readable ground truth the LLM must not contradict."""
    lines = [
        "DETERMINISTIC PRE-CHECK SUMMARY (authoritative):",
        deterministic.get("summary", ""),
    ]
    for f in deterministic.get("findings") or []:
        lines.append(
            f"  - [{f.get('severity')}] {f.get('category')}: {f.get('description')}"
        )

    lines.append("")
    lines.append("EVIDENCE AVAILABILITY (authoritative):")
    if ctx.get("briefing_provided"):
        lines.append(
            f"  - Executive briefing HTML: PROVIDED ({ctx.get('briefing_char_count', 0)} chars). "
            "Do NOT report it as missing."
        )
    else:
        lines.append("  - Executive briefing HTML: NOT PROVIDED (skip Graphics HTML cross-check).")

    lines.append(f"  - QA dashboard HTML: {ctx.get('dashboard_char_count', 0)} chars total.")
    lines.append("  - Dashboard audit sections detected:")
    for title in ctx.get("dashboard_section_titles") or []:
        lines.append(f"      • {title}")

    lines.append("  - Per-agent section + finding render status:")
    for role, present in (ctx.get("agent_sections") or {}).items():
        flags = ctx.get("findings_rendered", {}).get(role, [])
        missing = sum(1 for ok in flags if not ok)
        status = "section OK" if present else "SECTION MISSING"
        finding_note = f", {missing} finding(s) not in HTML" if missing else ", all findings rendered"
        lines.append(f"      • {role}: {status}{finding_note}")

    lines.append("")
    lines.append(
        "RULE: Do NOT re-audit dashboard badge matching or section presence — "
        "deterministic pre-check already did. Focus on debate-log/chairman verdict accuracy "
        "and Graphics Designer finding validation against the briefing excerpt."
    )
    return "\n".join(lines)


def _claims_missing_briefing(description: str) -> bool:
    desc = (description or "").lower()
    briefing_terms = (
        "executive briefing",
        "briefing html",
        "investor-facing artifact",
        "investor briefing",
        "rendered html dashboard",
    )
    missing_terms = (
        "not provided",
        "was not included",
        "not included",
        "missing",
        "could not be validated",
        "un-auditable",
        "without this",
        "absent from the input",
        "was not provided",
    )
    return any(t in desc for t in briefing_terms) and any(m in desc for m in missing_terms)


def _claims_missing_dashboard_section(description: str, agent_sections: dict[str, bool]) -> bool:
    desc = (description or "").lower()
    omit_terms = ("omit", "omits", "omitted", "missing section", "not presented", "no section", "entirely omitted")
    if not any(t in desc for t in omit_terms):
        return False
    for role, present in (agent_sections or {}).items():
        if not present:
            continue
        norm = _normalize_role(role)
        if norm in desc or norm.split("(")[0].strip() in desc:
            return True
    return False


def _claims_finding_truncated(description: str, findings_rendered: dict[str, list[bool]]) -> bool:
    desc = (description or "").lower()
    if "truncat" not in desc and "incomplete" not in desc:
        return False
    for role, flags in (findings_rendered or {}).items():
        if flags and all(flags):
            norm = _normalize_role(role)
            if norm in desc or norm.split("(")[0].strip() in desc:
                return True
    return False


def sanitize_llm_integrity_findings(
    findings: list[dict],
    ctx: dict,
    *,
    vote_ctx: dict | None = None,
) -> list[dict]:
    """Drop LLM findings that contradict deterministic evidence context."""
    cleaned: list[dict] = []
    for finding in findings or []:
        desc = finding.get("description") or ""
        cat = (finding.get("category") or "").lower()

        if vote_ctx and _claims_false_max_buy_violation(desc, vote_ctx):
            continue
        if vote_ctx and _contradicts_deterministic_post_mortem_pass(desc, vote_ctx):
            continue
        if ctx.get("briefing_provided") and _claims_missing_briefing(desc):
            continue
        if _claims_missing_dashboard_section(desc, ctx.get("agent_sections") or {}):
            continue
        if _claims_finding_truncated(desc, ctx.get("findings_rendered") or {}):
            continue
        # Deterministic layer owns dashboard badge/section checks — ignore LLM duplicates.
        if cat == "dashboard fidelity" and ctx.get("agent_sections"):
            if _claims_missing_dashboard_section(desc, ctx.get("agent_sections") or {}):
                continue
            if "truncat" in desc.lower() and any(
                all(flags) for flags in (ctx.get("findings_rendered") or {}).values() if flags
            ):
                continue

        cleaned.append(finding)
    return cleaned


def extract_dashboard_statuses(dashboard_html: str) -> dict[str, bool]:
    """Parse the QA summary table: role -> is_compliant (True=PASS)."""
    if not (dashboard_html or "").strip():
        return {}

    soup = BeautifulSoup(dashboard_html, "html.parser")
    statuses: dict[str, bool] = {}

    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        strong = cells[0].find("strong")
        if not strong:
            continue
        role = strong.get_text(strip=True)
        cell_html = str(cells[1])
        status_text = cells[1].get_text(strip=True)
        if "PASS" not in status_text and "FAIL" not in status_text and "✅" not in cell_html and "❌" not in cell_html:
            continue
        is_pass = "❌" not in cell_html and ("✅" in cell_html or "PASS" in status_text)
        statuses[role] = is_pass

    return statuses


def audit_dashboard_fidelity(qa_reports: list[dict], dashboard_html: str) -> list[dict]:
    """Verify rendered dashboard PASS/FAIL badges match the underlying QA JSON."""
    findings: list[dict] = []
    dashboard = extract_dashboard_statuses(dashboard_html)
    if not dashboard and qa_reports:
        findings.append({
            "severity": "CRITICAL",
            "category": "Dashboard Fidelity",
            "description": "QA dashboard HTML contains no parseable agent status rows.",
            "recommendation": "Regenerate the dashboard from qa_reports via generate_qa_dashboard_html.",
        })
        return findings

    norm_dashboard = {_normalize_role(k): v for k, v in dashboard.items()}

    for report in qa_reports or []:
        role = report.get("agent_role", "")
        if "integrity" in _normalize_role(role):
            continue
        expected = bool(report.get("is_compliant"))
        norm_role = _normalize_role(role)
        if norm_role not in norm_dashboard:
            findings.append({
                "severity": "CRITICAL",
                "category": "Dashboard Fidelity",
                "description": f"Agent '{role}' appears in QA reports but is missing from the dashboard summary table.",
                "recommendation": "Ensure generate_qa_dashboard_html receives the full qa_reports list.",
            })
            continue
        actual = norm_dashboard[norm_role]
        if actual != expected:
            badge = "PASS" if actual else "FAIL"
            expected_badge = "PASS" if expected else "FAIL"
            findings.append({
                "severity": "CRITICAL",
                "category": "Dashboard Fidelity",
                "description": (
                    f"Dashboard shows {badge} for '{role}' but the QA report JSON says {expected_badge}."
                ),
                "recommendation": "Rebuild the QA dashboard from the authoritative qa_reports JSON.",
            })

    return findings


def audit_qa_report_quality(qa_reports: list[dict]) -> list[dict]:
    """Catch self-contradictory or empty QA reports before the LLM integrity pass."""
    findings: list[dict] = []
    for report in qa_reports or []:
        role = report.get("agent_role", "Unknown")
        if "integrity" in _normalize_role(role):
            continue
        findings_list = report.get("findings") or []
        has_critical = any(str(f.get("severity", "")).upper() == "CRITICAL" for f in findings_list)
        if has_critical and report.get("is_compliant"):
            findings.append({
                "severity": "CRITICAL",
                "category": "QA Self-Contradiction",
                "description": f"'{role}' self-reported PASS while logging CRITICAL finding(s).",
                "recommendation": "reconcile_compliance() should force is_compliant=false — investigate bypass.",
            })
        if not report.get("summary", "").strip():
            findings.append({
                "severity": "WARNING",
                "category": "QA Coverage",
                "description": f"'{role}' returned an empty summary.",
                "recommendation": "Tighten the QA agent prompt to require a non-empty summary.",
            })
        if not report.get("is_compliant") and not findings_list:
            findings.append({
                "severity": "WARNING",
                "category": "QA Quality",
                "description": f"'{role}' reported FAIL with zero findings — unexplained failure.",
                "recommendation": "Require at least one finding when is_compliant is false.",
            })
    return findings


def audit_qa_coverage(qa_reports: list[dict]) -> list[dict]:
    """Ensure the core post-flight QA trio ran before integrity audit."""
    findings: list[dict] = []
    present = {_normalize_role(r.get("agent_role", "")) for r in (qa_reports or [])}
    for required in EXPECTED_QA_ROLES:
        norm = _normalize_role(required)
        if not any(norm in p or p in norm for p in present):
            findings.append({
                "severity": "CRITICAL",
                "category": "QA Coverage",
                "description": f"Required QA agent '{required}' has no report in this run.",
                "recommendation": "Ensure run_post_flight_qa completed before the integrity audit.",
            })
    return findings


def _find_qa_report(qa_reports: list[dict], role_substring: str) -> dict | None:
    needle = _normalize_role(role_substring)
    for report in qa_reports or []:
        role = _normalize_role(report.get("agent_role", ""))
        if needle in role:
            return report
    return None


def build_vote_ground_truth_context(
    chairman: dict | None,
    raw_verdicts: dict | None,
    *,
    all_symbols: list[str] | None = None,
    portfolio_symbols: set[str] | None = None,
    raw_board_messages: list | None = None,
) -> dict:
    """Round 2 JSON vote digest + deterministic post-mortem re-check for integrity audit."""
    from src.core.guardrails import MAX_DAILY_BUYS, count_equity_buys
    from src.core.vote_engine import build_vote_summaries, format_vote_digest
    from src.qa.post_mortem_audit import (
        audit_debate_prose_vs_raw_verdicts,
        audit_post_mortem_deterministic,
        format_post_mortem_digest,
    )

    chairman = chairman or {}
    all_symbols = all_symbols or []
    portfolio_symbols = portfolio_symbols or set()

    ctx: dict = {
        "equity_buy_count": count_equity_buys(chairman) if chairman else 0,
        "max_equity_buys": MAX_DAILY_BUYS,
        "vote_digest_text": "",
        "post_mortem_digest_text": "",
        "deterministic_violations": None,
        "prose_drift": [],
        "persona_violations": [],
    }

    if not raw_verdicts or not all_symbols:
        return ctx

    summaries = build_vote_summaries(
        raw_verdicts, all_symbols, portfolio_symbols=portfolio_symbols
    )
    ctx["vote_digest_text"] = format_vote_digest(
        summaries, portfolio_symbols=portfolio_symbols
    )
    ctx["deterministic_violations"] = audit_post_mortem_deterministic(
        chairman,
        raw_verdicts,
        all_symbols=all_symbols,
        portfolio_symbols=portfolio_symbols,
        raw_board_messages=raw_board_messages,
    )
    ctx["post_mortem_digest_text"] = format_post_mortem_digest(
        ctx["deterministic_violations"],
        raw_verdicts,
        all_symbols=all_symbols,
        portfolio_symbols=portfolio_symbols,
    )
    ctx["prose_drift"] = audit_debate_prose_vs_raw_verdicts(
        raw_board_messages, raw_verdicts, all_symbols=all_symbols
    )
    return ctx


def format_vote_ground_truth_digest(vote_ctx: dict) -> str:
    """Human-readable vote SSOT block for the integrity LLM prompt."""
    lines = [
        "VOTE GROUND TRUTH (Round 2 raw_verdicts JSON — authoritative for vote counts):",
        "Do NOT infer buy/sell tallies from debate markdown; use the digest below.",
        "",
    ]
    if vote_ctx.get("vote_digest_text"):
        lines.append(vote_ctx["vote_digest_text"])
    else:
        lines.append("  (raw_verdicts not available for this run)")
    lines.append("")
    lines.append(
        f"MAX EQUITY BUYS: {vote_ctx.get('equity_buy_count', 0)}/"
        f"{vote_ctx.get('max_equity_buys', 3)} Buy/Strong Buy equity positions "
        f"(TLT/VXX hedge excluded from cap). "
        f"capital_flow_audit.target_tickers may list TLT/VXX plus equity targets — "
        f"do NOT flag a max-3 violation from target_tickers length alone."
    )
    drift = vote_ctx.get("prose_drift") or []
    if drift:
        lines.append("")
        lines.append("PROSE vs JSON DRIFT (debate markdown disagrees with raw_verdicts):")
        for item in drift[:8]:
            lines.append(f"  - {item}")
    det = vote_ctx.get("deterministic_violations")
    if det is None:
        return "\n".join(lines)
    if det:
        lines.append("")
        lines.append(
            "DETERMINISTIC POST MORTEM RE-CHECK (Python vote_engine — authoritative):"
        )
        for item in det:
            lines.append(f"  - {item}")
    else:
        lines.append("")
        lines.append(
            "DETERMINISTIC POST MORTEM RE-CHECK: PASS — chairman aligns with vote digest."
        )
    return "\n".join(lines)


def audit_post_mortem_report_accuracy(
    qa_reports: list[dict],
    vote_ctx: dict,
) -> list[dict]:
    """Compare Post Mortem QA verdict to deterministic vote_engine re-check."""
    report = _find_qa_report(qa_reports, "post mortem")
    det = vote_ctx.get("deterministic_violations")
    if not report or det is None:
        return []

    expected_pass = len(det) == 0
    actual_pass = bool(report.get("is_compliant"))
    if actual_pass == expected_pass:
        return []

    if actual_pass and not expected_pass:
        return [{
            "severity": "CRITICAL",
            "category": "Verdict Accuracy - Post Mortem QA",
            "description": (
                f"Post Mortem QA reported PASS but deterministic vote_engine re-check found "
                f"{len(det)} violation(s): {'; '.join(det[:3])}"
            ),
            "recommendation": "Post Mortem must FAIL when Python vote alignment fails.",
        }]

    return [{
        "severity": "WARNING",
        "category": "Verdict Accuracy - Post Mortem QA",
        "description": (
            "Post Mortem QA reported FAIL but deterministic vote_engine re-check found "
            "no violations — LLM may have inferred vote counts from debate markdown."
        ),
        "recommendation": "Trust raw_verdicts vote digest over debate prose parsing.",
    }]


def audit_prompt_engineer_report_accuracy(
    qa_reports: list[dict],
    raw_board_messages: list | None,
    all_symbols: list[str] | None,
) -> list[dict]:
    """Compare Prompt Engineer QA verdict to deterministic persona re-check."""
    from src.qa.persona_audit import audit_debate_persona

    report = _find_qa_report(qa_reports, "prompt engineer")
    if not report:
        return []

    violations, _ = audit_debate_persona(raw_board_messages or [], all_symbols or [])
    expected_pass = len(violations) == 0
    actual_pass = bool(report.get("is_compliant"))
    if actual_pass == expected_pass:
        return []

    if actual_pass and not expected_pass:
        return [{
            "severity": "CRITICAL",
            "category": "Verdict Accuracy - Prompt Engineer QA",
            "description": (
                f"Prompt Engineer QA reported PASS but deterministic persona re-check found "
                f"{len(violations)} issue(s): {'; '.join(violations[:2])}"
            ),
            "recommendation": "Prompt Engineer must FAIL when Python persona audit fails.",
        }]

    return [{
        "severity": "WARNING",
        "category": "Verdict Accuracy - Prompt Engineer QA",
        "description": (
            "Prompt Engineer QA reported FAIL but deterministic persona re-check found "
            "no violations — verify quote attribution against Round 2 blocks."
        ),
        "recommendation": "Use per-panelist Round 2 blocks; cite evidence snippets.",
    }]


def _claims_false_max_buy_violation(description: str, vote_ctx: dict) -> bool:
    """Drop LLM findings that count hedge symbols in target_tickers toward max-3."""
    equity = vote_ctx.get("equity_buy_count")
    cap = vote_ctx.get("max_equity_buys", 3)
    if equity is None or equity > cap:
        return False
    desc = (description or "").lower()
    if not any(t in desc for t in ("max 3", "max-3", "3-buy", "buy count", "exceeds")):
        return False
    if "target_ticker" in desc or "target tickers" in desc:
        return True
    if re.search(r"\b4\b", desc) and "buy" in desc:
        return True
    return False


def _contradicts_deterministic_post_mortem_pass(description: str, vote_ctx: dict) -> bool:
    """Drop LLM claims Post Mortem missed violations when Python re-check passed."""
    det = vote_ctx.get("deterministic_violations")
    if det:
        return False
    desc = (description or "").lower()
    if "post mortem" not in desc:
        return False
    if any(t in desc for t in ("failed to identify", "incorrectly reported", "false negative", "rubber-stamp")):
        return _claims_false_max_buy_violation(description, vote_ctx) or (
            "max 3" in desc or "max-3" in desc or "3-buy" in desc
        )
    return False


def build_deterministic_integrity_report(
    qa_reports: list[dict],
    dashboard_html: str,
    *,
    vote_ctx: dict | None = None,
    raw_board_messages: list | None = None,
    all_symbols: list[str] | None = None,
) -> dict:
    """Run all deterministic integrity pre-checks — no LLM."""
    findings = []
    findings.extend(audit_qa_coverage(qa_reports))
    findings.extend(audit_qa_report_quality(qa_reports))
    findings.extend(audit_dashboard_fidelity(qa_reports, dashboard_html))
    findings.extend(audit_dashboard_sections(qa_reports, dashboard_html))
    findings.extend(audit_findings_rendered(qa_reports, dashboard_html))
    if vote_ctx is not None:
        findings.extend(audit_post_mortem_report_accuracy(qa_reports, vote_ctx))
    if raw_board_messages is not None and all_symbols:
        findings.extend(
            audit_prompt_engineer_report_accuracy(qa_reports, raw_board_messages, all_symbols)
        )

    has_critical = any(str(f.get("severity", "")).upper() == "CRITICAL" for f in findings)
    crit = sum(1 for f in findings if str(f.get("severity", "")).upper() == "CRITICAL")
    warn = sum(1 for f in findings if str(f.get("severity", "")).upper() == "WARNING")

    return reconcile_compliance({
        "agent_role": "QA Integrity (deterministic pre-check)",
        "is_compliant": not has_critical,
        "findings": findings,
        "summary": (
            f"Deterministic integrity pre-check: {crit} CRITICAL, {warn} WARNING."
            if findings else "Deterministic integrity pre-check: all dashboard and coverage checks passed."
        ),
    })


def merge_integrity_reports(deterministic: dict, llm_report: dict | None) -> dict:
    """Combine deterministic pre-check with the LLM integrity auditor output."""
    if not llm_report:
        return deterministic
    findings = list(deterministic.get("findings") or []) + list(llm_report.get("findings") or [])
    is_compliant = bool(deterministic.get("is_compliant")) and bool(llm_report.get("is_compliant"))
    summaries = [s for s in (deterministic.get("summary"), llm_report.get("summary")) if s]
    return reconcile_compliance({
        "agent_role": llm_report.get("agent_role", "QA Integrity Auditor"),
        "is_compliant": is_compliant,
        "findings": findings,
        "summary": " | ".join(summaries),
    })
