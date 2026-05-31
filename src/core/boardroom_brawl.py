"""Boardroom brawl synthesis helpers — clerk digest, validation, deterministic fallback."""
from __future__ import annotations

import re

from src.core.agents import agent_config
from src.core.board_roster import (
    PANELIST_KEYS,
    PANELIST_ROLES,
    PANELIST_AVATAR_URLS,
    resolve_panelist_key,
    shorten_panelist_references,
)

_OVERVIEW_MARKERS = ("**Portfolio Overview**", "**Rebuttal Summary**")
_TICKER_LINE = re.compile(r"^\*\s*\*\*(.+?)\*\*:\s*(.+)$", re.M)
_ROUND1 = re.compile(r"\*\*\[ROUND 1\]", re.I)
_ROUND2 = re.compile(r"\*\*\[ROUND 2", re.I)
_HEADER = re.compile(r"^\*\*\[(ROUND\s+\d+[^\]]*)\]\s*(.+?)\*\*:?\s*$", re.I | re.M)


def build_clerk_debate_digest(messages: list[dict]) -> str:
    """Slim debate context for the clerk — portfolio-level summaries only, not per-ticker dumps."""
    sections: list[str] = []
    for msg in messages or []:
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        lines = content.split("\n")
        header = lines[0] if lines else ""
        slim = [header] if header else []
        for line in lines[1:]:
            if any(marker in line for marker in _OVERVIEW_MARKERS):
                slim.append(line)
        if len(slim) > 1 or (slim and _ROUND1.search(slim[0])) or (slim and _ROUND2.search(slim[0])):
            sections.append("\n".join(slim))
    return "\n\n".join(sections)


def is_boardroom_brawl_complete(text: str) -> bool:
    """True when brawl is long enough, ends cleanly, and has multi-paragraph structure."""
    plain = re.sub(r"<[^>]+>", "", text or "").strip()
    if len(plain) < 200:
        return False
    if not re.search(r'[.!?]["\']?\s*$', plain):
        return False
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", plain) if p.strip()]
    if len(paragraphs) >= 2:
        return all(len(p) >= 40 for p in paragraphs[:2])
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", plain) if s.strip()]
    return len(sentences) >= 3 and len(plain) >= 350


def split_debate_paragraphs(brawl_text: str) -> list[str]:
    """Split brawl narrative into display paragraphs (prefer blank-line breaks)."""
    text = (brawl_text or "").strip()
    if not text:
        return []
    if "\n\n" in text:
        parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        if len(parts) >= 2:
            return parts
    return [p.strip() for p in text.split("\n") if p.strip()]


def _extract_debate_excerpt(content: str) -> str:
    """Portfolio Overview (R1) or Rebuttal Summary (R2) — clerk/fallback only."""
    for line in content.split("\n"):
        stripped = line.strip()
        for marker in _OVERVIEW_MARKERS:
            if marker in stripped and ":" in stripped:
                text = stripped.split(":", 1)[-1].strip()
                if text:
                    return text
    return ""


def _extract_ticker_debate_lines(content: str) -> list[str]:
    """Per-symbol verdict lines from a board message — excludes portfolio-level summaries."""
    lines: list[str] = []
    for raw in (content or "").split("\n"):
        stripped = raw.strip()
        if not stripped or any(marker in stripped for marker in _OVERVIEW_MARKERS):
            continue
        match = _TICKER_LINE.match(stripped)
        if not match:
            continue
        symbol = match.group(1).strip()
        detail = match.group(2).strip()
        if symbol and detail:
            lines.append(f"{symbol} — {detail}")
    return lines


def _extract_section_prose(content: str, marker: str) -> str:
    """Pull Portfolio Overview or Rebuttal Summary line body."""
    for raw in (content or "").split("\n"):
        stripped = raw.strip()
        if marker in stripped and ":" in stripped:
            text = stripped.split(":", 1)[-1].strip()
            if text:
                return text
    return ""


def _symbol_from_ticker_line(line: str) -> str:
    head = (line.split(" — ", 1)[0] if " — " in line else line).strip()
    return head.split()[0].upper() if head else ""


def _filter_debate_ticker_lines(
    lines: list[str],
    *,
    portfolio_symbols: set[str] | None,
    is_rebuttal: bool,
) -> tuple[list[str], list[str]]:
    """Split portfolio vs watchlist; drop Pass spam from watchlist in investor-facing debate."""
    portfolio = {s.upper() for s in (portfolio_symbols or set())}
    portfolio_lines: list[str] = []
    watchlist_lines: list[str] = []
    for line in lines:
        sym = _symbol_from_ticker_line(line)
        if portfolio and sym in portfolio:
            portfolio_lines.append(line)
        elif portfolio:
            detail = line.split(" — ", 1)[-1] if " — " in line else line
            if re.search(r"\bPass\b", detail, re.I):
                continue
            watchlist_lines.append(line)
        else:
            portfolio_lines.append(line)
    # Cap watchlist noise in Round 1; show actionable watchlist names only.
    max_watch = 5 if not is_rebuttal else 8
    if len(watchlist_lines) > max_watch:
        extra = len(watchlist_lines) - max_watch
        watchlist_lines = watchlist_lines[:max_watch]
        watchlist_lines.append(f"… +{extra} more watchlist names (full log)")
    return portfolio_lines, watchlist_lines


def _compose_turn_text(
    overview: str,
    portfolio_lines: list[str],
    watchlist_lines: list[str],
    *,
    is_rebuttal: bool,
) -> str:
    """Lead with conversational overview; attach compact position tables."""
    parts: list[str] = []
    if overview:
        parts.append(shorten_panelist_references(overview))
    if portfolio_lines:
        label = "Where I land on holdings" if is_rebuttal else "Portfolio calls"
        excerpt = _format_ticker_debate_excerpt(portfolio_lines, max_chars=1400)
        if excerpt:
            parts.append(f"{label}:\n{excerpt}")
    if watchlist_lines:
        label = "Watchlist moves" if is_rebuttal else "Watchlist highlights"
        excerpt = _format_ticker_debate_excerpt(watchlist_lines, max_chars=900)
        if excerpt:
            parts.append(f"{label}:\n{excerpt}")
    return "\n\n".join(parts)


def _format_ticker_debate_excerpt(lines: list[str], *, max_chars: int = 1800) -> str:
    """Join ticker debate lines for investor-facing chat bubbles."""
    if not lines:
        return ""
    parts: list[str] = []
    total = 0
    for line in lines:
        extra = len(line) + (1 if parts else 0)
        if total + extra > max_chars:
            parts.append("… (additional symbols in full debate log)")
            break
        parts.append(line)
        total += extra
    return "\n".join(parts)


def _parse_debate_message(content: str) -> tuple[str, str, str] | None:
    """Return (round_label, panelist_key, speaker_name) from a board message."""
    first_line = (content or "").split("\n", 1)[0].strip()
    match = _HEADER.match(first_line)
    if not match:
        return None
    round_label = match.group(1).strip().upper()
    speaker = match.group(2).strip().rstrip(":")
    panelist_key = resolve_panelist_key(speaker)
    if not panelist_key:
        return None
    return round_label, panelist_key, PANELIST_ROLES[panelist_key]


def debate_turn_heading(round_label: str) -> str:
    """Investor-facing debate phase — never show raw Round 1 / Round 2 labels."""
    label = (round_label or "").upper()
    if label.startswith("ROUND 1"):
        return "Initial Positions"
    if "ROUND 2" in label:
        return "Rebuttal"
    return ""


def build_debate_dialogue_turns(
    messages: list[dict],
    *,
    portfolio_symbols: set[str] | None = None,
) -> list[dict]:
    """Structured chat turns — opening/rebuttal prose first, then compact position calls."""
    turns: list[dict] = []
    for msg in messages or []:
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        parsed = _parse_debate_message(content)
        if not parsed:
            continue
        round_label, panelist_key, speaker = parsed
        is_rebuttal = "ROUND 2" in round_label
        overview_marker = "Rebuttal Summary" if is_rebuttal else "Portfolio Overview"
        overview = _extract_section_prose(content, overview_marker)
        ticker_lines = _extract_ticker_debate_lines(content)
        portfolio_lines, watchlist_lines = _filter_debate_ticker_lines(
            ticker_lines,
            portfolio_symbols=portfolio_symbols,
            is_rebuttal=is_rebuttal,
        )
        text = _compose_turn_text(
            overview, portfolio_lines, watchlist_lines, is_rebuttal=is_rebuttal,
        )
        if not text:
            continue
        turns.append({
            "speaker": speaker,
            "panelist_key": panelist_key,
            "turn_heading": debate_turn_heading(round_label),
            "text": text,
            "avatar_url": PANELIST_AVATAR_URLS[panelist_key],
            "align": "left",
        })
    for idx, turn in enumerate(turns):
        turn["align"] = "left" if idx % 2 == 0 else "right"
        turn["index"] = idx
    return turns


def build_debate_display_blocks(
    brawl_text: str,
    *,
    raw_board_messages: list[dict] | None = None,
    portfolio_symbols: set[str] | None = None,
) -> list[dict]:
    """Chat-style debate turns; falls back to clerk narrative paragraphs when messages unavailable."""
    turns = build_debate_dialogue_turns(
        raw_board_messages or [],
        portfolio_symbols=portfolio_symbols,
    )
    if turns:
        return [{"kind": "turn", **turn} for turn in turns]

    paragraphs = split_debate_paragraphs(brawl_text)
    blocks: list[dict] = []
    round_header_re = re.compile(r"^\s*\*\*\[ROUND\s+(?:ONE|TWO|\d+)", re.I)
    for idx, para in enumerate(paragraphs):
        kind = "body"
        first_line = para.split("\n", 1)[0].strip()
        if round_header_re.match(first_line):
            para = para.split("\n", 1)[-1].strip() if "\n" in para else ""
            if not para:
                continue
        blocks.append({"html": para, "kind": kind, "label": "", "index": idx})
    return blocks


def fallback_boardroom_brawl(messages: list[dict], raw_verdicts: dict[str, dict]) -> str:
    """Deterministic three-paragraph brawl when the clerk LLM returns truncated output."""
    r1_lines: list[str] = []
    r2_lines: list[str] = []

    for msg in messages or []:
        content = msg.get("content") or ""
        for match in _HEADER.finditer(content):
            round_label, role = match.group(1), match.group(2).strip()
            overview = ""
            for line in content.split("\n"):
                if any(marker in line for marker in _OVERVIEW_MARKERS):
                    overview = re.sub(r"^\*\s*", "", line.split(":", 1)[-1]).strip()
                    break
            if not overview:
                continue
            if round_label.upper().startswith("ROUND 1"):
                r1_lines.append(f"{role} opened by arguing that {overview}")
            elif round_label.upper().startswith("ROUND 2"):
                r2_lines.append(f"{role} fired back in rebuttal: {overview}")

    if not r2_lines:
        for key in PANELIST_KEYS:
            data = raw_verdicts.get(key) or {}
            critique = (data.get("overall_portfolio_critique") or "").strip()
            if not critique:
                continue
            role = agent_config["board_members"][key]["role"]
            r2_lines.append(f"{role} concluded Round 2 by stating: {critique}")

    para1 = (
        "Round 1 set the philosophical tone as each panelist staked an initial claim on the portfolio. "
        + " ".join(r1_lines[:3])
        if r1_lines
        else "Round 1 exposed deep philosophical splits across value, growth, momentum, and quantitative lenses."
    )
    para2 = (
        "The rebuttal round turned personal as members attacked each other's premises by name. "
        + " ".join(r2_lines[:4])
        if r2_lines
        else "Round 2 rebuttals sharpened disagreements without a clean consensus emerging."
    )
    para3 = (
        "By session's end the board remained divided on conviction and capital allocation, "
        "leaving the Chairman to reconcile competing mandates into a single executable plan."
    )
    return f"{para1}\n\n{para2}\n\n{para3}"
