"""Deterministic compliance checks on Chairman output — in-loop gate before deliver.

Mirrors Post Mortem QA hard rules (max buys, hedge execution) in Python so the
Compliance LLM focuses on debate-log alignment and funding logic.
"""
from __future__ import annotations

from src.core.guardrails import BUY_VERDICTS, MAX_DAILY_BUYS, _normalize_verdict

HEDGE_SYMBOLS = frozenset({"TLT", "VXX"})


def count_buy_verdicts(chairman: dict) -> int:
    """Count Buy/Strong Buy across portfolio and watchlist positions."""
    count = 0
    for section in ("portfolio_positions", "watchlist_positions"):
        for pos in chairman.get(section) or []:
            if _normalize_verdict(pos.get("final_verdict", "")) in BUY_VERDICTS:
                count += 1
    return count


def _hedge_in_targets(chairman: dict) -> bool:
    audit = chairman.get("capital_flow_audit") or {}
    targets = {str(s).upper() for s in (audit.get("target_tickers") or [])}
    return bool(targets & HEDGE_SYMBOLS)


def _hedge_buy_verdict(chairman: dict) -> bool:
    for section in ("portfolio_positions", "watchlist_positions"):
        for pos in chairman.get(section) or []:
            sym = str(pos.get("symbol", "")).upper()
            if sym in HEDGE_SYMBOLS and _normalize_verdict(pos.get("final_verdict", "")) in BUY_VERDICTS:
                return True
    return False


def _narrative_mentions_hedge(chairman: dict) -> bool:
    text = " ".join([
        chairman.get("chain_of_thought_scratchpad") or "",
        chairman.get("capital_allocation_narrative") or "",
        chairman.get("macro_view") or "",
    ]).upper()
    return any(k in text for k in (" HEDGE", "TLT", "VXX", "MANDATORY NON-CORRELATED"))


def audit_chairman_compliance(chairman: dict) -> list[str]:
    """Return human-readable violation strings; empty list means deterministic pass."""
    if not chairman:
        return ["Chairman output is empty."]

    violations: list[str] = []

    buy_count = count_buy_verdicts(chairman)
    if buy_count > MAX_DAILY_BUYS:
        symbols = []
        for section in ("portfolio_positions", "watchlist_positions"):
            for pos in chairman.get(section) or []:
                if _normalize_verdict(pos.get("final_verdict", "")) in BUY_VERDICTS:
                    symbols.append(pos.get("symbol", "?"))
        violations.append(
            f"MAX 3 BUYS: output contains {buy_count} Buy/Strong Buy verdicts "
            f"({', '.join(symbols)}) — limit is {MAX_DAILY_BUYS}."
        )

    hedge_executed = _hedge_in_targets(chairman) or _hedge_buy_verdict(chairman)
    if not hedge_executed:
        violations.append(
            "HEDGE MANDATE: TLT or VXX must appear in capital_flow_audit.target_tickers "
            "and/or as a Buy/Strong Buy position — mandatory hedge was not executed in JSON."
        )
    elif _narrative_mentions_hedge(chairman) and not _hedge_in_targets(chairman):
        violations.append(
            "HEDGE EXECUTION: scratchpad/narrative references a hedge purchase but "
            "capital_flow_audit.target_tickers does not include TLT or VXX."
        )

    audit = chairman.get("capital_flow_audit")
    if buy_count > 0 and not audit:
        violations.append(
            "CAPITAL FLOW: Buy verdicts present but capital_flow_audit is missing."
        )

    return violations


def format_debate_for_compliance(messages: list[dict], *, char_limit: int = 28000) -> str:
    """Extract Round 1 + Round 2 debate text for vote cross-check."""
    parts: list[str] = []
    for msg in messages or []:
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        if "[ROUND 1]" in content or "[ROUND 2" in content.upper():
            parts.append(content)
    text = "\n\n".join(parts)
    if len(text) > char_limit:
        return text[-char_limit:]
    return text


def format_compliance_digest(violations: list[str]) -> str:
    if not violations:
        return "DETERMINISTIC COMPLIANCE PRE-CHECK: PASS — max buys and hedge execution verified in JSON."
    lines = ["DETERMINISTIC COMPLIANCE PRE-CHECK: FAIL — fix these before resubmitting:"]
    for v in violations:
        lines.append(f"  - {v}")
    return "\n".join(lines)


def merge_compliance_reports(deterministic_violations: list[str], llm_report: dict | None) -> dict:
    """Combine Python gate with LLM compliance audit."""
    llm = llm_report or {}
    llm_violations = [str(v) for v in (llm.get("violations") or []) if v]
    combined = list(dict.fromkeys([*deterministic_violations, *llm_violations]))

    feedback_parts = []
    if deterministic_violations:
        feedback_parts.append(format_compliance_digest(deterministic_violations))
    llm_feedback = (llm.get("feedback_to_chairman") or "").strip()
    if llm_feedback:
        feedback_parts.append(llm_feedback)

    if deterministic_violations:
        is_compliant = False
    elif llm_report:
        is_compliant = bool(llm.get("is_compliant")) and not llm_violations
    else:
        is_compliant = False

    return {
        "is_compliant": is_compliant,
        "violations": combined,
        "feedback_to_chairman": "\n\n".join(feedback_parts) or "Compliance rejection — revise chairman output.",
    }
