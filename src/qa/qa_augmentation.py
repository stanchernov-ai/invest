"""When post-flight QA agents invoke Gemini vs stay on Python-only paths.

Policy: improve agent value with targeted LLM passes — do not treat deterministic
PASS as a broken or idle agent.
"""
from __future__ import annotations

from src.qa.persona_audit import MIN_TICKERS_FOR_UNANIMITY, UNANIMOUS_TICKER_RATE_THRESHOLD

# Persona: LLM only on borderline unanimous PASS — not on deterministic FAIL (B2).
# Band [PERSONA_BORDERLINE_UNANIMOUS_RATE, UNANIMOUS_TICKER_RATE_THRESHOLD).
PERSONA_BORDERLINE_UNANIMOUS_RATE = 0.52

EXECUTION_MODES = frozenset({
    "deterministic_pass",
    "deterministic_fail",
    "llm_fail",
    "llm_borderline",
    "llm_spot_check",
    "vote_engine",
    "python_gate",
    "infra",
    "on_demand",
    "llm_active",
})

# agent_role (display) -> config key for QA_EXECUTION telemetry
ROLE_TO_AGENT_KEY: dict[str, str] = {
    "Post Mortem QA Auditor": "post_mortem_qa",
    "Systems Architect QA": "system_architect",
    "Prompt Engineer QA": "prompt_engineer",
    "Graphics Designer Visual SME": "graphics_designer_qa",
    "QA Integrity Auditor": "qa_integrity_auditor",
    "Legal Counsel QA": "legal_counsel_qa",
    "Legal Counsel QA (Codebase)": "legal_counsel_code",
}


def should_augment_persona_llm(violations: list[str], stats: dict) -> bool:
    """Run Prompt Engineer LLM on borderline unanimous PASS only — skip when Python already FAIL."""
    if violations:
        return False
    total = stats.get("total_tickers", 0) or 0
    if total < MIN_TICKERS_FOR_UNANIMITY:
        return False
    rate = stats.get("unanimous_rate", 0) or 0
    return PERSONA_BORDERLINE_UNANIMOUS_RATE <= rate < UNANIMOUS_TICKER_RATE_THRESHOLD


def should_augment_architect_llm(violations: list[str]) -> bool:
    """Systems Architect stays on deterministic Python gate only (no LLM on FAIL)."""
    return False


def should_augment_post_mortem_spot(
    chairman: dict,
    drift_warnings: list[str],
) -> bool:
    """Lightweight LLM spot-check on procedural PASS (drift hints or vote-engine day)."""
    if drift_warnings:
        return True
    scratch = (chairman or {}).get("chain_of_thought_scratchpad") or ""
    return "PYTHON VOTE ENGINE" in scratch or "VOTE ENGINE ALLOCATION" in scratch


def collect_post_mortem_drift_warnings(
    chairman: dict,
    raw_verdicts: dict | None,
    raw_board_messages: list[dict] | None,
    *,
    all_symbols: list[str],
    portfolio_symbols: set[str] | None,
) -> list[str]:
    """Non-blocking procedural cross-checks (scratchpad vs SSOT, prose vs JSON)."""
    from src.qa.post_mortem_audit import (
        audit_debate_prose_vs_raw_verdicts,
        audit_scratchpad_digest_consistency,
    )

    warnings: list[str] = []
    warnings.extend(
        audit_scratchpad_digest_consistency(
            chairman,
            raw_verdicts,
            all_symbols=all_symbols,
            portfolio_symbols=portfolio_symbols,
        )
    )
    warnings.extend(
        audit_debate_prose_vs_raw_verdicts(
            raw_board_messages,
            raw_verdicts,
            all_symbols=all_symbols,
        )
    )
    return warnings


def extract_qa_execution(qa_reports: list[dict]) -> dict[str, str]:
    """Map agent config keys -> execution_mode for HR / telemetry consumers."""
    out: dict[str, str] = {}
    for report in qa_reports or []:
        mode = report.get("execution_mode")
        if not mode:
            continue
        key = report.get("agent_key")
        if not key:
            role = report.get("agent_role") or ""
            key = ROLE_TO_AGENT_KEY.get(role, "")
        if key:
            out[key] = mode
    return out


def execution_mode_display(mode: str) -> str:
    """Short label for utilization tables."""
    labels = {
        "deterministic_pass": "DET_PASS",
        "deterministic_fail": "DET_FAIL",
        "llm_fail": "LLM (FAIL)",
        "llm_borderline": "LLM (BORDERLINE)",
        "llm_spot_check": "LLM (SPOT)",
        "llm_active": "LLM_OK",
        "vote_engine": "VOTE_ENGINE",
        "python_gate": "PYTHON_GATE",
        "infra": "INFRA",
        "on_demand": "ON_DEMAND",
    }
    return labels.get(mode, mode.upper() if mode else "NOT_INVOKED")
