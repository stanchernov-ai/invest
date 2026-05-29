"""Deterministic Post Mortem QA pre-checks — chairman vs Round 2 raw_verdicts SSOT."""
from __future__ import annotations

from src.core.compliance_audit import audit_chairman_compliance
from src.core.vote_engine import build_vote_summaries, format_vote_digest


def audit_post_mortem_deterministic(
    chairman: dict,
    raw_verdicts: dict[str, dict] | None,
    *,
    all_symbols: list[str],
    portfolio_symbols: set[str] | None = None,
) -> list[str]:
    """Return violation strings; empty means chairman aligns with vote_engine math."""
    if not chairman:
        return ["Chairman allocation JSON is empty."]
    if not raw_verdicts:
        return [
            "POST MORTEM: raw_verdicts missing from debate checkpoint — "
            "cannot verify vote tallies against chairman JSON."
        ]
    return audit_chairman_compliance(
        chairman,
        raw_verdicts,
        all_symbols=all_symbols,
        portfolio_symbols=portfolio_symbols,
    )


def format_post_mortem_digest(
    violations: list[str],
    raw_verdicts: dict[str, dict] | None,
    *,
    all_symbols: list[str],
    portfolio_symbols: set[str] | None = None,
) -> str:
    portfolio_symbols = portfolio_symbols or set()
    lines = [
        "DETERMINISTIC POST MORTEM PRE-CHECK (Round 2 raw_verdicts JSON — authoritative; "
        "do NOT re-count from debate markdown alone):",
    ]
    if raw_verdicts and all_symbols:
        summaries = build_vote_summaries(
            raw_verdicts, all_symbols, portfolio_symbols=portfolio_symbols
        )
        lines.append(format_vote_digest(summaries, portfolio_symbols=portfolio_symbols))
        lines.append("")
    if not violations:
        lines.append(
            "Verdict: PASS — max buys, hedge, majority alignment, and majority-buy mandate verified."
        )
        return "\n".join(lines)
    lines.append("Verdict: FAIL — Post Mortem must not PASS while these stand:")
    for v in violations:
        lines.append(f"  - {v}")
    return "\n".join(lines)


def merge_post_mortem_reports(deterministic_violations: list[str], llm_report: dict | None) -> dict:
    """Combine Python vote gate with Post Mortem LLM audit."""
    llm = llm_report or {}
    llm_findings = list(llm.get("findings") or [])
    combined_findings = list(llm_findings)

    for v in deterministic_violations:
        combined_findings.insert(0, {
            "severity": "CRITICAL",
            "category": "Procedural",
            "description": v,
            "recommendation": (
                "Chairman JSON must match Round 2 raw_verdicts majority math; "
                "plurality Buy (e.g. 2/5) cannot authorize a purchase."
            ),
        })

    if deterministic_violations:
        is_compliant = False
    elif llm_report:
        is_compliant = bool(llm.get("is_compliant"))
    else:
        is_compliant = False

    summary = (llm.get("summary") or "").strip()
    if deterministic_violations and summary:
        summary = f"Deterministic post mortem FAIL ({len(deterministic_violations)} issue(s)). {summary}"
    elif deterministic_violations:
        summary = f"Deterministic post mortem FAIL — {len(deterministic_violations)} issue(s) detected."

    return {
        "agent_role": llm.get("agent_role") or "Post Mortem QA Auditor",
        "is_compliant": is_compliant,
        "findings": combined_findings,
        "summary": summary or "Post mortem audit complete.",
    }
