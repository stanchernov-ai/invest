"""Deterministic chairman guardrails (Layer 2 — authoritative).

Financial limits must be enforced in Python, not trusted to LLM prompts alone.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime

from src.config.settings import now_local

MAX_DAILY_BUYS = 3
WASH_SALE_DAYS = 30

BUY_VERDICTS = frozenset({"ACCUMULATE CANDIDATE", "HIGH CONVICTION (OVERWEIGHT)"})
SELL_VERDICTS = frozenset({"BEARISH (LIQUIDATE)", "STRONG BEARISH (LIQUIDATE)", "REDUCE EXPOSURE"})
HEDGE_SYMBOLS = frozenset({"TLT", "VXX"})

_DATE_FORMATS = (
    "%m/%d/%Y",
    "%Y-%m-%d",
    "%m/%d/%y",
    "%b %d, %Y",
    "%B %d, %Y",
)


def _normalize_verdict(verdict: str) -> str:
    return (verdict or "").upper().strip()


def _parse_purchase_date(date_str: str, ref: datetime) -> datetime | None:
    if not date_str or str(date_str).strip().lower() in ("unknown", "n/a", ""):
        return None
    text = str(date_str).strip()
    for fmt in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt)
            if ref.tzinfo is not None:
                return parsed.replace(tzinfo=ref.tzinfo)
            return parsed
        except ValueError:
            continue
    return None


def _within_wash_sale_window(purchase_date: str, ref: datetime | None = None) -> bool:
    ref = ref or now_local()
    parsed = _parse_purchase_date(purchase_date, ref)
    if parsed is None:
        return False
    days = (ref.date() - parsed.date()).days
    return 0 <= days < WASH_SALE_DAYS


def _prepend_override(pos: dict, message: str) -> None:
    pos["synthesis"] = f"{message} {pos.get('synthesis', '')}"


def _is_hedge_symbol(symbol: str) -> bool:
    return str(symbol or "").upper() in HEDGE_SYMBOLS


def count_equity_buys(chairman: dict) -> int:
    """Accumulate Candidate/High Conviction (Overweight) equity positions only (TLT/VXX hedge excluded from the cap)."""
    count = 0
    for section in ("portfolio_positions", "watchlist_positions"):
        for pos in chairman.get(section) or []:
            sym = pos.get("symbol", "")
            if _is_hedge_symbol(sym):
                continue
            if _normalize_verdict(pos.get("final_verdict", "")) in BUY_VERDICTS:
                count += 1
    return count


def enforce_max_buys(chairman: dict, *, max_buys: int = MAX_DAILY_BUYS) -> dict:
    """Keep at most ``max_buys`` equity Accumulate Candidate/High Conviction (Overweight) verdicts; demote the rest by conviction.

    Mandatory hedge symbols (TLT/VXX) are exempt from the buy cap and are always
    preserved in ``capital_flow_audit.target_tickers`` so the compliance gate can
    verify hedge execution."""
    ranked: list[tuple[int, str, int, dict]] = []
    for section_key in ("portfolio_positions", "watchlist_positions"):
        for idx, pos in enumerate(chairman.get(section_key, [])):
            sym = pos.get("symbol", "")
            if _normalize_verdict(pos.get("final_verdict", "")) in BUY_VERDICTS:
                if _is_hedge_symbol(sym):
                    continue
                ranked.append((
                    int(pos.get("aggregate_conviction_score") or 0),
                    section_key,
                    idx,
                    pos,
                ))

    ranked.sort(key=lambda item: (-item[0], item[3].get("symbol", "")))
    kept_symbols = {item[3]["symbol"] for item in ranked[:max_buys]}

    for score, section_key, idx, pos in ranked[max_buys:]:
        demote_to = "Hold" if section_key == "portfolio_positions" else "Pass"
        pos["final_verdict"] = demote_to
        _prepend_override(
            pos,
            f"[SYSTEM OVERRIDE: Maximum {max_buys} Buys limit (conviction {score}). Demoted to {demote_to}.]",
        )

    audit = chairman.get("capital_flow_audit")
    if audit and "target_tickers" in audit:
        audit["target_tickers"] = [
            sym for sym in audit.get("target_tickers", [])
            if sym in kept_symbols or _is_hedge_symbol(sym)
        ]

    return chairman


def enforce_wash_sale(
    chairman: dict,
    purchase_dates: dict[str, str],
    *,
    ref: datetime | None = None,
    wash_days: int = WASH_SALE_DAYS,
) -> dict:
    """Block Bearish (Liquidate)/Reduce Exposure on assets purchased within the wash-sale window."""
    ref = ref or now_local()
    pos_dict = {p["symbol"]: p for p in chairman.get("portfolio_positions", [])}
    blocked: set[str] = set()

    for sym, pos in pos_dict.items():
        verdict = _normalize_verdict(pos.get("final_verdict", ""))
        if verdict not in SELL_VERDICTS:
            continue
        purchase_date = purchase_dates.get(sym, "Unknown")
        if not _within_wash_sale_window(purchase_date, ref):
            continue
        pos["final_verdict"] = "HOLD"
        _prepend_override(
            pos,
            f"[SYSTEM OVERRIDE: Wash-Sale Rule — purchased {purchase_date} "
            f"(<{wash_days} days). Bearish (Liquidate)/Reduce Exposure blocked.]",
        )
        blocked.add(sym)

    audit = chairman.get("capital_flow_audit")
    if audit and blocked:
        audit["liquidated_tickers"] = [
            sym for sym in audit.get("liquidated_tickers", []) if sym not in blocked
        ]

    return chairman


def enforce_liquidation_cap(
    chairman: dict,
    *,
    total_portfolio_value: float,
    portfolio_holdings: dict[str, float],
    cap_pct: float | None = None,
) -> dict:
    """Cap total Bearish (Liquidate)/Reduce Exposure notional to ``cap_pct`` of portfolio value."""
    from src.config.settings import LIQUIDATION_CAP_PCT

    if cap_pct is None:
        cap_pct = LIQUIDATION_CAP_PCT
    if not chairman.get("capital_flow_audit"):
        return chairman

    cap_remaining = total_portfolio_value * cap_pct
    liquidations = chairman["capital_flow_audit"].get("liquidated_tickers", [])
    pos_dict = {p["symbol"]: p for p in chairman.get("portfolio_positions", [])}
    valid_liquidations: list[str] = []

    for sym in liquidations:
        if sym not in pos_dict:
            continue
        pos = pos_dict[sym]
        verdict = _normalize_verdict(pos.get("final_verdict", ""))
        if verdict not in SELL_VERDICTS:
            continue

        holding_value = float(portfolio_holdings.get(sym, 0.0) or 0.0)
        if holding_value <= 0:
            continue

        if cap_remaining <= 0:
            # CHAIR-1: board reduce mandates stay REDUCE EXPOSURE when cap is exhausted — never demote to HOLD.
            if verdict != "REDUCE EXPOSURE":
                pos["final_verdict"] = "Reduce Exposure"
            _prepend_override(
                pos,
                "[SYSTEM OVERRIDE: 10% Liquidation Cap Reached. Fractional trim only — "
                "remaining allowance $0.]",
            )
            valid_liquidations.append(sym)
            continue

        if verdict == "BEARISH (LIQUIDATE)" and holding_value > cap_remaining:
            pos["final_verdict"] = "Reduce Exposure"
            _prepend_override(
                pos,
                f"[SYSTEM OVERRIDE: Bearish (Liquidate) mathematically capped at ${cap_remaining:,.2f} "
                f"to respect 10% limit. Converted to fractional trim.]",
            )
            cap_remaining = 0
            valid_liquidations.append(sym)
        else:
            deduction = holding_value if verdict == "BEARISH (LIQUIDATE)" else (holding_value / 2.0)
            if deduction > cap_remaining:
                _prepend_override(
                    pos,
                    f"[SYSTEM OVERRIDE: Reduce Exposure mathematically capped at ${cap_remaining:,.2f} "
                    f"to respect 10% limit.]",
                )
                cap_remaining = 0
            else:
                cap_remaining -= deduction
            valid_liquidations.append(sym)

    for sym, pos in pos_dict.items():
        if _normalize_verdict(pos.get("final_verdict", "")) in SELL_VERDICTS and sym not in valid_liquidations:
            pos["final_verdict"] = "Reduce Exposure"
            _prepend_override(
                pos,
                "[SYSTEM OVERRIDE: 10% Liquidation Cap Reached. Deferred trim — cap exhausted.]",
            )
            valid_liquidations.append(sym)

    chairman["capital_flow_audit"]["liquidated_tickers"] = valid_liquidations
    return chairman


def apply_chairman_guardrails(
    chairman: dict,
    *,
    total_portfolio_value: float,
    portfolio_holdings: dict[str, float],
    purchase_dates: dict[str, str] | None = None,
    ref: datetime | None = None,
    raw_verdicts: dict[str, dict] | None = None,
    all_symbols: list[str] | None = None,
    user_profile: dict | None = None,
) -> dict:
    """Apply all P0 chairman guardrails in deterministic order."""
    from src.core.chairman_alignment import apply_board_and_cap_coherence
    from src.core.portfolio_policy import resolve_policy
    
    policy = resolve_policy(user_profile)

    result = deepcopy(chairman)
    enforce_max_buys(result, max_buys=policy.max_daily_buys)
    portfolio_symbols = set((portfolio_holdings or {}).keys())
    universe = set(all_symbols or []) | portfolio_symbols
    watchlist_symbols = universe - portfolio_symbols
    apply_board_and_cap_coherence(
        result,
        raw_verdicts,
        portfolio_symbols=portfolio_symbols,
        watchlist_symbols=watchlist_symbols,
    )
    from src.core.vote_engine import ensure_funding_sell

    ensure_funding_sell(
        result,
        portfolio_symbols=portfolio_symbols,
        raw_verdicts=raw_verdicts,
        all_symbols=list(universe),
    )
    enforce_wash_sale(result, purchase_dates or {}, ref=ref)
    enforce_liquidation_cap(
        result,
        total_portfolio_value=total_portfolio_value,
        portfolio_holdings=portfolio_holdings,
        cap_pct=policy.liquidation_cap_pct,
    )
    return result
