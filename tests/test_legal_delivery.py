"""Tests for Legal Counsel persistence and email rendering."""
from src.qa.legal_delivery import (
    briefing_blob_name,
    code_audit_blob_name,
    render_legal_counsel_email_html,
)


def test_briefing_blob_name():
    assert briefing_blob_name("20260530_120000") == "legal_counsel_briefing_20260530_120000.json"


def test_render_email_includes_findings():
    report = {
        "is_compliant": False,
        "summary": "One CRITICAL endorsement risk.",
        "findings": [{
            "severity": "CRITICAL",
            "category": "Implied Endorsement",
            "description": "Briefing implies Buffett endorses product.",
            "recommendation": "Remove endorsement language.",
        }],
    }
    html = render_legal_counsel_email_html(
        report,
        title="Legal Counsel — Executive Briefing Review",
        subtitle="Run 20260530_120000",
        artifact_ref=briefing_blob_name("20260530_120000"),
    )
    assert "REVIEW" in html or "FINDINGS" in html
    assert "Implied Endorsement" in html
    assert "legal_counsel_briefing_20260530_120000.json" in html


def test_render_email_pass_shows_no_findings():
    report = {"is_compliant": True, "summary": "Clean.", "findings": []}
    html = render_legal_counsel_email_html(
        report,
        title="Legal Counsel — Daily Codebase Audit",
        subtitle="Date 20260530",
        artifact_ref=code_audit_blob_name("20260530"),
    )
    assert "No findings flagged" in html
    assert "PASS" in html
