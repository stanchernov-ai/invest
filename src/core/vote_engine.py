"""Deterministic vote arithmetic from Round 2 panel JSON (SSOT).

Panel structured output is ground truth — never re-count votes from debate markdown.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

from src.core.guardrails import (
    BUY_VERDICTS,
    MAX_DAILY_BUYS,
    SELL_VERDICTS,
    _is_hedge_symbol,
    _normalize_verdict,
    _prepend_override,
    count_equity_buys,
)

FUNDING_SELL_MARKER = "[VOTE ENGINE] Funding sell"

logger = logging.getLogger(__name__)

MAJORITY_THRESHOLD = 3
PANEL_SIZE = 5

from src.core.board_roster import PANELIST_KEYS, PANELIST_ROLES, normalize_panelist_key

AGENT_KEYS = PANELIST_KEYS
AGENT_DISPLAY = PANELIST_ROLES

Bucket = Literal["buy", "reduce", "hold", "pass"]

BUY_SIDE_VERDICTS = frozenset({"STRONG BUY", "BUY"})
SELL_SIDE_VERDICTS = frozenset({"STRONG SELL", "SELL", "TRIM"})


def panel_verdict_side(verdict: str, section: Literal["portfolio", "watchlist"]) -> Literal["buy", "sell", "pass", "neutral"]:
    """Map panel Round 2 vote to buy-side, sell-side, pass (watchlist), or neutral."""
    v = _normalize_verdict(verdict)
    if v in BUY_SIDE_VERDICTS:
        return "buy"
    if v in SELL_SIDE_VERDICTS:
        return "sell"
    if v == "PASS":
        return "pass" if section == "watchlist" else "neutral"
    return "neutral"


def verdict_bucket(verdict: str) -> Bucket:
    v = _normalize_verdict(verdict)
    if v in BUY_VERDICTS:
        return "buy"
    if v in SELL_SIDE_VERDICTS:
        return "reduce"
    if v == "PASS":
        return "pass"
    return "hold"


def _iter_panel_verdicts(raw_verdicts: dict[str, dict] | None):
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
                yield agent_key, sym, section, row.get("verdict", ""), int(row.get("conviction_score") or 0)


@dataclass
class SymbolVoteSummary:
    symbol: str
    section: Literal["portfolio", "watchlist"]
    votes: dict[str, tuple[str, int]] = field(default_factory=dict)  # agent_key -> (verdict, conviction)
    bucket_counts: dict[Bucket, int] = field(default_factory=dict)

    def rebuild_counts(self) -> None:
        counts: dict[Bucket, int] = {"buy": 0, "reduce": 0, "hold": 0, "pass": 0}
        for verdict, _conviction in self.votes.values():
            counts[verdict_bucket(verdict)] += 1
        self.bucket_counts = counts

    def buy_side_count(self) -> int:
        return sum(
            1 for v, _ in self.votes.values()
            if panel_verdict_side(v, self.section) == "buy"
        )

    def sell_side_count(self) -> int:
        return sum(
            1 for v, _ in self.votes.values()
            if panel_verdict_side(v, self.section) == "sell"
        )

    def pass_count(self) -> int:
        return sum(
            1 for v, _ in self.votes.values()
            if panel_verdict_side(v, self.section) == "pass"
        )

    @property
    def panel_count(self) -> int:
        return len(self.votes)

    def is_unanimous(self, bucket: Bucket | None = None) -> bool:
        if self.panel_count < PANEL_SIZE:
            return False
        buckets = {verdict_bucket(v) for v, _ in self.votes.values()}
        if len(buckets) != 1:
            return False
        if bucket is None:
            return True
        return next(iter(buckets)) == bucket

    def majority_bucket(self) -> Bucket | None:
        best: Bucket | None = None
        best_count = 0
        for b, count in self.bucket_counts.items():
            if count > best_count:
                best_count = count
                best = b
        if best_count >= MAJORITY_THRESHOLD:
            return best
        return None

    def is_actionable_unanimous(self) -> bool:
        """5/5 on Buy or 5/5 on Reduce only."""
        return self.is_unanimous("buy") or self.is_unanimous("reduce")

    def has_actionable_majority(self) -> bool:
        return (self.bucket_counts.get("buy", 0) >= MAJORITY_THRESHOLD
                or self.bucket_counts.get("reduce", 0) >= MAJORITY_THRESHOLD)

    def needs_chairman_judgment(self) -> bool:
        """Phase C: mandates are always Python-resolvable when the full panel voted."""
        return self.panel_count < MAJORITY_THRESHOLD


def build_vote_summaries(
    raw_verdicts: dict[str, dict] | None,
    all_symbols: list[str],
    *,
    portfolio_symbols: set[str] | None = None,
) -> dict[str, SymbolVoteSummary]:
    portfolio_symbols = portfolio_symbols or set()
    summaries: dict[str, SymbolVoteSummary] = {}
    for sym in all_symbols:
        section: Literal["portfolio", "watchlist"] = "portfolio" if sym in portfolio_symbols else "watchlist"
        summaries[sym] = SymbolVoteSummary(symbol=sym, section=section)

    for agent_key, sym, section, verdict, conviction in _iter_panel_verdicts(raw_verdicts):
        if sym not in summaries:
            summaries[sym] = SymbolVoteSummary(symbol=sym, section=section)  # type: ignore[arg-type]
        summaries[sym].votes[agent_key] = (verdict, conviction)
        if section == "portfolio":
            summaries[sym].section = "portfolio"
        elif summaries[sym].section != "portfolio":
            summaries[sym].section = "watchlist"

    for summary in summaries.values():
        summary.rebuild_counts()
    return summaries


def board_majority_buy_counts(raw_verdicts: dict[str, dict] | None) -> dict[str, int]:
    """Round 2 panel votes: symbol -> count of Buy/Strong Buy."""
    counts: dict[str, int] = {}
    for _, sym, _, verdict, _ in _iter_panel_verdicts(raw_verdicts):
        if _normalize_verdict(verdict) in BUY_VERDICTS:
            counts[sym] = counts.get(sym, 0) + 1
    return counts


def detect_unicorn_trades(summaries: dict[str, SymbolVoteSummary]) -> list[dict]:
    trades: list[dict] = []
    for sym, summary in summaries.items():
        if not summary.is_unanimous():
            continue
        verdict = next(iter(summary.votes.values()))[0]
        if verdict_bucket(verdict) == "pass":
            continue
        trades.append({"symbol": sym, "verdict": verdict.title() if verdict else "Hold"})
    return trades


def detect_sell_candidates(summaries: dict[str, SymbolVoteSummary]) -> list[str]:
    return [
        sym for sym, summary in summaries.items()
        if summary.sell_side_count() >= MAJORITY_THRESHOLD
        and summary.section == "portfolio"
    ]


def _buy_rank_score(summary: SymbolVoteSummary) -> int:
    """Rank max-3 candidates: Strong Buy votes weighted above Buy."""
    score = 0
    for verdict, conviction in summary.votes.values():
        v = _normalize_verdict(verdict)
        if v == "STRONG BUY":
            score += int(conviction) + 100
        elif v == "BUY":
            score += int(conviction)
    return score


def _mandate_from_buy_votes(summary: SymbolVoteSummary) -> str:
    strong = sum(
        1 for v, _ in summary.votes.values() if _normalize_verdict(v) == "STRONG BUY"
    )
    if strong >= MAJORITY_THRESHOLD:
        return "Strong Buy"
    return "Buy"


def _mandate_from_sell_votes(summary: SymbolVoteSummary) -> str:
    strong = sum(
        1 for v, _ in summary.votes.values() if _normalize_verdict(v) == "STRONG SELL"
    )
    if strong >= MAJORITY_THRESHOLD:
        return "Strong Sell"
    regular = sum(
        1 for v, _ in summary.votes.values()
        if _normalize_verdict(v) in ("SELL", "TRIM")
    )
    return "Sell" if regular >= MAJORITY_THRESHOLD else "Trim"


def mandate_verdict(summary: SymbolVoteSummary) -> str:
    """Phase C mandate: ≥3/5 buy-side or sell-side; else Hold (portfolio) / Pass (watchlist)."""
    buys = summary.buy_side_count()
    sells = summary.sell_side_count()

    if summary.section == "watchlist":
        if buys >= MAJORITY_THRESHOLD:
            return _mandate_from_buy_votes(summary)
        return "Pass"

    if buys >= MAJORITY_THRESHOLD and buys > sells:
        return _mandate_from_buy_votes(summary)
    if sells >= MAJORITY_THRESHOLD and sells > buys:
        return _mandate_from_sell_votes(summary)
    return "Hold"


def can_determine_allocation(summaries: dict[str, SymbolVoteSummary]) -> bool:
    """Skip chairman Pro when every symbol has a full panel vote (Phase C mandates in Python)."""
    if not summaries:
        return False
    return all(summary.panel_count >= MAJORITY_THRESHOLD for summary in summaries.values())


def can_bypass_chairman(summaries: dict[str, SymbolVoteSummary]) -> bool:
    """Alias for ``can_determine_allocation``."""
    return can_determine_allocation(summaries)


def _supporting_for_mandate(summary: SymbolVoteSummary, final_verdict: str) -> tuple[list[str], int]:
    final = _normalize_verdict(final_verdict)
    members: list[str] = []
    conviction_sum = 0
    for agent_key, (verdict, conviction) in summary.votes.items():
        side = panel_verdict_side(verdict, summary.section)
        v = _normalize_verdict(verdict)
        matched = False
        if final in BUY_VERDICTS and side == "buy":
            matched = True
        elif final in ("STRONG SELL", "SELL", "TRIM") and side == "sell":
            matched = True
        elif final == "PASS" and side == "pass":
            matched = True
        elif final == "HOLD" and side == "neutral":
            matched = True
        if matched:
            members.append(AGENT_DISPLAY.get(agent_key, agent_key))
            conviction_sum += conviction
    return members, conviction_sum


def build_matrix_from_raw_verdicts(
    raw_verdicts: dict[str, dict] | None,
    all_symbols: list[str],
) -> dict[str, dict[str, str]]:
    matrix = {t: {k: "" for k in AGENT_KEYS} for t in all_symbols}
    for agent_key, sym, _, verdict, _ in _iter_panel_verdicts(raw_verdicts):
        if sym in matrix:
            matrix[sym][agent_key] = verdict or ""
    return matrix


def format_vote_digest(
    summaries: dict[str, SymbolVoteSummary],
    *,
    portfolio_symbols: set[str] | None = None,
) -> str:
    portfolio_symbols = portfolio_symbols or set()
    lines = [
        "DETERMINISTIC VOTE DIGEST (Round 2 JSON — authoritative; do not re-count from prose):",
        f"Phase C mandate: ≥{MAJORITY_THRESHOLD}/{PANEL_SIZE} buy-side (Strong Buy+Buy) or "
        f"sell-side (Strong Sell+Sell); else Hold/Pass. Strong Buy/Sell rank above Buy/Sell.",
        "",
    ]
    for sym in sorted(summaries.keys(), key=lambda s: (s not in portfolio_symbols, s)):
        s = summaries[sym]
        mandate = mandate_verdict(s)
        uni = ""
        if s.is_actionable_unanimous():
            uni = " [ACTIONABLE UNANIMOUS 5/5]"
        elif s.is_unanimous():
            uni = " [UNANIMOUS]"
        lines.append(
            f"  {sym}: buy_side={s.buy_side_count()}/5 sell_side={s.sell_side_count()}/5 "
            f"pass={s.pass_count()}/5 → mandate={mandate}{uni}"
        )
    deterministic = can_determine_allocation(summaries)
    lines.append("")
    lines.append(
        f"BYPASS CHAIRMAN ARBITRATION: "
        f"{'YES — vote_engine allocation in Python' if deterministic else 'NO — judgment required'}"
    )
    return "\n".join(lines)


def _default_narrative(champion: str = "Board") -> dict:
    return {
        "champion": champion,
        "champion_quote": "Vote-engine mandate from unanimous / deterministic Round 2 panel votes.",
        "dissenter": "None",
        "dissenter_quote": "N/A",
    }


def _pick_alpha_pick_from_chairman(
    chairman: dict,
    summaries: dict[str, SymbolVoteSummary],
) -> dict:
    """Alpha pick from executed Buy rows only (post max-3 cap)."""
    candidates: list[tuple[int, str]] = []
    for section in ("portfolio_positions", "watchlist_positions"):
        for pos in chairman.get(section) or []:
            sym = (pos.get("symbol") or "").strip()
            if not sym or _is_hedge_symbol(sym):
                continue
            if _normalize_verdict(pos.get("final_verdict", "")) not in BUY_VERDICTS:
                continue
            summary = summaries.get(sym)
            if summary and summary.buy_side_count() < MAJORITY_THRESHOLD:
                continue
            conviction = int(pos.get("aggregate_conviction_score") or 0)
            candidates.append((conviction, sym))
    candidates.sort(key=lambda x: (-x[0], x[1]))
    if not candidates:
        sym = next(iter(summaries.keys()), "N/A")
        return {"symbol": sym, "champion_quote": "No executed majority Buy for alpha pick."}
    sym = candidates[0][1]
    summary = summaries[sym]
    members, _ = _supporting_for_mandate(summary, mandate_verdict(summary))
    champion = members[0] if members else "Board"
    return {
        "symbol": sym,
        "champion_quote": f"{champion} led the board's conviction on {sym} for near-term alpha.",
    }


def _pick_alpha_pick(
    summaries: dict[str, SymbolVoteSummary],
    raw_verdicts: dict[str, dict] | None,
) -> dict:
    """Legacy helper — prefer ``_pick_alpha_pick_from_chairman`` after max-3 cap."""
    candidates: list[tuple[int, str]] = []
    for sym, summary in summaries.items():
        if summary.buy_side_count() < MAJORITY_THRESHOLD:
            continue
        candidates.append((_buy_rank_score(summary), sym))
    candidates.sort(key=lambda x: (-x[0], x[1]))
    if not candidates:
        sym = next(iter(summaries.keys()), "N/A")
        return {"symbol": sym, "champion_quote": "No majority Buy candidate in Round 2."}
    sym = candidates[0][1]
    members, _ = _supporting_for_mandate(summaries[sym], mandate_verdict(summaries[sym]))
    champion = members[0] if members else "Board"
    return {
        "symbol": sym,
        "champion_quote": f"{champion} led the board's conviction on {sym} for near-term alpha.",
    }


def is_funding_sell_override(pos: dict) -> bool:
    """True when Python assigned a sell to fund equity buys (exempt from mandate alignment)."""
    return FUNDING_SELL_MARKER in (pos.get("synthesis") or "")


def count_board_portfolio_sell_mandates(
    summaries: dict[str, SymbolVoteSummary],
    portfolio_symbols: set[str],
) -> int:
    """Portfolio symbols with a Round 2 majority sell-side mandate (Trim/Sell/Strong Sell)."""
    count = 0
    for sym, summary in summaries.items():
        if sym not in portfolio_symbols:
            continue
        if _normalize_verdict(mandate_verdict(summary)) in SELL_VERDICTS:
            count += 1
    return count


def _portfolio_has_sell(chairman: dict) -> bool:
    for pos in chairman.get("portfolio_positions") or []:
        sym = (pos.get("symbol") or "").strip()
        if not sym or _is_hedge_symbol(sym):
            continue
        if _normalize_verdict(pos.get("final_verdict", "")) in SELL_VERDICTS:
            return True
    return False


def _funding_sell_candidates(chairman: dict) -> list[dict]:
    """Portfolio equities eligible to fund buys: Hold, Trim, Sell, Strong Sell — never Buy."""
    candidates: list[dict] = []
    for pos in chairman.get("portfolio_positions") or []:
        sym = (pos.get("symbol") or "").strip()
        if not sym or _is_hedge_symbol(sym):
            continue
        if _normalize_verdict(pos.get("final_verdict", "")) in BUY_VERDICTS:
            continue
        candidates.append(pos)
    return candidates


def _all_portfolio_equities_are_buys(chairman: dict) -> bool:
    """True when every non-hedge portfolio row is Buy/Strong Buy (no sell funding possible)."""
    equities = [
        pos for pos in (chairman.get("portfolio_positions") or [])
        if (pos.get("symbol") or "").strip() and not _is_hedge_symbol(pos.get("symbol", ""))
    ]
    if not equities:
        return False
    return all(
        _normalize_verdict(pos.get("final_verdict", "")) in BUY_VERDICTS
        for pos in equities
    )


def ensure_funding_sell(
    chairman: dict,
    *,
    summaries: dict[str, SymbolVoteSummary] | None = None,
    portfolio_symbols: set[str] | None = None,
    raw_verdicts: dict[str, dict] | None = None,
    all_symbols: list[str] | None = None,
) -> dict:
    """When equity buys exist, authorize one portfolio Sell — lowest conviction — to fund them.

    Funding sell candidate pool (portfolio only):
      - Allowed: Hold, Trim, Sell, Strong Sell (any non-Buy equity).
      - Forbidden: Buy, Strong Buy, hedge symbols (TLT/VXX).

    Hard stop: if every portfolio equity is Buy/Strong Buy, no sell is added.

    Skipped when the board already voted sell on more than one portfolio name.
    Skipped when a portfolio Sell/Trim/Strong Sell is already present.
    """
    if count_equity_buys(chairman) < 1:
        return chairman

    ps = portfolio_symbols or set()
    if summaries is None and raw_verdicts is not None and ps:
        symbols = all_symbols or list(ps)
        summaries = build_vote_summaries(raw_verdicts, symbols, portfolio_symbols=ps)

    if summaries and ps and count_board_portfolio_sell_mandates(summaries, ps) > 1:
        return chairman

    if _portfolio_has_sell(chairman):
        return chairman

    if _all_portfolio_equities_are_buys(chairman):
        logger.info(
            "Funding sell skipped — all portfolio equities are Buy/Strong Buy; "
            "no non-buy holding available to fund equity purchases."
        )
        return chairman

    candidates = _funding_sell_candidates(chairman)
    if not candidates:
        return chairman

    victim = min(
        candidates,
        key=lambda p: (int(p.get("aggregate_conviction_score") or 0), p.get("symbol", "")),
    )
    score = int(victim.get("aggregate_conviction_score") or 0)
    victim["final_verdict"] = "Sell"
    _prepend_override(
        victim,
        f"{FUNDING_SELL_MARKER} — lowest conviction portfolio holding "
        f"(score {score}) funds equity buy(s).",
    )

    audit = chairman.get("capital_flow_audit")
    if not audit:
        chairman["capital_flow_audit"] = audit = {"liquidated_tickers": [], "target_tickers": []}
    liquidated = list(audit.get("liquidated_tickers") or [])
    sym = victim["symbol"]
    if sym not in liquidated:
        liquidated.append(sym)
    audit["liquidated_tickers"] = liquidated
    return chairman


def apply_max_three_buys(
    chairman: dict,
    summaries: dict[str, SymbolVoteSummary] | None = None,
    *,
    max_buys: int = MAX_DAILY_BUYS,
) -> dict:
    """Keep top ``max_buys`` equity Buy mandates by board conviction; demote the rest."""
    ranked: list[tuple[int, str, dict]] = []
    for section_key in ("portfolio_positions", "watchlist_positions"):
        for pos in chairman.get(section_key) or []:
            sym = (pos.get("symbol") or "").strip()
            if not sym or _is_hedge_symbol(sym):
                continue
            if _normalize_verdict(pos.get("final_verdict", "")) not in BUY_VERDICTS:
                continue
            conviction = int(pos.get("aggregate_conviction_score") or 0)
            ranked_score = conviction
            if summaries and sym in summaries:
                ranked_score = _buy_rank_score(summaries[sym])
                pos["aggregate_conviction_score"] = ranked_score
            ranked.append((ranked_score, section_key, pos))

    ranked.sort(key=lambda item: (-item[0], item[2].get("symbol", "")))
    kept_symbols = {item[2]["symbol"] for item in ranked[:max_buys]}

    for conviction, section_key, pos in ranked[max_buys:]:
        demote_to = "Hold" if section_key == "portfolio_positions" else "Pass"
        pos["final_verdict"] = demote_to
        _prepend_override(
            pos,
            f"[VOTE ENGINE] Surplus majority buy demoted (max {max_buys} equity buys; "
            f"conviction {conviction}). Assigned {demote_to}.",
        )

    audit = chairman.get("capital_flow_audit")
    if not audit:
        chairman["capital_flow_audit"] = audit = {"liquidated_tickers": [], "target_tickers": []}
    targets = [sym for sym in (audit.get("target_tickers") or []) if sym in kept_symbols or _is_hedge_symbol(sym)]
    for sym in kept_symbols:
        if sym not in targets:
            targets.append(sym)
    if not any(_is_hedge_symbol(t) for t in targets):
        targets.insert(0, "TLT")
    audit["target_tickers"] = targets
    return chairman


def enforce_alpha_pick_from_executed_buys(
    chairman: dict,
    raw_verdicts: dict[str, dict] | None,
    all_symbols: list[str],
    *,
    portfolio_symbols: set[str] | None = None,
) -> dict:
    """Overwrite alpha_pick from executed Buy rows (guards against LLM chairman errors)."""
    if not chairman or not raw_verdicts:
        return chairman
    summaries = build_vote_summaries(
        raw_verdicts, all_symbols, portfolio_symbols=portfolio_symbols or set(),
    )
    chairman["alpha_pick"] = _pick_alpha_pick_from_chairman(chairman, summaries)
    return chairman


def build_chairman_allocation(
    raw_verdicts: dict[str, dict] | None,
    all_symbols: list[str],
    *,
    portfolio_symbols: set[str],
    watchlist_symbols: set[str],
) -> dict:
    """ChairmanMasterSynthesis from vote_engine — board majority days (Phase B).

    Per-symbol mandates from ``mandate_verdict``, max-3 equity buys by conviction,
    alpha pick from executed buys only. Chairman Pro is not invoked."""
    summaries = build_vote_summaries(raw_verdicts, all_symbols, portfolio_symbols=portfolio_symbols)
    portfolio_positions: list[dict] = []
    watchlist_positions: list[dict] = []
    target_tickers: list[str] = ["TLT"]

    for sym, summary in sorted(summaries.items()):
        final = mandate_verdict(summary)
        members, conviction = _supporting_for_mandate(summary, final)
        row = {
            "symbol": sym,
            "final_verdict": final,
            "synthesis": (
                "[VOTE ENGINE] Deterministic mandate from Round 2 panel votes "
                f"(buy_side={summary.buy_side_count()}/5, "
                f"sell_side={summary.sell_side_count()}/5)."
            ),
            "narrative": _default_narrative(members[0] if members else "Board"),
            "supporting_members": members,
            "aggregate_conviction_score": conviction,
        }
        if sym in portfolio_symbols:
            portfolio_positions.append(row)
        else:
            watchlist_positions.append(row)
        if _normalize_verdict(final) in BUY_VERDICTS and sym not in target_tickers:
            target_tickers.append(sym)

    chairman: dict = {
        "chain_of_thought_scratchpad": "",
        "macro_view": (
            "Board-majority allocation day — verdicts follow Round 2 panel votes "
            "without chairman tie-break."
        ),
        "capital_allocation_narrative": (
            "Verdicts derived deterministically from Round 2 structured votes. "
            "Surplus majority buys demoted by conviction when over the max-3 cap. "
            "Mandatory TLT hedge included in target_tickers."
        ),
        "capital_flow_audit": {
            "liquidated_tickers": [
                sym for sym, s in summaries.items()
                if sym in portfolio_symbols
                and _normalize_verdict(mandate_verdict(s)) in ("TRIM", "SELL", "STRONG SELL")
            ],
            "target_tickers": target_tickers,
        },
        "portfolio_positions": portfolio_positions,
        "watchlist_positions": watchlist_positions,
        "alpha_pick": {"symbol": "N/A", "champion_quote": "Pending max-3 cap."},
        "upcoming_events": [],
    }

    chairman = apply_max_three_buys(chairman, summaries)
    chairman = ensure_funding_sell(
        chairman, summaries=summaries, portfolio_symbols=portfolio_symbols,
    )
    chairman["alpha_pick"] = _pick_alpha_pick_from_chairman(chairman, summaries)

    digest = format_vote_digest(summaries, portfolio_symbols=portfolio_symbols)
    chairman["chain_of_thought_scratchpad"] = (
        "PYTHON VOTE ENGINE ALLOCATION (Phase B): Board majorities resolved in Python; "
        "chairman executes panel mandates.\n\n"
        f"{digest}"
    )
    return chairman


def build_chairman_skeleton(
    raw_verdicts: dict[str, dict] | None,
    all_symbols: list[str],
    *,
    portfolio_symbols: set[str],
    watchlist_symbols: set[str],
) -> dict:
    """Backward-compatible alias for ``build_chairman_allocation``."""
    return build_chairman_allocation(
        raw_verdicts,
        all_symbols,
        portfolio_symbols=portfolio_symbols,
        watchlist_symbols=watchlist_symbols,
    )


def apply_conviction_scores(chairman: dict, raw_verdicts: dict[str, dict] | None) -> dict:
    """Recompute supporting_members and aggregate_conviction_score from Round 2 JSON."""
    if not raw_verdicts or not chairman:
        return chairman

    all_syms = set()
    for section in ("portfolio_positions", "watchlist_positions"):
        for pos in chairman.get(section) or []:
            sym = (pos.get("symbol") or "").strip()
            if sym:
                all_syms.add(sym)

    summaries = build_vote_summaries(raw_verdicts, list(all_syms))
    for section in ("portfolio_positions", "watchlist_positions"):
        for pos in chairman.get(section) or []:
            sym = (pos.get("symbol") or "").strip()
            summary = summaries.get(sym)
            if not summary:
                continue
            final = pos.get("final_verdict", "")
            members, conviction = _supporting_for_mandate(summary, final)
            if members:
                pos["supporting_members"] = members
            pos["aggregate_conviction_score"] = conviction
    return chairman
