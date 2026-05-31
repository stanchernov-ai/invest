"""Deterministic compliance checks on Chairman output — in-loop gate before deliver.

Mirrors Post Mortem QA hard rules (max buys, hedge execution) in Python so the
Compliance LLM focuses on debate-log alignment and funding logic.
"""
from __future__ import annotations

import re

from src.core.guardrails import (
    BUY_VERDICTS,
    HEDGE_SYMBOLS,
    MAX_DAILY_BUYS,
    _is_hedge_symbol,
    _normalize_verdict,
    count_equity_buys,
)
from src.core.vote_engine import (
    MAJORITY_THRESHOLD,
    build_vote_summaries,
    is_funding_sell_override,
    mandate_verdict,
    verdict_bucket,
)

_SYSTEM_MAX_BUY_OVERRIDE = "[SYSTEM OVERRIDE: Maximum"
_SYSTEM_VOTE_ENGINE = "[VOTE ENGINE]"


def count_buy_verdicts(chairman: dict) -> int:
    """Count Accumulate Candidate/High Conviction (Overweight) across portfolio and watchlist positions."""
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


def _chairman_aligns_with_mandate(final_verdict: str, expected_mandate: str) -> bool:
    final = _normalize_verdict(final_verdict)
    expected = _normalize_verdict(expected_mandate)
    if final == expected:
        return True
    if expected in BUY_VERDICTS and final in BUY_VERDICTS:
        return True
    if expected in ("BEARISH (LIQUIDATE)", "EXTREME BEARISH (LIQUIDATE)", "REDUCE EXPOSURE") and final in ("BEARISH (LIQUIDATE)", "EXTREME BEARISH (LIQUIDATE)", "REDUCE EXPOSURE"):
        return True
    if expected == "HOLD" and final == "HOLD":
        return True
    if expected == "PASS" and final == "PASS":
        return True
    return False


def _is_surplus_majority_buy_demotion(
    pos: dict,
    summary,
    chairman: dict,
    majority_bucket: str,
) -> bool:
    """Pass/Hold on a 3/5 buy-side when max equity buy slots are already filled."""
    if summary.buy_side_count() < MAJORITY_THRESHOLD:
        return False
    if _normalize_verdict(pos.get("final_verdict", "")) in BUY_VERDICTS:
        return False
    return count_equity_buys(chairman) >= MAX_DAILY_BUYS


def _has_valid_majority_override(pos: dict, majority_bucket: str) -> bool:
    syn = pos.get("synthesis") or ""
    if _SYSTEM_MAX_BUY_OVERRIDE in syn or _SYSTEM_VOTE_ENGINE in syn:
        return True
    if "SYSTEM OVERRIDE" in syn and majority_bucket == "buy":
        return True
    return False


def audit_chairman_vote_alignment(
    chairman: dict,
    raw_verdicts: dict[str, dict] | None,
    *,
    all_symbols: list[str] | None = None,
    portfolio_symbols: set[str] | None = None,
) -> list[str]:
    """Python checks for compliance checklist A, D, E (majority, originator, alpha pick)."""
    if not chairman or not raw_verdicts:
        return []

    portfolio_symbols = portfolio_symbols or set()
    symbols = all_symbols or []
    for section in ("portfolio_positions", "watchlist_positions"):
        for pos in chairman.get(section) or []:
            sym = (pos.get("symbol") or "").strip()
            if sym and sym not in symbols:
                symbols.append(sym)

    summaries = build_vote_summaries(raw_verdicts, symbols, portfolio_symbols=portfolio_symbols)
    violations: list[str] = []

    for section in ("portfolio_positions", "watchlist_positions"):
        for pos in chairman.get(section) or []:
            sym = (pos.get("symbol") or "").strip()
            if not sym:
                continue
            summary = summaries.get(sym)
            if not summary:
                continue
            expected = mandate_verdict(summary)
            final = pos.get("final_verdict", "")
            mb = "buy" if summary.buy_side_count() >= MAJORITY_THRESHOLD else (
                "reduce" if summary.sell_side_count() >= MAJORITY_THRESHOLD else None
            )
            if _has_valid_majority_override(pos, mb or ""):
                continue
            if is_funding_sell_override(pos):
                continue
            if _is_surplus_majority_buy_demotion(pos, summary, chairman, mb or ""):
                continue
            if not _chairman_aligns_with_mandate(final, expected):
                violations.append(
                    f"MAJORITY VOTE ALIGNMENT: {sym} board mandate is {expected} "
                    f"(buy_side={summary.buy_side_count()}/5, sell_side={summary.sell_side_count()}/5) "
                    f"but chairman final_verdict is {final}."
                )

    for section in ("portfolio_positions", "watchlist_positions"):
        for pos in chairman.get(section) or []:
            sym = (pos.get("symbol") or "").strip()
            if not sym or _is_hedge_symbol(sym):
                continue
            if _normalize_verdict(pos.get("final_verdict", "")) not in BUY_VERDICTS:
                continue
            summary = summaries.get(sym)
            if not summary:
                violations.append(
                    f"ORIGINATOR RULE: {sym} is Accumulate Candidate/High Conviction (Overweight) in chairman JSON but has no Round 2 panel votes."
                )
                continue
            buy_votes = summary.buy_side_count()
            if buy_votes < MAJORITY_THRESHOLD:
                violations.append(
                    f"MAJORITY ACCUMULATE CANDIDATE MANDATE: {sym} chairman Accumulate Candidate/High Conviction (Overweight) requires "
                    f"{MAJORITY_THRESHOLD}/5 panel Accumulate Candidate votes but only {buy_votes}/5 voted Accumulate Candidate "
                    f"(plurality is not a majority)."
                )

    alpha = chairman.get("alpha_pick") or {}
    alpha_sym = (alpha.get("symbol") or "").strip()
    any_majority_buy = any(
        s.buy_side_count() >= MAJORITY_THRESHOLD for s in summaries.values()
    )
    if alpha_sym and any_majority_buy:
        alpha_summary = summaries.get(alpha_sym)
        if not alpha_summary:
            violations.append(
                f"ALPHA PICK: {alpha_sym} has no Round 2 panel votes."
            )
        elif alpha_summary.buy_side_count() < MAJORITY_THRESHOLD:
            violations.append(
                f"ALPHA PICK: {alpha_sym} requires majority Accumulate Candidate support "
                f"({alpha_summary.buy_side_count()}/{MAJORITY_THRESHOLD} panelists)."
            )

    return violations


def audit_chairman_compliance(
    chairman: dict,
    raw_verdicts: dict[str, dict] | None = None,
    *,
    all_symbols: list[str] | None = None,
    portfolio_symbols: set[str] | None = None,
) -> list[str]:
    """Return human-readable violation strings; empty list means deterministic pass."""
    violations = audit_chairman_compliance_limits(chairman)
    violations.extend(
        audit_chairman_vote_alignment(
            chairman,
            raw_verdicts,
            all_symbols=all_symbols,
            portfolio_symbols=portfolio_symbols,
        )
    )
    return violations


def audit_chairman_compliance_limits(chairman: dict) -> list[str]:
    """Max buys, hedge mandate, capital flow presence."""
    if not chairman:
        return ["Chairman output is empty."]

    violations: list[str] = []

    buy_count = count_equity_buys(chairman)
    if buy_count > MAX_DAILY_BUYS:
        symbols = []
        for section in ("portfolio_positions", "watchlist_positions"):
            for pos in chairman.get(section) or []:
                sym = pos.get("symbol", "?")
                if _is_hedge_symbol(sym):
                    continue
                if _normalize_verdict(pos.get("final_verdict", "")) in BUY_VERDICTS:
                    symbols.append(sym)
        violations.append(
            f"MAX 3 BUYS: output contains {buy_count} equity Accumulate Candidate/High Conviction (Overweight) verdicts "
            f"({', '.join(symbols)}) — limit is {MAX_DAILY_BUYS} (TLT/VXX hedge excluded)."
        )

    hedge_executed = _hedge_in_targets(chairman) or _hedge_buy_verdict(chairman)
    if not hedge_executed:
        violations.append(
            "HEDGE MANDATE: TLT or VXX must appear in capital_flow_audit.target_tickers "
            "and/or as a Accumulate Candidate/High Conviction (Overweight) position — mandatory hedge was not executed in JSON."
        )
    elif _narrative_mentions_hedge(chairman) and not _hedge_in_targets(chairman):
        violations.append(
            "HEDGE EXECUTION: scratchpad/narrative references a hedge purchase but "
            "capital_flow_audit.target_tickers does not include TLT or VXX."
        )

    audit = chairman.get("capital_flow_audit")
    if buy_count > 0 and not audit:
        violations.append(
            "CAPITAL FLOW: Accumulate Candidate verdicts present but capital_flow_audit is missing."
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
        return "DETERMINISTIC COMPLIANCE PRE-CHECK: PASS — max buys, hedge, majority alignment, originator, and alpha pick verified."
    lines = ["DETERMINISTIC COMPLIANCE PRE-CHECK: FAIL — fix these before resubmitting:"]
    for v in violations:
        lines.append(f"  - {v}")
    return "\n".join(lines)


def format_compliance_failure_summary(
    *,
    violations: list[str],
    feedback: str = "",
    attempts: int = 0,
    chairman_empty: bool = False,
) -> str:
    """Human-readable summary for logs, run_status, and failure emails."""
    lines = [
        "Compliance gate rejected chairman output after debate (single pass — no retry).",
        "Flagged for prompt engineering and data quality expert review.",
    ]
    if chairman_empty:
        lines.append("Chairman produced no approved allocation JSON.")
    if violations:
        lines.append("Violations:")
        lines.extend(f"  - {v}" for v in violations)
    feedback = (feedback or "").strip()
    if feedback:
        lines.append(f"Feedback to chairman:\n{feedback}")
    return "\n".join(lines)


def _find_chairman_position(chairman: dict, symbol: str) -> dict | None:
    for section in ("portfolio_positions", "watchlist_positions"):
        for pos in chairman.get(section) or []:
            if (pos.get("symbol") or "").upper() == (symbol or "").upper():
                return pos
    return None


def _symbol_from_majority_violation(violation: str) -> str | None:
    """Best-effort parse e.g. '... for AMZN is non-compliant'."""
    match = re.search(r"\bfor\s+([A-Z][A-Z0-9.\-]{0,9})\b", violation, re.IGNORECASE)
    return match.group(1).upper() if match else None


def filter_spurious_majority_violations(
    violations: list[str],
    chairman: dict,
) -> list[str]:
    """Drop LLM majority-alignment noise for valid SYSTEM OVERRIDE max-buy demotions."""
    kept: list[str] = []
    for violation in violations:
        text = violation or ""
        upper = text.upper()
        if "MAJORITY VOTE" not in upper and "MAJORITY VOTE ALIGNMENT" not in upper:
            kept.append(violation)
            continue
        sym = _symbol_from_majority_violation(text)
        if sym:
            pos = _find_chairman_position(chairman, sym)
            if pos:
                if _SYSTEM_MAX_BUY_OVERRIDE in (pos.get("synthesis") or ""):
                    continue
                if _normalize_verdict(pos.get("final_verdict", "")) in BUY_VERDICTS:
                    continue
        kept.append(violation)
    return kept


def merge_compliance_reports(
    deterministic_violations: list[str],
    llm_report: dict | None,
    *,
    chairman: dict | None = None,
) -> dict:
    """Combine Python gate with LLM compliance audit."""
    llm = llm_report or {}
    llm_violations = [str(v) for v in (llm.get("violations") or []) if v]
    if chairman:
        llm_violations = filter_spurious_majority_violations(llm_violations, chairman)
    combined = list(dict.fromkeys([*deterministic_violations, *llm_violations]))

    feedback_parts = []
    if deterministic_violations:
        feedback_parts.append(format_compliance_digest(deterministic_violations))
    llm_feedback = (llm.get("feedback_to_chairman") or "").strip()
    if llm_feedback:
        feedback_parts.append(llm_feedback)

    # Evidence-based gate: filtered violations are authoritative (same pattern as QA reconcile).
    is_compliant = len(combined) == 0

    return {
        "is_compliant": is_compliant,
        "violations": combined,
        "feedback_to_chairman": "\n\n".join(feedback_parts) or "Compliance rejection — revise chairman output.",
    }
