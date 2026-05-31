"""Tests for Legal Counsel deterministic surface audit."""
from src.qa.legal_audit import (
    audit_briefing_legal_surface,
    build_deterministic_legal_report,
    merge_legal_reports,
)


def test_allowed_domains_no_warning():
    html = (
        '<img src="https://stboardroomprod.blob.core.windows.net/charts/x.png">'
        '<p>For informational purposes only — not investment advice.</p>'
    )
    findings = audit_briefing_legal_surface(html)
    assert not any(f["severity"] == "WARNING" for f in findings)


def test_unexpected_domain_flags_warning():
    html = '<img src="https://evil-cdn.example.com/stolen-logo.png">'
    findings = audit_briefing_legal_surface(html)
    assert any(f["category"] == "Third-Party Assets" for f in findings)


def test_guaranteed_returns_critical():
    html = "<p>Our model delivers guaranteed returns every quarter.</p>"
    report = build_deterministic_legal_report(html)
    assert report["is_compliant"] is False
    assert any(f["severity"] == "CRITICAL" for f in report["findings"])


def test_missing_disclaimer_info_only():
    html = "<p>Portfolio update for Stan.</p>"
    findings = audit_briefing_legal_surface(html)
    assert any(f["severity"] == "INFO" and f["category"] == "Disclosure" for f in findings)


def test_merge_legal_reports_combines_findings():
    det = build_deterministic_legal_report("<p>guaranteed profit</p>")
    llm = {
        "agent_role": "Legal Counsel QA",
        "is_compliant": True,
        "findings": [{
            "severity": "WARNING",
            "category": "Trademark",
            "description": "Uses NVIDIA logo without attribution.",
            "recommendation": "Add source line or remove logo.",
        }],
        "summary": "One trademark concern.",
    }
    merged = merge_legal_reports(det, llm)
    assert merged["is_compliant"] is False
    assert len(merged["findings"]) >= 2


def test_code_audit_collects_agents_py():
    from src.qa.legal_audit import collect_code_audit_corpus, build_deterministic_code_legal_report
    corpus = collect_code_audit_corpus()
    assert "src/core/agents.py" in corpus
    report = build_deterministic_code_legal_report(corpus)
    assert report["is_compliant"] is True
    assert "src/core/agents.py" in (report.get("files_scanned") or [])


def test_panelist_prompts_include_investor_heroes():
    from src.core.agents import agent_config
    hyp = agent_config["board_members"]["hypatia"]["system_instruction"]
    assert "Warren Buffett" in hyp or "Munger" in hyp
    assert "margin of safety" in hyp.lower()
    assert "NEVER fabricate a direct quote" in hyp
