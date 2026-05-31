"""Deterministic State of the Union quotes from panel Round 1 portfolio overviews."""
from __future__ import annotations

import re

from src.core.board_roster import PANELIST_KEYS, PANELIST_ROLES

BUY_VERDICTS = frozenset({"HIGH CONVICTION (OVERWEIGHT)", "ACCUMULATE CANDIDATE"})
SELL_VERDICTS = frozenset({"BEARISH (LIQUIDATE)", "REDUCE EXPOSURE", "STRONG BEARISH (LIQUIDATE)"})

# Round 2 overall_portfolio_critique is peer rebuttal prose — not briefing SoTU material.
_REBUTTAL_OPENERS = re.compile(
    r"^\s*(i\s+(fundamentally\s+)?(dis)?agree|while\s+i\s+(dis)?agree|"
    r"i\s+must\s+(dis)?agree|i\s+partially\s+concede|davinci\s+is\s+right|hypatia\s+is\s+right|"
    r"leonardo\s+da\s+vinci\s+is\s+right)",
    re.I,
)
_TICKER_HEAVY = re.compile(r"\b[A-Z]{1,5}\b(?:\s*[:—-]\s|\s+(?:is|was|remains)\b)", re.M)


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


def _looks_like_rebuttal(text: str) -> bool:
    """Heuristic: Round 2 peer-rebuttal summary vs Round 1 portfolio overview."""
    if not text:
        return False
    if _REBUTTAL_OPENERS.search(text):
        return True
    # Many ALLCAPS tickers + rebuttal framing → per-stock fight, not portfolio view.
    tickers = _TICKER_HEAVY.findall(text)
    return len(tickers) >= 3


def _pick_sotu_quote(
    agent_key: str,
    raw_verdicts: dict[str, dict],
    round1_critiques: dict[str, str] | None,
) -> str:
    """Prefer Round 1 portfolio overview; never surface Round 2 rebuttal summaries in SoTU."""
    round1 = (round1_critiques or {}).get(agent_key, "").strip()
    if round1:
        return round1

    round2 = ((raw_verdicts.get(agent_key) or {}).get("overall_portfolio_critique") or "").strip()
    if round2 and not _looks_like_rebuttal(round2):
        return round2
    if round2:
        return (
            "Round 1 portfolio overview unavailable; Round 2 text was peer rebuttal only — "
            "re-run debate for a portfolio-level State of the Union quote."
        )
    return "No overall portfolio critique was recorded for this session."


def condense_sotu_quote(text: str, *, max_sentences: int = 2) -> str:
    """Reduce Exposure SoTU quotes for executive scan (1-2 sentences)."""
    text = (text or "").strip()
    if not text:
        return text
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if len(sentences) <= max_sentences:
        return text
    return " ".join(sentences[:max_sentences])


def build_state_of_union_quotes(
    raw_verdicts: dict[str, dict],
    *,
    round1_critiques: dict[str, str] | None = None,
) -> list[dict]:
    """Build SoTU from Round 1 overall_portfolio_critique; stance stars from Round 2 votes."""
    quotes: list[dict] = []
    for agent_key in PANELIST_KEYS:
        data = raw_verdicts.get(agent_key) or {}
        critique = _pick_sotu_quote(agent_key, raw_verdicts, round1_critiques)
        role = PANELIST_ROLES[agent_key]
        stance = _stance_label(data.get("portfolio_verdicts") or [])
        quotes.append({
            "board_member": f"{role} {stance}",
            "quote": condense_sotu_quote(critique),
        })
    return quotes
