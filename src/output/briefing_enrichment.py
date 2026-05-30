"""Enrich investor-facing briefing copy from Round 2 panel JSON (render-time only)."""
from __future__ import annotations

import re

from src.core.vote_engine import (
    AGENT_DISPLAY,
    BUY_VERDICTS,
    panel_verdict_side,
    _normalize_verdict,
)

_DISPLAY_TO_AGENT = {name: key for key, name in AGENT_DISPLAY.items()}

_GENERIC_SYNTHESIS_MARKERS = (
    "consensus mandate from today's panel vote",
    "investment committee finalized this position",
)


def _iter_symbol_rows(raw_verdicts: dict[str, dict] | None):
    if not raw_verdicts:
        return
    for agent_key, agent_data in raw_verdicts.items():
        if not agent_data:
            continue
        for bucket in ("portfolio_verdicts", "watchlist_verdicts"):
            section = "portfolio" if bucket == "portfolio_verdicts" else "watchlist"
            for row in agent_data.get(bucket) or []:
                sym = (row.get("symbol") or "").strip()
                if not sym:
                    continue
                yield {
                    "agent_key": agent_key,
                    "display_name": AGENT_DISPLAY.get(agent_key, agent_key),
                    "symbol": sym,
                    "section": section,
                    "verdict": row.get("verdict", ""),
                    "analysis": (row.get("analysis") or "").strip(),
                    "conviction": int(row.get("conviction_score") or 0),
                }


def _symbol_rows(raw_verdicts: dict[str, dict] | None, symbol: str) -> list[dict]:
    sym = symbol.strip().upper()
    return [r for r in _iter_symbol_rows(raw_verdicts) if r["symbol"].upper() == sym]


def _agent_keys_for_names(names: list[str]) -> list[str]:
    keys: list[str] = []
    for name in names:
        key = _DISPLAY_TO_AGENT.get(name)
        if key:
            keys.append(key)
    return keys


def _side_matches_final(side: str, final_verdict: str, section: str) -> bool:
    final = _normalize_verdict(final_verdict)
    if final in BUY_VERDICTS:
        return side == "buy"
    if final in ("STRONG SELL", "SELL", "TRIM"):
        return side == "sell"
    if final == "PASS":
        return side == "pass"
    if final == "HOLD":
        return side == "neutral"
    return False


def _side_opposes_final(side: str, final_verdict: str, section: str) -> bool:
    final = _normalize_verdict(final_verdict)
    if final in BUY_VERDICTS:
        return side == "sell"
    if final in ("STRONG SELL", "SELL", "TRIM"):
        return side == "buy"
    if final == "PASS":
        return side == "buy"
    if final == "HOLD":
        return side in ("buy", "sell")
    return False


def _pick_champion_row(
    rows: list[dict],
    *,
    preferred_agents: list[str],
    final_verdict: str,
) -> dict | None:
    if not rows:
        return None
    section = rows[0]["section"]
    candidates = [r for r in rows if r["analysis"]]
    if not candidates:
        return None

    preferred = set(preferred_agents)
    if preferred:
        preferred_rows = [r for r in candidates if r["agent_key"] in preferred]
        if preferred_rows:
            return max(preferred_rows, key=lambda r: r["conviction"])

    def _rank(row: dict) -> tuple[int, int]:
        side = panel_verdict_side(row["verdict"], section)
        aligned = 1 if _side_matches_final(side, final_verdict, section) else 0
        return (aligned, row["conviction"])

    return max(candidates, key=_rank)


def _pick_dissenter_row(
    rows: list[dict],
    *,
    champion_key: str | None,
    final_verdict: str,
) -> dict | None:
    if not rows:
        return None
    section = rows[0]["section"]
    candidates = [
        r for r in rows
        if r["analysis"] and r["agent_key"] != champion_key
    ]
    opposing = [
        r for r in candidates
        if _side_opposes_final(panel_verdict_side(r["verdict"], section), final_verdict, section)
    ]
    pool = opposing or candidates
    if not pool:
        return None
    return max(pool, key=lambda r: r["conviction"])


def _is_generic_synthesis(text: str) -> bool:
    lowered = (text or "").lower()
    if not lowered:
        return True
    return any(marker in lowered for marker in _GENERIC_SYNTHESIS_MARKERS)


def extract_override_context(sanitized_synthesis: str) -> str:
    """Keep portfolio-rule context (liquidation cap, max buys) without generic mandate filler."""
    text = (sanitized_synthesis or "").strip()
    if not text:
        return ""
    parts = [p.strip() for p in re.split(r"\.\s+", text) if p.strip()]
    kept: list[str] = []
    for part in parts:
        fragment = part if part.endswith(".") else f"{part}."
        if _is_generic_synthesis(fragment):
            continue
        kept.append(fragment)
    return " ".join(kept).strip()


def enrich_position_from_round2(
    pos: dict,
    raw_verdicts: dict[str, dict] | None,
    *,
    sanitized_synthesis: str = "",
) -> dict:
    """Attach Round 2 champion/dissenter quotes for briefing render."""
    sym = (pos.get("symbol") or "").strip()
    if not sym or not raw_verdicts:
        return pos

    rows = _symbol_rows(raw_verdicts, sym)
    if not rows:
        return pos

    final = pos.get("final_verdict", "")
    preferred_keys = _agent_keys_for_names(pos.get("supporting_members") or [])
    champion_row = _pick_champion_row(rows, preferred_agents=preferred_keys, final_verdict=final)
    if not champion_row and preferred_keys:
        champion_row = _pick_champion_row(rows, preferred_agents=[], final_verdict=final)

    out = dict(pos)
    narrative = dict(pos.get("narrative") or {})
    override = extract_override_context(sanitized_synthesis)

    if champion_row:
        champion_analysis = champion_row["analysis"]
        if override:
            out["synthesis"] = f"{override} {champion_analysis}".strip()
        else:
            out["synthesis"] = champion_analysis
        narrative["champion"] = champion_row["display_name"]
        narrative["champion_quote"] = champion_analysis

        dissenter_row = _pick_dissenter_row(
            rows,
            champion_key=champion_row["agent_key"],
            final_verdict=final,
        )
        if dissenter_row:
            narrative["dissenter"] = dissenter_row["display_name"]
            narrative["dissenter_quote"] = dissenter_row["analysis"]
        else:
            narrative["dissenter"] = narrative.get("dissenter") or "None"
            narrative["dissenter_quote"] = ""
    elif override:
        out["synthesis"] = override

    out["narrative"] = narrative
    return out


def enrich_chairman_for_briefing(
    chairman_data: dict,
    raw_verdicts: dict[str, dict] | None,
    *,
    sanitize_fn,
) -> dict:
    """Return chairman_data copy with positions enriched from Round 2 quotes."""
    if not chairman_data or not raw_verdicts:
        return chairman_data

    out = dict(chairman_data)
    for section in ("portfolio_positions", "watchlist_positions"):
        enriched = []
        for pos in chairman_data.get(section) or []:
            sanitized = sanitize_fn(pos.get("synthesis", ""))
            enriched.append(
                enrich_position_from_round2(pos, raw_verdicts, sanitized_synthesis=sanitized)
            )
        out[section] = enriched

    alpha = dict(chairman_data.get("alpha_pick") or {})
    sym = (alpha.get("symbol") or "").strip()
    if sym and sym.upper() not in {"N/A", "NONE"}:
        rows = _symbol_rows(raw_verdicts, sym)
        preferred = []
        for section in ("portfolio_positions", "watchlist_positions"):
            for pos in out.get(section) or []:
                if (pos.get("symbol") or "").upper() == sym.upper():
                    preferred = _agent_keys_for_names(pos.get("supporting_members") or [])
                    break
        champion_row = _pick_champion_row(
            rows,
            preferred_agents=preferred,
            final_verdict="Buy",
        )
        if champion_row and champion_row["analysis"]:
            alpha["champion_quote"] = champion_row["analysis"]
    out["alpha_pick"] = alpha
    return out
