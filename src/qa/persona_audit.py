"""Deterministic persona / sycophancy pre-checks for Prompt Engineer QA.

Python catches unanimous-vote collapse and forbidden cross-persona vocabulary;
the LLM focuses on nuanced drift, chairman scratchpad fidelity, and dissent quality.
"""
from __future__ import annotations

import re

from src.core.board_roster import PANELIST_ROLES

PANELIST_MARKERS = PANELIST_ROLES

# Round-2 text must not lean on another agent's core vocabulary (case-insensitive).
FORBIDDEN_PHRASES: dict[str, tuple[str, ...]] = {
    "suntzu": (
        "p/e",
        "pe ratio",
        "price-to-earnings",
        "price to earnings",
        "margin of safety",
        "intrinsic value",
        "free cash flow",
        "return on equity",
    ),
    "hypatia": (
        "3m trend",
        "relative strength",
        "the tape",
        "momentum breakout",
        "breakout",
        "rising scale",
    ),
    "aurelius": (
        "economic moat",
        "margin of safety",
        "story stock",
        "secular narrative",
    ),
}

UNANIMOUS_TICKER_RATE_THRESHOLD = 0.60
MIN_TICKERS_FOR_UNANIMITY = 3


def _verdict_bucket(verdict: str) -> str:
    v = (verdict or "").upper()
    if "BUY" in v:
        return "buy"
    if "SELL" in v or "TRIM" in v:
        return "reduce"
    if "PASS" in v:
        return "pass"
    return "hold"


def _extract_round2_text(messages: list[dict], agent_key: str) -> str:
    from src.core.rebuttal import extract_panelist_round2_block
    return extract_panelist_round2_block(messages, agent_key)


def _unanimous_ticker_stats(matrix: dict) -> dict:
    """Return unanimous-rate stats from the Round 2 vote matrix."""
    total = 0
    unanimous = 0
    for votes in (matrix or {}).values():
        vals = [v for v in votes.values() if v]
        if len(vals) < 3:
            continue
        total += 1
        buckets = {_verdict_bucket(v) for v in vals}
        if len(buckets) == 1 and len(vals) >= 4:
            unanimous += 1
    rate = (unanimous / total) if total else 0.0
    return {"total_tickers": total, "unanimous_tickers": unanimous, "unanimous_rate": rate}


def _scan_forbidden_phrases(agent_key: str, text: str) -> list[str]:
    if not text:
        return []
    lower = text.lower()
    hits: list[str] = []
    for phrase in FORBIDDEN_PHRASES.get(agent_key, ()):
        if phrase in lower:
            hits.append(phrase)
    return hits


def audit_debate_persona(raw_messages: list[dict], all_symbols: list[str]) -> tuple[list[str], dict]:
    """Return (violation strings, stats dict) for the debate transcript."""
    from src.core.rebuttal import extract_panelist_round2_block, extract_round_overview, is_verbatim_r1_copy
    from src.qa_pipeline import parse_board_matrix

    violations: list[str] = []
    matrix = parse_board_matrix(raw_messages or [], all_symbols or [])
    stats = _unanimous_ticker_stats(matrix)
    stats["persona_keyword_hits"] = {}
    stats["verbatim_r1_copies"] = []

    if stats["total_tickers"] >= MIN_TICKERS_FOR_UNANIMITY:
        if stats["unanimous_rate"] >= UNANIMOUS_TICKER_RATE_THRESHOLD:
            violations.append(
                f"SYCOPHANCY / DEBATE COLLAPSE: {stats['unanimous_tickers']}/{stats['total_tickers']} "
                f"tickers ({stats['unanimous_rate']:.0%}) show 4+ panelists with identical Round 2 verdict "
                f"buckets — consensus without dissent is a failed debate."
            )

    for agent_key, marker in PANELIST_MARKERS.items():
        r1 = extract_round_overview(raw_messages, agent_key, "1")
        r2 = extract_round_overview(raw_messages, agent_key, "2")
        if is_verbatim_r1_copy(r1, r2):
            stats["verbatim_r1_copies"].append(agent_key)
            violations.append(
                f"VERBATIM R1 COPY ({marker}): Round 2 rebuttal summary duplicates Round 1 Portfolio Overview — "
                f"debate logging failure; Prompt Engineer must FAIL."
            )

        round2 = _extract_round2_text(raw_messages, agent_key)
        hits = _scan_forbidden_phrases(agent_key, round2)
        if hits:
            stats["persona_keyword_hits"][agent_key] = hits
            evidence = ""
            lower = round2.lower()
            for phrase in hits:
                idx = lower.find(phrase)
                if idx >= 0:
                    start = max(0, idx - 40)
                    end = min(len(round2), idx + len(phrase) + 60)
                    evidence = round2[start:end].replace("\n", " ").strip()
                    break
            snippet = f' Evidence: "...{evidence}..."' if evidence else ""
            violations.append(
                f"PERSONA DRIFT ({marker}): Round 2 rebuttal uses forbidden vocabulary for this persona: "
                f"{', '.join(repr(h) for h in hits)}.{snippet}"
            )

    return violations, stats


def format_persona_digest(violations: list[str], stats: dict) -> str:
    lines = [
        "DETERMINISTIC PERSONA PRE-CHECK:",
        f"  Round-2 matrix: {stats.get('total_tickers', 0)} tickers scored; "
        f"{stats.get('unanimous_tickers', 0)} with 4+ identical verdict buckets "
        f"({stats.get('unanimous_rate', 0):.0%} unanimous rate; threshold {UNANIMOUS_TICKER_RATE_THRESHOLD:.0%}).",
    ]
    keyword_hits = stats.get("persona_keyword_hits") or {}
    if keyword_hits:
        for agent, hits in keyword_hits.items():
            lines.append(f"  {PANELIST_MARKERS.get(agent, agent)} forbidden phrases: {', '.join(hits)}")
    else:
        lines.append("  Forbidden cross-persona vocabulary: none detected in Round 2.")
    verbatim = stats.get("verbatim_r1_copies") or []
    if verbatim:
        names = ", ".join(PANELIST_MARKERS.get(k, k) for k in verbatim)
        lines.append(f"  Verbatim R1 copies in Round 2: {names}")
    else:
        lines.append("  Verbatim R1 copies in Round 2: none detected.")
    if not violations:
        lines.append("  Verdict: PASS — no deterministic persona collapse detected.")
        return "\n".join(lines)
    lines.append("  Verdict: FAIL — address these before claiming behavioral compliance:")
    for v in violations:
        lines.append(f"    - {v}")
    return "\n".join(lines)


def merge_persona_reports(deterministic_violations: list[str], llm_report: dict | None) -> dict:
    """Combine Python gate with LLM persona audit."""
    llm = llm_report or {}
    llm_findings = list(llm.get("findings") or [])
    combined_findings = list(llm_findings)

    for v in deterministic_violations:
        combined_findings.insert(0, {
            "severity": "CRITICAL",
            "category": "Persona Drift",
            "description": v,
            "recommendation": "Tighten agent system prompts or META_DIRECTIVE enforcement; require dissent in Round 2.",
        })

    if deterministic_violations:
        is_compliant = False
    elif llm_report:
        is_compliant = bool(llm.get("is_compliant"))
    else:
        is_compliant = True

    summary = (llm.get("summary") or "").strip()
    if deterministic_violations and summary:
        summary = f"Deterministic persona FAIL ({len(deterministic_violations)} issue(s)). {summary}"
    elif deterministic_violations:
        summary = f"Deterministic persona FAIL — {len(deterministic_violations)} issue(s) detected."

    return {
        "agent_role": llm.get("agent_role") or "Prompt Engineer QA",
        "is_compliant": is_compliant,
        "findings": combined_findings,
        "summary": summary or "Persona audit complete.",
    }


def sanitize_rubber_stamp_pass(report: dict) -> dict:
    """Reject PASS verdicts that only contain INFO praise with no substantive findings."""
    if (report.get("agent_role") or "").strip() != "Prompt Engineer QA":
        return report
    if not report.get("is_compliant"):
        return report

    findings = report.get("findings") or []
    has_substance = any(
        str(f.get("severity", "")).upper() in ("WARNING", "CRITICAL")
        for f in findings
    )
    if has_substance:
        return report

    report = dict(report)
    report["is_compliant"] = False
    report["findings"] = list(findings) + [{
        "severity": "CRITICAL",
        "category": "Rubber Stamp",
        "description": (
            "Prompt Engineer QA self-reported PASS with no WARNING or CRITICAL findings — "
            "this is a rubber-stamp verdict. A contrarian persona audit must cite per-agent "
            "Round 2 evidence or flag at least one behavioral defect."
        ),
        "recommendation": "Re-audit with distinct quotes per panelist; downgrade to FAIL if debate collapsed.",
    }]
    summary = (report.get("summary") or "").strip()
    report["summary"] = f"Rubber-stamp PASS rejected. {summary}".strip()
    return report
