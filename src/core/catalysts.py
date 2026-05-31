"""Deterministic upcoming catalysts from FMP advanced metrics (prepare phase)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

EARNINGS_DATE_FMT = "%Y-%m-%d"
_BENCHMARK_OR_HEDGE = frozenset({"QQQ", "SPY", "TLT", "VXX"})
_GENERIC_FCS = frozenset({
    "ETF Structural Exemption.",
    "No major forward catalysts identified.",
})


def catalyst_symbol_universe(
    chairman_data: dict,
    portfolio_symbols: set[str] | None = None,
) -> set[str]:
    """Portfolio + watchlist symbols eligible for catalyst surfacing."""
    syms: set[str] = set()
    for pos in (chairman_data.get("portfolio_positions") or []) + (
        chairman_data.get("watchlist_positions") or []
    ):
        sym = (pos.get("symbol") or "").strip().upper()
        if sym and sym not in ("N/A", "NONE"):
            syms.add(sym)
    if portfolio_symbols:
        syms |= {str(s).strip().upper() for s in portfolio_symbols if s}
    return syms - _BENCHMARK_OR_HEDGE


def _parse_earnings_date(raw: str) -> date | None:
    text = (raw or "").strip()
    if not text or text.lower() == "unknown":
        return None
    try:
        return datetime.strptime(text, EARNINGS_DATE_FMT).date()
    except ValueError:
        return None


def _build_impact(adv: dict) -> str:
    rationale = (adv.get("fcs_rationale") or "").strip()
    if rationale and rationale not in _GENERIC_FCS:
        return rationale
    eps = adv.get("eps_estimated")
    if eps not in (None, "", "N/A"):
        return (
            f"Consensus EPS estimate {eps}. "
            "The report may reset sentiment and implied volatility for this name."
        )
    return "Upcoming earnings may materially reset sentiment and implied volatility for this name."


def build_upcoming_events_from_advanced_data(
    advanced_data: dict,
    symbols: set[str] | list[str],
    *,
    horizon_days: int = 90,
    limit: int = 12,
    as_of: date | None = None,
) -> list[dict]:
    """Build chairman-style upcoming_events from prepare-phase FMP metrics."""
    if not advanced_data:
        return []
    today = as_of or date.today()
    horizon = today + timedelta(days=horizon_days)
    candidates: list[tuple[date, str, dict]] = []

    for sym in symbols or []:
        key = str(sym).strip().upper()
        if not key or key in _BENCHMARK_OR_HEDGE:
            continue
        adv = advanced_data.get(key) or advanced_data.get(key.replace(".", "-"))
        if not adv:
            continue
        earn_date = _parse_earnings_date(adv.get("next_earnings", ""))
        if not earn_date or earn_date < today or earn_date > horizon:
            continue
        candidates.append((earn_date, key, adv))

    candidates.sort(key=lambda row: (row[0], -int(row[2].get("fcs_score") or 0), row[1]))

    events: list[dict] = []
    for earn_date, sym, adv in candidates[:limit]:
        detail = f"Next Earnings: {earn_date.isoformat()}"
        eps = adv.get("eps_estimated")
        if eps not in (None, "", "N/A"):
            detail += f" (EPS est. {eps})"
        events.append({
            "symbol": sym,
            "event_detail": detail,
            "impact": _build_impact(adv),
        })
    return events


def ensure_chairman_catalysts(
    chairman_data: dict,
    advanced_data: dict | None,
    portfolio_symbols: set[str] | None = None,
) -> dict:
    """Fill upcoming_events when chairman/vote-engine left the list empty."""
    if not chairman_data or chairman_data.get("upcoming_events"):
        return chairman_data
    symbols = catalyst_symbol_universe(chairman_data, portfolio_symbols)
    events = build_upcoming_events_from_advanced_data(advanced_data or {}, symbols)
    if not events:
        return chairman_data
    enriched = dict(chairman_data)
    enriched["upcoming_events"] = events
    return enriched
