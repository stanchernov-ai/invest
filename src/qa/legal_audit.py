"""Deterministic pre-checks for Legal Counsel QA on the investor-facing briefing."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from src.qa.legal_policy import (
    BRIEFING_ENDORSEMENT_PATTERNS,
    CODE_ENDORSEMENT_PATTERNS,
    CODE_MARKETING_PATTERNS,
    CODE_SCAN_REL_PATHS,
    USER_FACING_CODE_PATHS,
)

# Domains we expect in a normal executive briefing artifact.
_ALLOWED_ASSET_DOMAINS = (
    "stboardroomprod.blob.core.windows.net",
    "quickchart.io",
    "financialmodelingprep.com",
    "images.financialmodelingprep.com",
    "logo.clearbit.com",
)

_URL_RE = re.compile(r"""https?://[^\s"'<>]+""", re.IGNORECASE)
_DISCLAIMER_PHRASES = (
    "not investment advice",
    "not a recommendation",
    "for informational purposes",
    "does not constitute legal advice",
    "consult a qualified",
)


def _domain_allowed(netloc: str) -> bool:
    host = (netloc or "").lower().split(":")[0]
    if not host:
        return True
    if host.endswith(".blob.core.windows.net"):
        return True
    return any(host == d or host.endswith("." + d) for d in _ALLOWED_ASSET_DOMAINS)


def extract_external_urls(html: str) -> list[str]:
    return _URL_RE.findall(html or "")


def audit_briefing_legal_surface(html: str) -> list[dict]:
    """Fast HTML scan before the Legal Counsel LLM pass."""
    findings: list[dict] = []
    html_lower = (html or "").lower()

    unexpected: list[str] = []
    for url in extract_external_urls(html):
        try:
            host = urlparse(url).netloc
        except Exception:
            continue
        if host and not _domain_allowed(host):
            unexpected.append(f"{host} ({url[:80]})")
    if unexpected:
        seen = sorted(set(unexpected))[:8]
        findings.append({
            "severity": "WARNING",
            "category": "Third-Party Assets",
            "description": (
                "Briefing loads assets from domains outside the usual allowlist "
                f"({', '.join(_ALLOWED_ASSET_DOMAINS[:3])}…): "
                + "; ".join(seen)
            ),
            "recommendation": (
                "Confirm licensing/ToS for each external URL or re-host on boardroom blob storage."
            ),
        })

    if not any(phrase in html_lower for phrase in _DISCLAIMER_PHRASES):
        findings.append({
            "severity": "INFO",
            "category": "Disclosure",
            "description": (
                "No standard investment-advice disclaimer detected in the executive briefing footer."
            ),
            "recommendation": (
                "Consider a one-line footer: informational purposes only; not investment or legal advice."
            ),
        })

    if re.search(r"guaranteed\s+(returns?|profit)", html_lower):
        findings.append({
            "severity": "CRITICAL",
            "category": "Regulatory Language",
            "description": "Briefing contains guaranteed-return language.",
            "recommendation": "Remove or soften guaranteed performance claims before distribution.",
        })

    for pattern, category, severity, recommendation in BRIEFING_ENDORSEMENT_PATTERNS:
        if re.search(pattern, html_lower, re.IGNORECASE):
            findings.append({
                "severity": severity,
                "category": category,
                "description": f"Briefing matched risky pattern: {pattern}",
                "recommendation": recommendation,
            })

    return findings


def build_deterministic_legal_report(html: str) -> dict:
    findings = audit_briefing_legal_surface(html)
    has_critical = any(str(f.get("severity", "")).upper() == "CRITICAL" for f in findings)
    crit = sum(1 for f in findings if str(f.get("severity", "")).upper() == "CRITICAL")
    warn = sum(1 for f in findings if str(f.get("severity", "")).upper() == "WARNING")
    return {
        "agent_role": "Legal Counsel QA (deterministic pre-check)",
        "is_compliant": not has_critical,
        "findings": findings,
        "summary": (
            f"Deterministic legal surface scan: {crit} CRITICAL, {warn} WARNING."
            if findings else "Deterministic legal surface scan: no issues flagged."
        ),
    }


def merge_legal_reports(deterministic: dict, llm_report: dict | None) -> dict:
    llm = llm_report or {}
    combined = list(deterministic.get("findings") or []) + list(llm.get("findings") or [])
    is_compliant = bool(deterministic.get("is_compliant")) and bool(llm.get("is_compliant", True))
    if any(str(f.get("severity", "")).upper() == "CRITICAL" for f in combined):
        is_compliant = False
    summaries = [s for s in (deterministic.get("summary"), llm.get("summary")) if s]
    return {
        "agent_role": llm.get("agent_role") or "Legal Counsel QA",
        "is_compliant": is_compliant,
        "findings": combined,
        "summary": " | ".join(summaries) if summaries else "Legal counsel review complete.",
    }


def _scan_text_for_patterns(
    text: str,
    patterns: list[tuple],
    *,
    file_label: str,
) -> list[dict]:
    findings: list[dict] = []
    skip_markers = (
        "must not", "do not", "don't", "never ", "remove ", "avoid ",
        "flag critical", "forbidden", "out of scope", "safe (do not",
    )
    for pattern, category, severity, recommendation in patterns:
        for line in (text or "").splitlines():
            line_lower = line.lower()
            if any(marker in line_lower for marker in skip_markers):
                continue
            match = re.search(pattern, line, re.IGNORECASE)
            if not match:
                continue
            snippet = (match.group(0) or "")[:120]
            findings.append({
                "severity": severity,
                "category": category,
                "description": f"{file_label}: …{snippet}…",
                "recommendation": recommendation,
            })
    return findings


def collect_code_audit_corpus(repo_root: Path | None = None) -> dict[str, str]:
    """Load configured source paths for daily Legal Counsel code review."""
    root = repo_root or Path(__file__).resolve().parents[2]
    corpus: dict[str, str] = {}
    for rel in CODE_SCAN_REL_PATHS:
        path = root / rel
        if path.is_file():
            try:
                corpus[rel] = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
    return corpus


def audit_codebase_legal_surface(corpus: dict[str, str]) -> list[dict]:
    """Deterministic scan of product code + prompts for endorsement / marketing risk."""
    findings: list[dict] = []
    for rel, text in sorted(corpus.items()):
        patterns = list(CODE_ENDORSEMENT_PATTERNS)
        if rel in USER_FACING_CODE_PATHS:
            patterns.extend(CODE_MARKETING_PATTERNS)
        findings.extend(
            _scan_text_for_patterns(text, patterns, file_label=rel)
        )
    return findings


def build_deterministic_code_legal_report(corpus: dict[str, str]) -> dict:
    findings = audit_codebase_legal_surface(corpus)
    has_critical = any(str(f.get("severity", "")).upper() == "CRITICAL" for f in findings)
    crit = sum(1 for f in findings if str(f.get("severity", "")).upper() == "CRITICAL")
    warn = sum(1 for f in findings if str(f.get("severity", "")).upper() == "WARNING")
    files = len(corpus)
    return {
        "agent_role": "Legal Counsel QA (deterministic code pre-check)",
        "is_compliant": not has_critical,
        "findings": findings,
        "summary": (
            f"Deterministic code scan ({files} files): {crit} CRITICAL, {warn} WARNING."
            if findings else f"Deterministic code scan ({files} files): no issues flagged."
        ),
        "files_scanned": sorted(corpus.keys()),
    }
