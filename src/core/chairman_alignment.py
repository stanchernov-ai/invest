"""Chairman ↔ board majority coherence (deterministic).

Fixes cases like run 20260529_134042: board majority Buy on AMZN while the
chairman JSON says Pass citing a false "Maximum 3 Buys" excuse when only two
equity buys were executed.
"""
from __future__ import annotations

import re

from src.core.guardrails import (
    BUY_VERDICTS,
    MAX_DAILY_BUYS,
    _is_hedge_symbol,
    _normalize_verdict,
    _prepend_override,
    count_equity_buys,
)

PANEL_MAJORITY_THRESHOLD = 3  # 3 of 5 panelists

_SYSTEM_MAX_BUY_OVERRIDE = "[SYSTEM OVERRIDE: Maximum"
_FALSE_MAX_BUY_PATTERNS = re.compile(
    r"(maximum\s+3\s+buys?|max(?:imum)?\s+3\s+buys?|maximum\s+three\s+buys?)",
    re.IGNORECASE,
)


def board_majority_buy_counts(raw_verdicts: dict[str, dict] | None) -> dict[str, int]:
    """Round 2 panel votes: symbol -> count of Buy/Strong Buy."""
    counts: dict[str, int] = {}
    if not raw_verdicts:
        return counts
    for agent_data in raw_verdicts.values():
        if not agent_data:
            continue
        for bucket in ("portfolio_verdicts", "watchlist_verdicts"):
            for verdict in agent_data.get(bucket) or []:
                sym = (verdict.get("symbol") or "").strip()
                if not sym:
                    continue
                if _normalize_verdict(verdict.get("verdict", "")) in BUY_VERDICTS:
                    counts[sym] = counts.get(sym, 0) + 1
    return counts


def _has_system_max_buy_override(synthesis: str) -> bool:
    return _SYSTEM_MAX_BUY_OVERRIDE in (synthesis or "")


def _cites_false_max_buy_cap(synthesis: str) -> bool:
    if _has_system_max_buy_override(synthesis):
        return False
    return bool(_FALSE_MAX_BUY_PATTERNS.search(synthesis or ""))


def _strip_false_max_buy_phrases(synthesis: str) -> str:
    text = _FALSE_MAX_BUY_PATTERNS.sub("", synthesis or "")
    return " ".join(text.split())


def reconcile_false_max_buy_narratives(chairman: dict) -> dict:
    """When equity buys are under the cap, remove chairman-authored false max-3 claims."""
    equity_buys = count_equity_buys(chairman)
    if equity_buys >= MAX_DAILY_BUYS:
        return chairman

    for section in ("portfolio_positions", "watchlist_positions"):
        for pos in chairman.get(section) or []:
            if _normalize_verdict(pos.get("final_verdict", "")) in BUY_VERDICTS:
                continue
            syn = pos.get("synthesis") or ""
            if not _cites_false_max_buy_cap(syn):
                continue
            cleaned = _strip_false_max_buy_phrases(syn).strip()
            note = (
                f"[SYSTEM NOTE: Only {equity_buys}/{MAX_DAILY_BUYS} equity buys executed — "
                f"the max-buy cap does not apply to this position.]"
            )
            pos["synthesis"] = f"{note} {cleaned}".strip() if cleaned else note
    return chairman


def fill_majority_buys_within_cap(chairman: dict, raw_verdicts: dict[str, dict] | None) -> dict:
    """Promote board majority Buys into open equity buy slots (after enforce_max_buys)."""
    if not raw_verdicts:
        return chairman

    majority_counts = board_majority_buy_counts(raw_verdicts)
    candidates: list[tuple[int, int, dict]] = []

    for section in ("portfolio_positions", "watchlist_positions"):
        for pos in chairman.get(section) or []:
            sym = (pos.get("symbol") or "").strip()
            if not sym or _is_hedge_symbol(sym):
                continue
            panel_votes = majority_counts.get(sym, 0)
            if panel_votes < PANEL_MAJORITY_THRESHOLD:
                continue
            if _normalize_verdict(pos.get("final_verdict", "")) in BUY_VERDICTS:
                continue
            if _has_system_max_buy_override(pos.get("synthesis", "")):
                continue
            candidates.append((
                int(pos.get("aggregate_conviction_score") or 0),
                panel_votes,
                pos,
            ))

    candidates.sort(key=lambda item: (-item[0], -item[1], item[2].get("symbol", "")))

    audit = chairman.get("capital_flow_audit")
    if not audit:
        chairman["capital_flow_audit"] = audit = {"liquidated_tickers": [], "target_tickers": []}
    targets = list(audit.get("target_tickers") or [])

    for conviction, panel_votes, pos in candidates:
        if count_equity_buys(chairman) >= MAX_DAILY_BUYS:
            break
        sym = pos["symbol"]
        slot = count_equity_buys(chairman) + 1
        pos["final_verdict"] = "Buy"
        _prepend_override(
            pos,
            f"[SYSTEM OVERRIDE: Board majority Buy ({panel_votes}/5 panelists, "
            f"conviction {conviction}). Slot {slot}/{MAX_DAILY_BUYS}.]",
        )
        if sym not in targets:
            targets.append(sym)
        audit["target_tickers"] = targets

    return chairman


def apply_board_and_cap_coherence(
    chairman: dict,
    raw_verdicts: dict[str, dict] | None = None,
) -> dict:
    """Run after enforce_max_buys / before wash-sale and liquidation cap."""
    if raw_verdicts:
        fill_majority_buys_within_cap(chairman, raw_verdicts)
    reconcile_false_max_buy_narratives(chairman)
    return chairman
