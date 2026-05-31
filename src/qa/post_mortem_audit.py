"""Deterministic Post Mortem QA pre-checks — chairman vs Round 2 raw_verdicts SSOT."""
from __future__ import annotations

import re

from src.core.compliance_audit import audit_chairman_compliance
from src.core.guardrails import _normalize_verdict
from src.core.vote_engine import (
    AGENT_DISPLAY,
    AGENT_KEYS,
    build_matrix_from_raw_verdicts,
    build_vote_summaries,
    format_vote_digest,
)

_SCRATCHPAD_DIGEST_LINE_RE = re.compile(
    r"^\s*([A-Z][A-Z0-9.\-]{0,9}):\s*buy_side=(\d)/5\s*sell_side=(\d)/5",
    re.MULTILINE,
)


def audit_scratchpad_digest_consistency(
    chairman: dict,
    raw_verdicts: dict[str, dict] | None,
    *,
    all_symbols: list[str],
    portfolio_symbols: set[str] | None = None,
) -> list[str]:
    """Chairman scratchpad vote digest must match Round 2 raw_verdicts math."""
    scratch = (chairman or {}).get("chain_of_thought_scratchpad") or ""
    if "DETERMINISTIC VOTE DIGEST" not in scratch or not raw_verdicts:
        return []

    summaries = build_vote_summaries(
        raw_verdicts, all_symbols, portfolio_symbols=portfolio_symbols
    )
    violations: list[str] = []
    for match in _SCRATCHPAD_DIGEST_LINE_RE.finditer(scratch):
        sym = match.group(1).strip()
        scratch_buy = int(match.group(2))
        scratch_sell = int(match.group(3))
        summary = summaries.get(sym)
        if not summary:
            continue
        if (
            summary.buy_side_count() != scratch_buy
            or summary.sell_side_count() != scratch_sell
        ):
            violations.append(
                f"SCRATCHPAD DIGEST MISMATCH: {sym} scratchpad shows "
                f"buy_side={scratch_buy}/5 sell_side={scratch_sell}/5 but "
                f"raw_verdicts JSON has buy_side={summary.buy_side_count()}/5 "
                f"sell_side={summary.sell_side_count()}/5."
            )
    return violations


def audit_debate_prose_vs_raw_verdicts(
    raw_messages: list[dict] | None,
    raw_verdicts: dict[str, dict] | None,
    *,
    all_symbols: list[str],
) -> list[str]:
    """Round 2 debate prose must match structured raw_verdicts (SSOT cross-check)."""
    if not raw_messages or not raw_verdicts:
        return []

    from src.qa_pipeline import parse_board_matrix

    prose_matrix = parse_board_matrix(raw_messages, all_symbols)
    json_matrix = build_matrix_from_raw_verdicts(raw_verdicts, all_symbols)
    violations: list[str] = []
    for sym in all_symbols:
        for agent_key in AGENT_KEYS:
            prose = _normalize_verdict(prose_matrix.get(sym, {}).get(agent_key, ""))
            json_v = _normalize_verdict(json_matrix.get(sym, {}).get(agent_key, ""))
            if not prose or not json_v:
                continue
            if prose != json_v:
                label = AGENT_DISPLAY.get(agent_key, agent_key)
                violations.append(
                    f"VOTE JSON/PROSE DRIFT: {sym} {label} — debate log Round 2 says "
                    f"{prose_matrix[sym][agent_key]!r} but raw_verdicts JSON says {json_v!r}."
                )
    return violations


def audit_post_mortem_deterministic(
    chairman: dict,
    raw_verdicts: dict[str, dict] | None,
    *,
    all_symbols: list[str],
    portfolio_symbols: set[str] | None = None,
    raw_board_messages: list[dict] | None = None,
) -> list[str]:
    """Return violation strings; empty means chairman aligns with vote_engine math."""
    if not chairman:
        return ["Chairman allocation JSON is empty."]
    if not raw_verdicts:
        return [
            "POST MORTEM: raw_verdicts missing from debate checkpoint — "
            "cannot verify vote tallies against chairman JSON."
        ]
    violations = audit_chairman_compliance(
        chairman,
        raw_verdicts,
        all_symbols=all_symbols,
        portfolio_symbols=portfolio_symbols,
    )
    violations.extend(
        audit_scratchpad_digest_consistency(
            chairman,
            raw_verdicts,
            all_symbols=all_symbols,
            portfolio_symbols=portfolio_symbols,
        )
    )
    violations.extend(
        audit_debate_prose_vs_raw_verdicts(
            raw_board_messages,
            raw_verdicts,
            all_symbols=all_symbols,
        )
    )
    return violations


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
                "plurality Accumulate Candidate (e.g. 2/5) cannot authorize a purchase."
            ),
        })

    if deterministic_violations:
        is_compliant = False
    elif llm_report:
        is_compliant = bool(llm.get("is_compliant"))
    else:
        is_compliant = True

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
