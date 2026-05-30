"""Boardroom brawl synthesis helpers — clerk digest, validation, deterministic fallback."""
from __future__ import annotations

import re

from src.core.agents import agent_config
from src.core.board_roster import PANELIST_KEYS, PANELIST_ROLES

_OVERVIEW_MARKERS = ("**Portfolio Overview**", "**Rebuttal Summary**")
_ROUND1 = re.compile(r"\*\*\[ROUND 1\]", re.I)
_ROUND2 = re.compile(r"\*\*\[ROUND 2", re.I)
_HEADER = re.compile(r"^\*\*\[(ROUND \d+[^\]]*)\]\s*(.+?)\*\*\s*$", re.M)


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
