"""Deterministic Systems Architect QA pre-checks — chairman JSON, raw_verdicts, log bloat.

Python catches structural failures and debate-log bloat; the LLM is skipped on
deterministic PASS. On FAIL, a Flash LLM pass augments Python findings (see qa_augmentation).
"""
from __future__ import annotations

import re

from src.core.vote_engine import AGENT_KEYS

_CHAIRMAN_LIST_KEYS = ("portfolio_positions", "watchlist_positions")
_RAW_LOG_CHAR_LIMIT = 120_000
_SCRATCHPAD_CHAR_LIMIT = 25_000
_PASS_MENTION_PER_SYMBOL = 6
_MIN_SYMBOLS_FOR_PASS_SPAM = 12
_MIN_PASS_MENTIONS = 72
_WATCHLIST_PASS_RATE_THRESHOLD = 0.85
_MIN_WATCHLIST_VERDICT_ROWS = 50
_REPETITIVE_SYNTHESIS_MIN_LEN = 40
_REPETITIVE_SYNTHESIS_MIN_SYMBOLS = 4


def audit_chairman_structure(chairman: dict) -> list[str]:
    """Validate chairman allocation JSON shape and position rows."""
    if not chairman:
        return ["Chairman allocation JSON is empty."]

    violations: list[str] = []
    seen_symbols: list[str] = []

    for key in _CHAIRMAN_LIST_KEYS:
        val = chairman.get(key)
        if val is None:
            violations.append(f"CHAIRMAN SCHEMA: missing required key '{key}'.")
        elif not isinstance(val, list):
            violations.append(f"CHAIRMAN SCHEMA: '{key}' must be a list, got {type(val).__name__}.")

    for section in _CHAIRMAN_LIST_KEYS:
        for i, pos in enumerate(chairman.get(section) or []):
            if not isinstance(pos, dict):
                violations.append(f"CHAIRMAN SCHEMA: {section}[{i}] is not an object.")
                continue
            sym = (pos.get("symbol") or "").strip()
            label = sym or f"{section}[{i}]"
            if not sym:
                violations.append(f"CHAIRMAN SCHEMA: {section}[{i}] missing symbol.")
            elif sym in seen_symbols:
                violations.append(f"CHAIRMAN SCHEMA: duplicate symbol '{sym}' in chairman positions.")
            else:
                seen_symbols.append(sym)
            if not (pos.get("final_verdict") or "").strip():
                violations.append(f"CHAIRMAN SCHEMA: {label} missing final_verdict.")

    return violations


def audit_raw_verdicts_structure(raw_verdicts: dict | None) -> list[str]:
    if not raw_verdicts:
        return ["ARCHITECT: raw_verdicts missing from debate checkpoint."]

    violations: list[str] = []
    for agent_key in AGENT_KEYS:
        if agent_key not in raw_verdicts:
            violations.append(f"ARCHITECT: raw_verdicts missing panelist key '{agent_key}'.")
            continue
        if not isinstance(raw_verdicts[agent_key], dict):
            violations.append(f"ARCHITECT: raw_verdicts['{agent_key}'] is not an object.")
    return violations


def audit_repetitive_synthesis(chairman: dict) -> list[str]:
    """Flag copy-pasted synthesis/strategic_context across many positions."""
    by_text: dict[str, list[str]] = {}
    for section in _CHAIRMAN_LIST_KEYS:
        for pos in chairman.get(section) or []:
            if not isinstance(pos, dict):
                continue
            text = (pos.get("synthesis") or pos.get("strategic_context") or "").strip()
            if len(text) < _REPETITIVE_SYNTHESIS_MIN_LEN:
                continue
            sym = (pos.get("symbol") or "?").strip()
            by_text.setdefault(text, []).append(sym)

    violations: list[str] = []
    for text, symbols in by_text.items():
        if len(symbols) < _REPETITIVE_SYNTHESIS_MIN_SYMBOLS:
            continue
        preview = ", ".join(symbols[:5])
        if len(symbols) > 5:
            preview += "..."
        violations.append(
            f"REPETITIVE SYNTHESIS: {len(symbols)} positions share identical copy ({preview})."
        )
    return violations


def audit_scratchpad_bloat(chairman: dict) -> list[str]:
    scratch = (chairman or {}).get("chain_of_thought_scratchpad") or ""
    if len(scratch) > _SCRATCHPAD_CHAR_LIMIT:
        return [
            f"SCRATCHPAD BLOAT: chain_of_thought_scratchpad is {len(scratch):,} chars "
            f"(threshold {_SCRATCHPAD_CHAR_LIMIT:,})."
        ]
    return []


def audit_debate_log_bloat(raw_log: str, *, all_symbols: list[str]) -> list[str]:
    violations: list[str] = []
    log = raw_log or ""
    if len(log) > _RAW_LOG_CHAR_LIMIT:
        violations.append(
            f"DEBATE LOG BLOAT: raw log is {len(log):,} chars (threshold {_RAW_LOG_CHAR_LIMIT:,})."
        )

    symbol_count = len(all_symbols or [])
    pass_mentions = len(re.findall(r"\bPass\b", log, re.I))
    if (
        symbol_count >= _MIN_SYMBOLS_FOR_PASS_SPAM
        and pass_mentions >= _MIN_PASS_MENTIONS
        and pass_mentions >= symbol_count * _PASS_MENTION_PER_SYMBOL
    ):
        violations.append(
            f"DEBATE LOG BLOAT: debate log contains {pass_mentions} 'Pass' mentions "
            f"across {symbol_count} symbols — likely watchlist Pass spam."
        )
    return violations


def audit_watchlist_pass_spam(raw_verdicts: dict | None) -> list[str]:
    if not raw_verdicts:
        return []

    total = 0
    passes = 0
    for agent_key in AGENT_KEYS:
        for row in (raw_verdicts.get(agent_key) or {}).get("watchlist_verdicts") or []:
            total += 1
            verdict = (row.get("verdict") or "").upper()
            if "PASS" in verdict:
                passes += 1

    if total >= _MIN_WATCHLIST_VERDICT_ROWS and passes / total >= _WATCHLIST_PASS_RATE_THRESHOLD:
        return [
            f"DEBATE LOG BLOAT: {passes}/{total} watchlist verdict rows are Pass "
            f"(>{_WATCHLIST_PASS_RATE_THRESHOLD:.0%}) — slim Round 2 output for watchlist Pass rows."
        ]
    return []


def audit_system_architect_deterministic(
    chairman: dict,
    raw_log: str,
    raw_verdicts: dict | None,
    *,
    all_symbols: list[str],
) -> list[str]:
    """Return violation strings; empty means structural/log checks passed."""
    violations: list[str] = []
    violations.extend(audit_chairman_structure(chairman))
    violations.extend(audit_raw_verdicts_structure(raw_verdicts))
    violations.extend(audit_repetitive_synthesis(chairman))
    violations.extend(audit_scratchpad_bloat(chairman))
    violations.extend(audit_debate_log_bloat(raw_log, all_symbols=all_symbols))
    violations.extend(audit_watchlist_pass_spam(raw_verdicts))
    return violations


def format_architect_digest(violations: list[str]) -> str:
    lines = ["DETERMINISTIC SYSTEMS ARCHITECT PRE-CHECK:"]
    if not violations:
        lines.append(
            "Verdict: PASS — chairman JSON structure, raw_verdicts shape, and debate log size OK."
        )
        return "\n".join(lines)
    lines.append("Verdict: FAIL — structural or bloat issues detected:")
    for v in violations:
        lines.append(f"  - {v}")
    return "\n".join(lines)


def merge_architect_reports(deterministic_violations: list[str], llm_report: dict | None) -> dict:
    """Combine Python structural gate with optional Systems Architect LLM audit."""
    llm = llm_report or {}
    combined_findings = list(llm.get("findings") or [])

    for v in deterministic_violations:
        combined_findings.insert(0, {
            "severity": "CRITICAL",
            "category": "Pipeline / JSON",
            "description": v,
            "recommendation": (
                "Fix chairman JSON shape, deduplicate synthesis, or slim Round 2 watchlist Pass output."
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
        summary = f"Deterministic architect FAIL ({len(deterministic_violations)} issue(s)). {summary}"
    elif deterministic_violations:
        summary = f"Deterministic architect FAIL — {len(deterministic_violations)} issue(s) detected."
    elif not llm_report:
        summary = "Deterministic architect PASS — LLM audit skipped."

    return {
        "agent_role": llm.get("agent_role") or "Systems Architect QA",
        "is_compliant": is_compliant,
        "findings": combined_findings,
        "summary": summary or "Systems architect audit complete.",
    }
