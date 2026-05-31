"""Round 2 rebuttal prompt construction and verbatim-R1 detection."""
from __future__ import annotations

import re

from src.core.agents import agent_config

from src.core.board_roster import PANELIST_KEYS

_OVERVIEW_RE = re.compile(
    r"\*\s*\*\*Portfolio Overview\*\*\s*:\s*(.+?)(?=\n\*|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_REBUTTAL_SUMMARY_RE = re.compile(
    r"\*\s*\*\*Rebuttal Summary\*\*\s*:\s*(.+?)(?=\n\*|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_ROUND2_HEADER_RE = re.compile(
    r"\*\*\[ROUND 2 REBUTTAL\]\s+(.+?)\*\*:",
    re.IGNORECASE,
)
_TICKER_VERDICT_LINE_RE = re.compile(
    r"^\*\s*\*\*([^*]+)\*\*\s*:\s*(.+)$",
)


def _marker_for(agent_key: str) -> str:
    return agent_config["board_members"][agent_key]["role"]


def extract_panelist_round2_block(messages: list[dict], agent_key: str) -> str:
    """Return only this panelist's Round 2 block (handles cumulative debate messages)."""
    marker = _marker_for(agent_key)
    header = f"**[ROUND 2 REBUTTAL] {marker}**:"
    for msg in reversed(messages or []):
        content = msg.get("content") or ""
        if header not in content:
            continue
        start = content.index(header)
        section = content[start:]
        next_match = _ROUND2_HEADER_RE.search(section, len(header))
        if next_match:
            section = section[: next_match.start()]
        return section
    return ""


def parse_ticker_verdict_from_line(line: str) -> tuple[str, str] | None:
    """Parse `* **NVDA**: Strong Sell (7/10).` → (symbol, verdict)."""
    match = _TICKER_VERDICT_LINE_RE.match((line or "").strip())
    if not match:
        return None
    ticker = match.group(1).strip()
    rest = match.group(2)
    # Verdict is before optional (score) or first sentence — ignore rationale prose.
    verdict_part = rest.split("(")[0].split(".")[0].strip()
    lower = verdict_part.lower()
    if "strong sell" in lower:
        return ticker, "Strong Sell"
    if "strong buy" in lower:
        return ticker, "Strong Buy"
    if re.search(r"\btrim\b", lower):
        return ticker, "Trim"
    if re.search(r"\bsell\b", lower):
        return ticker, "Sell"
    if re.search(r"\bbuy\b", lower):
        return ticker, "Buy"
    if re.search(r"\bpass\b", lower):
        return ticker, "Pass"
    if re.search(r"\bhold\b", lower):
        return ticker, "Hold"
    return None


def extract_round_overview(messages: list[dict], agent_key: str, round_num: str) -> str:
    """Extract portfolio-level prose from Round 1 or Round 2 debate log blocks."""
    marker = _marker_for(agent_key)
    round_tag = "[ROUND 1]" if round_num == "1" else "ROUND 2"
    pattern = _OVERVIEW_RE if round_num == "1" else _REBUTTAL_SUMMARY_RE
    for msg in messages or []:
        content = msg.get("content") or ""
        if marker not in content or round_tag not in content.upper():
            continue
        match = pattern.search(content)
        if match:
            return match.group(1).strip()
        if round_num == "2":
            fallback = _OVERVIEW_RE.search(content)
            if fallback:
                return fallback.group(1).strip()
    return ""


def _normalize_compare_text(text: str) -> str:
    return re.sub(r"[^a-z0-9\s]", " ", (text or "").lower()).strip()


def is_verbatim_r1_copy(r1: str, r2: str, *, word_overlap_threshold: float = 0.82) -> bool:
    """True when Round 2 overview is identical or near-copy of Round 1."""
    n1 = _normalize_compare_text(r1)
    n2 = _normalize_compare_text(r2)
    if not n1 or not n2:
        return False
    if n1 == n2:
        return True
    if n1 in n2 or n2 in n1:
        return True
    w1 = set(n1.split())
    w2 = set(n2.split())
    if not w1:
        return False
    overlap = len(w1 & w2) / len(w1)
    return overlap >= word_overlap_threshold


def _round1_peer_summaries(messages: list[dict], exclude_key: str) -> list[str]:
    lines: list[str] = []
    for key in PANELIST_KEYS:
        if key == exclude_key:
            continue
        overview = extract_round_overview(messages, key, "1")
        if overview:
            role = _marker_for(key)
            lines.append(f"- **{role}**: {overview[:500]}")
    return lines


def build_round2_user_prompt(agent_key: str, messages: list[dict]) -> str:
    """Per-panelist Round 2 user prompt — forces engagement with peer arguments."""
    role = _marker_for(agent_key)
    history = "\n\n".join(m["content"] for m in (messages or []))
    r1_self = extract_round_overview(messages, agent_key, "1")
    peers = _round1_peer_summaries(messages, agent_key)
    peers_block = "\n".join(peers) if peers else "- (See full Round 1 log below.)"

    return (
        f"You are **{role}** in ROUND 2 REBUTTAL.\n\n"
        f"YOUR ROUND 1 PORTFOLIO OVERVIEW — do NOT copy or lightly paraphrase:\n"
        f"\"\"\"{r1_self or '(none recorded)'}\"\"\"\n\n"
        f"OTHER PANELISTS' ROUND 1 VIEWPOINTS — you MUST name at least one peer and respond:\n"
        f"{peers_block}\n\n"
        "[ROUND 2 TASK]\n"
        "1. `overall_portfolio_critique`: 2-3 NEW sentences TO THE ROOM. The FIRST sentence MUST name another "
        "panelist by name and respond to their Round 1 claim (agree, disagree, or concede). At least 50% of "
        "the words must be new vs your Round 1 Portfolio Overview block above — do NOT copy or lightly "
        "paraphrase that block. Conversational flow, not a stock list.\n"
        "2. Every `analysis` field: NEW Round 2 reasoning (max 2 sentences). Reference a peer "
        "argument or new evidence — never paste Round 1 analysis.\n"
        "3. Final `verdict` + `conviction_score` for every portfolio and watchlist symbol.\n\n"
        "[ANTI-DRIFT PROTOCOL]\n"
        "When rebutting peers, you MUST paraphrase their arguments in your own persona's vocabulary. "
        "You are STRICTLY FORBIDDEN from adopting their jargon. For example, if you are Sun Tzu, do not say 'margin of safety'; "
        "if you are Hypatia, do not say 'the tape' or 'relative strength'. Stay in character.\n\n"
        f"FULL DEBATE LOG:\n{history}"
    )
