"""Shared debate log formatting — slim watchlist Pass rows, brawl ticker filters."""
from __future__ import annotations

import re

_BUY_SIDE_RE = re.compile(r"\b(?:strong\s+buy|buy)\b", re.I)
_TICKER_LINE = re.compile(r"^\*\s*\*\*(.+?)\*\*:\s*(.+)$", re.M)


def is_buy_side_verdict(verdict: str) -> bool:
    return bool(_BUY_SIDE_RE.search(verdict or ""))


def format_ticker_verdict_markdown(
    symbol: str,
    verdict: str,
    conviction_score: int,
    analysis: str = "",
) -> str:
    """Single markdown bullet: ``* **NVDA**: Hold (7/10). rationale``."""
    sym = (symbol or "Unknown").strip()
    v_erd = (verdict or "Hold").strip()
    v_sc = conviction_score if conviction_score is not None else 5
    v_ans = (analysis or "").strip()
    if v_ans:
        return f"* **{sym}**: {v_erd} ({v_sc}/10). {v_ans}"
    return f"* **{sym}**: {v_erd} ({v_sc}/10)."


def format_portfolio_verdict_markdown_lines(portfolio_verdicts: list[dict] | None) -> list[str]:
    """Every owned symbol gets its own line (portfolio mandates full rationales)."""
    lines: list[str] = []
    for row in portfolio_verdicts or []:
        lines.append(
            format_ticker_verdict_markdown(
                row.get("symbol", "Unknown"),
                row.get("verdict", "Hold"),
                row.get("conviction_score", 5),
                row.get("analysis") or "",
            )
        )
    return lines


def format_watchlist_verdict_markdown_lines(
    watchlist_verdicts: list[dict] | None,
    *,
    max_symbols_in_summary: int = 12,
) -> list[str]:
    """Actionable Buys as individual lines; aggregate no-buy-case names into one summary."""
    lines: list[str] = []
    no_buy_symbols: list[str] = []
    for row in watchlist_verdicts or []:
        sym = (row.get("symbol") or "Unknown").strip()
        verdict = (row.get("verdict") or "Pass").strip()
        if is_buy_side_verdict(verdict):
            lines.append(
                format_ticker_verdict_markdown(
                    sym,
                    verdict,
                    row.get("conviction_score", 5),
                    row.get("analysis") or "",
                )
            )
        else:
            no_buy_symbols.append(sym)
    if no_buy_symbols:
        preview = ", ".join(no_buy_symbols[:max_symbols_in_summary])
        extra = len(no_buy_symbols) - max_symbols_in_summary
        if extra > 0:
            preview = f"{preview}, … +{extra} more"
        lines.append(
            f"* **Watchlist — no buy case ({len(no_buy_symbols)} names)**: {preview} "
            f"(per-symbol votes in structured JSON)."
        )
    return lines


def symbol_from_ticker_line(line: str) -> str:
    head = (line.split(" — ", 1)[0] if " — " in line else line).strip()
    return head.split()[0].upper() if head else ""


def filter_debate_ticker_lines(
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
        sym = symbol_from_ticker_line(line)
        if portfolio and sym in portfolio:
            portfolio_lines.append(line)
        elif portfolio:
            detail = line.split(" — ", 1)[-1] if " — " in line else line
            if re.search(r"\bPass\b", detail, re.I):
                continue
            if "no buy case" in line.lower():
                continue
            watchlist_lines.append(line)
        else:
            portfolio_lines.append(line)
    max_watch = 5 if not is_rebuttal else 8
    if len(watchlist_lines) > max_watch:
        extra = len(watchlist_lines) - max_watch
        watchlist_lines = watchlist_lines[:max_watch]
        watchlist_lines.append(f"… +{extra} more watchlist names (full log)")
    return portfolio_lines, watchlist_lines


def format_ticker_debate_excerpt(lines: list[str], *, max_chars: int = 1800) -> str:
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


def parse_ticker_debate_lines_from_message(content: str, overview_markers: tuple[str, ...]) -> list[str]:
    """Per-symbol verdict lines from a board message — excludes portfolio-level summaries."""
    lines: list[str] = []
    for raw in (content or "").split("\n"):
        stripped = raw.strip()
        if not stripped or any(marker in stripped for marker in overview_markers):
            continue
        match = _TICKER_LINE.match(stripped)
        if not match:
            continue
        symbol = match.group(1).strip()
        if symbol.lower().startswith("watchlist"):
            continue
        detail = match.group(2).strip()
        if symbol and detail:
            lines.append(f"{symbol} — {detail}")
    return lines
