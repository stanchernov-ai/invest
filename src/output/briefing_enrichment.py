"""Enrich investor-facing Action Plan copy from Round 2 JSON + Flash strategic context."""
from __future__ import annotations

import json
import logging
import re
from typing import Callable

from google.genai import types

from src.core.agents import FAST_MODEL, FLASH_TOKEN_LIMIT, call_gemini_async, client
from src.core.schemas import ActionPlanStrategicContexts
from src.core.board_roster import (
    PANELIST_ARCHETYPES,
    normalize_panelist_key,
    panelist_short_name,
    resolve_panelist_key,
)
from src.core.vote_engine import (
    AGENT_DISPLAY,
    BUY_VERDICTS,
    build_vote_summaries,
    panel_verdict_side,
    _normalize_verdict,
)

logger = logging.getLogger(__name__)

_DISPLAY_TO_AGENT = {name: key for key, name in AGENT_DISPLAY.items()}
for legacy_name, key in (
    ("Warren Buffett", "hypatia"),
    ("Peter Lynch", "davinci"),
    ("Jesse Livermore", "suntzu"),
    ("Jensen Huang", "tesla"),
    ("Jim Simons", "aurelius"),
    ("Benjamin Franklin", "hypatia"),
    ("Charles Darwin", "davinci"),
    ("Pythagoras", "aurelius"),
    ("Aristotle", "hypatia"),
    ("Hypatia of Alexandria", "hypatia"),
    ("Leonardo da Vinci", "davinci"),
    ("Marcus Aurelius", "aurelius"),
):
    _DISPLAY_TO_AGENT.setdefault(legacy_name, key)

_MIN_STRATEGIC_CONTEXT_CHARS = 48
_QUOTE_OVERLAP_WORD_THRESHOLD = 0.42
_QUOTE_OVERLAP_SUBSTRING_CHARS = 40

_GENERIC_SYNTHESIS_MARKERS = (
    "consensus mandate from today's panel vote",
    "investment committee finalized this position",
    "vote-engine mandate",
    "deterministic mandate from round 2",
    "[vote engine]",
)

_STRATEGIC_CONTEXT_SYSTEM = """You are the board secretary drafting Strategic Context lines for an executive Action Plan.

For EACH symbol in the user prompt, write strategic_context: 2-3 sentences capturing why the committee landed on the final verdict.

Rules:
- Open with vote math when relevant (e.g. unanimous 5-0, or 3/5 majority split).
- Synthesize distinct panel worldviews (value, growth, tape, platform, quant) into one room narrative.
- Do NOT paste or lightly paraphrase a single panelist's Round 2 quote — Champion/Dissent lines carry those separately.
- When a guardrail override applies (liquidation cap, max buys), state that constraint first, then the board's underlying mandate.
- Write specific, investor-facing prose — never boilerplate like "the committee finalized this position"."""


def _iter_symbol_rows(raw_verdicts: dict[str, dict] | None):
    if not raw_verdicts:
        return
    for agent_key, agent_data in raw_verdicts.items():
        if not agent_data:
            continue
        agent_key = normalize_panelist_key(agent_key)
        if agent_key not in AGENT_DISPLAY:
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
    pool = opposing or None
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


def enrich_position_narratives(
    pos: dict,
    raw_verdicts: dict[str, dict] | None,
    *,
    sanitized_synthesis: str = "",
) -> dict:
    """Attach Round 2 champion/dissenter quotes without merging into strategic context."""
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
    if override:
        out["override_context"] = override

    if champion_row:
        narrative["champion"] = champion_row["display_name"]
        narrative["champion_quote"] = champion_row["analysis"]
        dissenter_row = _pick_dissenter_row(
            rows,
            champion_key=champion_row["agent_key"],
            final_verdict=final,
        )
        if dissenter_row:
            narrative["dissenter"] = dissenter_row["display_name"]
            narrative["dissenter_quote"] = dissenter_row["analysis"]
        else:
            narrative["dissenter"] = "None"
            narrative["dissenter_quote"] = "N/A"

    out["narrative"] = narrative
    return out


def _collect_positions(chairman_data: dict) -> list[dict]:
    positions: list[dict] = []
    for section in ("portfolio_positions", "watchlist_positions"):
        positions.extend(chairman_data.get(section) or [])
    return positions


def _action_plan_enriched(chairman_data: dict) -> bool:
    for pos in _collect_positions(chairman_data):
        ctx = (pos.get("strategic_context") or "").strip()
        if ctx and not _is_generic_synthesis(ctx):
            return True
    return False


def _build_symbol_prompt_block(
    pos: dict,
    raw_verdicts: dict[str, dict],
    summaries: dict,
) -> str:
    sym = (pos.get("symbol") or "").strip().upper()
    final = pos.get("final_verdict", "")
    summary = summaries.get(sym)
    buy = summary.buy_side_count() if summary else 0
    sell = summary.sell_side_count() if summary else 0
    unanimous = ""
    if summary and summary.is_unanimous():
        unanimous = " [UNANIMOUS 5/5]"
    override = pos.get("override_context") or ""
    lines = [
        f"### {sym} ###",
        f"Final verdict (executed): {final}",
        f"Round 2 votes: buy_side={buy}/5 sell_side={sell}/5{unanimous}",
    ]
    if override:
        lines.append(f"Guardrail override: {override}")
    lines.append("Round 2 panel analyses:")
    for row in _symbol_rows(raw_verdicts, sym):
        lines.append(
            f"- {row['display_name']} ({row['verdict']}, {row['conviction']}/10): {row['analysis']}"
        )
    return "\n".join(lines)


def _normalize_overlap_text(text: str) -> str:
    lowered = (text or "").lower()
    return re.sub(r"[^a-z0-9\s]", " ", lowered)


def _word_overlap_ratio(left: str, right: str) -> float:
    left_words = {w for w in _normalize_overlap_text(left).split() if len(w) > 2}
    right_words = {w for w in _normalize_overlap_text(right).split() if len(w) > 2}
    if not left_words or not right_words:
        return 0.0
    return len(left_words & right_words) / min(len(left_words), len(right_words))


def _overlaps_panel_quotes(text: str, *quotes: str) -> bool:
    """True when strategic context reuses Champion/Dissent Round 2 prose."""
    ctx = (text or "").strip()
    if not ctx:
        return False
    ctx_norm = _normalize_overlap_text(ctx)
    for quote in quotes:
        q = (quote or "").strip()
        if not q or q.upper() == "N/A":
            continue
        q_norm = _normalize_overlap_text(q)
        if len(q_norm) >= _QUOTE_OVERLAP_SUBSTRING_CHARS:
            if q_norm[:_QUOTE_OVERLAP_SUBSTRING_CHARS] in ctx_norm:
                return True
            if ctx_norm[:_QUOTE_OVERLAP_SUBSTRING_CHARS] in q_norm:
                return True
        if _word_overlap_ratio(ctx, q) >= _QUOTE_OVERLAP_WORD_THRESHOLD:
            return True
    return False


def _panelist_camp_label(row: dict) -> str:
    archetype = PANELIST_ARCHETYPES.get(row["agent_key"], "")
    short = panelist_short_name(row["agent_key"])
    if archetype:
        return f"{short} ({archetype.replace('The ', '')})"
    return short


def _committee_camps_sentence(rows: list[dict], final_verdict: str) -> str:
    """Name aligned vs opposing camps without quoting Round 2 analysis."""
    if not rows:
        return ""
    buy, sell, neutral, pass_ = [], [], [], []
    for row in rows:
        side = panel_verdict_side(row["verdict"], row["section"])
        label = _panelist_camp_label(row)
        if side == "buy":
            buy.append(label)
        elif side == "sell":
            sell.append(label)
        elif side == "pass":
            pass_.append(label)
        else:
            neutral.append(label)

    final = _normalize_verdict(final_verdict)
    sym = rows[0]["symbol"]

    def _join(names: list[str]) -> str:
        if not names:
            return ""
        if len(names) == 1:
            return names[0]
        return ", ".join(names[:-1]) + f", and {names[-1]}"

    if final in BUY_VERDICTS and buy:
        lead = _join(buy)
        if sell:
            return (
                f"The buy-side camp ({lead}) carried the room to an executed {final} "
                f"over reduce dissent ({_join(sell)})."
            )
        return f"The committee aligned on the buy-side ({lead}) for an executed {final} on {sym}."

    if final in ("STRONG SELL", "SELL", "TRIM") and sell:
        lead = _join(sell)
        if buy:
            return (
                f"The reduce camp ({lead}) set the mandate; growth dissent ({_join(buy)}) "
                f"did not block the executed {final}."
            )
        return f"The board aligned on the reduce side ({lead}) for an executed {final} on {sym}."

    if final == "PASS" and pass_:
        return (
            f"No actionable conviction emerged — {_join(pass_)} led the Pass stance on {sym}."
        )

    if final == "HOLD" and neutral:
        return f"The panel split without a tradeable edge; {_join(neutral)} anchored Hold on {sym}."

    camps = buy + sell + neutral + pass_
    if camps:
        return f"The committee debated across {len(camps)} distinct camps before landing on {final} for {sym}."
    return ""


def _vote_math_sentence(sym: str, summary, final_verdict: str) -> str:
    if not summary:
        return ""
    buy, sell = summary.buy_side_count(), summary.sell_side_count()
    final = _normalize_verdict(final_verdict)
    if summary.is_unanimous("reduce"):
        return f"The board reached a unanimous {sell}-0 Round 2 reduce mandate on {sym} (executed {final})."
    if summary.is_unanimous("buy"):
        return f"The board reached a unanimous {buy}-0 Round 2 buy mandate on {sym} (executed {final})."
    if summary.is_unanimous():
        return f"The panel voted unanimously on {sym}; committee executes {final}."
    return (
        f"Round 2 split buy_side={buy}/5 sell_side={sell}/5 on {sym}; "
        f"committee executes {final}."
    )


def _synthetic_strategic_context(
    pos: dict,
    raw_verdicts: dict[str, dict],
    summaries: dict,
) -> str:
    """Deterministic strategic context — vote math + camp labels, never panel quote paste."""
    sym = (pos.get("symbol") or "").strip().upper()
    rows = _symbol_rows(raw_verdicts, sym)
    final = pos.get("final_verdict", "")
    parts: list[str] = []
    override = pos.get("override_context") or ""
    if override:
        parts.append(override)
    summary = summaries.get(sym)
    vote_line = _vote_math_sentence(sym, summary, final)
    if vote_line:
        parts.append(vote_line)
    camp_line = _committee_camps_sentence(rows, final)
    if camp_line:
        parts.append(camp_line)
    text = " ".join(parts).strip()
    return text[:800] if text else ""


def _fallback_strategic_context(pos: dict, raw_verdicts: dict[str, dict], summaries: dict) -> str:
    """Degraded strategic context when Flash is unavailable or returns duplicate prose."""
    return _synthetic_strategic_context(pos, raw_verdicts, summaries)


def _finalize_strategic_context(
    pos: dict,
    ctx: str,
    raw_verdicts: dict[str, dict],
    summaries: dict,
) -> str:
    """Ensure strategic context is distinct from Champion/Dissent quotes."""
    narrative = pos.get("narrative") or {}
    quotes = (
        narrative.get("champion_quote") or "",
        narrative.get("dissenter_quote") or "",
    )
    cleaned = (ctx or "").strip()
    if (
        not cleaned
        or _is_generic_synthesis(cleaned)
        or len(cleaned) < _MIN_STRATEGIC_CONTEXT_CHARS
        or _overlaps_panel_quotes(cleaned, *quotes)
    ):
        return _synthetic_strategic_context(pos, raw_verdicts, summaries)
    return cleaned


def _apply_strategic_contexts(
    chairman_data: dict,
    contexts: dict[str, str],
    raw_verdicts: dict[str, dict],
    summaries: dict,
) -> dict:
    out = dict(chairman_data)
    for section in ("portfolio_positions", "watchlist_positions"):
        enriched = []
        for pos in chairman_data.get(section) or []:
            row = dict(pos)
            sym = (row.get("symbol") or "").strip().upper()
            ctx = (contexts.get(sym) or "").strip()
            ctx = _finalize_strategic_context(row, ctx, raw_verdicts, summaries)
            row["strategic_context"] = ctx
            row["synthesis"] = ctx
            enriched.append(row)
        out[section] = enriched
    return out


async def _flash_strategic_contexts(
    chairman_data: dict,
    raw_verdicts: dict[str, dict],
    *,
    portfolio_symbols: set[str],
) -> dict[str, str]:
    positions = _collect_positions(chairman_data)
    if not positions:
        return {}

    summaries = build_vote_summaries(
        raw_verdicts,
        [p.get("symbol", "") for p in positions],
        portfolio_symbols=portfolio_symbols,
    )
    blocks = [
        _build_symbol_prompt_block(pos, raw_verdicts, summaries)
        for pos in positions
    ]
    prompt = (
        "Write strategic_context for every symbol below (one JSON item per symbol).\n\n"
        + "\n\n".join(blocks)
    )

    if not client:
        logger.warning("Gemini client unavailable — using Round 2 fallback strategic contexts.")
        return {
            (p.get("symbol") or "").strip().upper(): _fallback_strategic_context(p, raw_verdicts, summaries)
            for p in positions
        }

    contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]
    config = types.GenerateContentConfig(
        system_instruction=_STRATEGIC_CONTEXT_SYSTEM,
        temperature=0.25,
        max_output_tokens=FLASH_TOKEN_LIMIT,
        response_mime_type="application/json",
        response_schema=ActionPlanStrategicContexts,
    )
    try:
        response = await call_gemini_async(
            FAST_MODEL,
            contents,
            config,
            agent_name="briefing_strategic_context",
            schema=ActionPlanStrategicContexts,
        )
        parsed = json.loads(response.text.strip().replace("```json", "").replace("```", "").strip())
        return {
            (item["symbol"] or "").strip().upper(): item["strategic_context"]
            for item in parsed.get("items", [])
            if item.get("symbol")
        }
    except Exception as exc:
        logger.warning("Flash strategic context failed (%s) — using Round 2 fallback.", exc)
        return {
            (p.get("symbol") or "").strip().upper(): _fallback_strategic_context(p, raw_verdicts, summaries)
            for p in positions
        }


def _enrich_narratives(
    chairman_data: dict,
    raw_verdicts: dict[str, dict] | None,
    *,
    sanitize_fn: Callable[[str], str],
) -> dict:
    if not chairman_data or not raw_verdicts:
        return chairman_data

    out = dict(chairman_data)
    for section in ("portfolio_positions", "watchlist_positions"):
        enriched = []
        for pos in chairman_data.get(section) or []:
            sanitized = sanitize_fn(pos.get("synthesis", ""))
            enriched.append(
                enrich_position_narratives(pos, raw_verdicts, sanitized_synthesis=sanitized)
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
        champion_row = _pick_champion_row(rows, preferred_agents=preferred, final_verdict="Buy")
        if champion_row and champion_row["analysis"]:
            alpha["champion_quote"] = champion_row["analysis"]
    out["alpha_pick"] = alpha
    return out


async def enrich_chairman_for_briefing(
    chairman_data: dict,
    raw_verdicts: dict[str, dict] | None,
    *,
    portfolio_symbols: set[str] | None = None,
    sanitize_fn: Callable[[str], str],
) -> dict:
    """Narratives from Round 2 JSON + Flash strategic context (batched per run)."""
    if not chairman_data or not raw_verdicts:
        return chairman_data
    if _action_plan_enriched(chairman_data):
        return chairman_data

    portfolio_symbols = portfolio_symbols or set()
    with_narratives = _enrich_narratives(chairman_data, raw_verdicts, sanitize_fn=sanitize_fn)
    contexts = await _flash_strategic_contexts(
        with_narratives, raw_verdicts, portfolio_symbols=portfolio_symbols,
    )
    summaries = build_vote_summaries(
        raw_verdicts,
        [p.get("symbol", "") for p in _collect_positions(with_narratives)],
        portfolio_symbols=portfolio_symbols,
    )
    return _apply_strategic_contexts(with_narratives, contexts, raw_verdicts, summaries)


def enrich_chairman_for_briefing_sync(
    chairman_data: dict,
    raw_verdicts: dict[str, dict] | None,
    *,
    portfolio_symbols: set[str] | None = None,
    sanitize_fn: Callable[[str], str],
) -> dict:
    """Sync path for unit tests — narratives + Round 2 fallback strategic context."""
    if not chairman_data or not raw_verdicts:
        return chairman_data
    if _action_plan_enriched(chairman_data):
        return chairman_data

    portfolio_symbols = portfolio_symbols or set()
    with_narratives = _enrich_narratives(chairman_data, raw_verdicts, sanitize_fn=sanitize_fn)
    positions = _collect_positions(with_narratives)
    summaries = build_vote_summaries(
        raw_verdicts,
        [p.get("symbol", "") for p in positions],
        portfolio_symbols=portfolio_symbols,
    )
    contexts = {
        (p.get("symbol") or "").strip().upper(): _fallback_strategic_context(p, raw_verdicts, summaries)
        for p in positions
    }
    return _apply_strategic_contexts(with_narratives, contexts, raw_verdicts, summaries)


# Backward-compatible alias used in older tests
enrich_position_from_round2 = enrich_position_narratives
