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
)


def _normalize_role(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


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


def build_deterministic_integrity_report(qa_reports: list[dict], dashboard_html: str) -> dict:
    """Run all deterministic integrity pre-checks — no LLM."""
    findings = []
    findings.extend(audit_qa_coverage(qa_reports))
    findings.extend(audit_qa_report_quality(qa_reports))
    findings.extend(audit_dashboard_fidelity(qa_reports, dashboard_html))

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
