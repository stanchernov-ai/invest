"""Deterministic State of the Union quotes from panel overall portfolio critiques."""
from __future__ import annotations

from src.core.agents import agent_config

PANELIST_KEYS = ("buffett", "lynch", "livermore", "huang", "simons")

BUY_VERDICTS = frozenset({"STRONG BUY", "BUY"})
SELL_VERDICTS = frozenset({"SELL", "TRIM", "STRONG SELL"})


def _stance_label(portfolio_verdicts: list[dict]) -> str:
    """Derive star rating + stance from Round 2 portfolio verdict weights."""
    net = 0
    for verdict_row in portfolio_verdicts or []:
        verdict = (verdict_row.get("verdict") or "").upper().strip()
        conviction = int(verdict_row.get("conviction_score") or 5)
        if verdict in BUY_VERDICTS:
            net += conviction
        elif verdict in SELL_VERDICTS:
            net -= conviction

    if net >= 15:
        return "(⭐⭐⭐⭐ Bullish)"
    if net >= 5:
        return "(⭐⭐⭐ Bullish)"
    if net <= -15:
        return "(⭐ Bearish)"
    if net <= -5:
        return "(⭐⭐ Bearish)"
    return "(⭐⭐ Neutral)"


def build_state_of_union_quotes(raw_verdicts: dict[str, dict]) -> list[dict]:
    """Build SoTU from each panelist's Round 2 overall_portfolio_critique (authoritative)."""
    quotes: list[dict] = []
    for agent_key in PANELIST_KEYS:
        data = raw_verdicts.get(agent_key) or {}
        critique = (data.get("overall_portfolio_critique") or "").strip()
        if not critique:
            critique = "No overall portfolio critique was recorded for this session."

        role = agent_config["board_members"][agent_key]["role"]
        stance = _stance_label(data.get("portfolio_verdicts") or [])
        quotes.append({
            "board_member": f"{role} {stance}",
            "quote": critique,
        })
    return quotes
