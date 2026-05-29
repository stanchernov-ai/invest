"""Deterministic pre-flight price gate (Layer 2).

Replaces the former Flash LLM Data Oracle. The only kill switch is a zero or
missing Current Price on portfolio or watchlist assets — N/A secondary metrics
are ignored, matching the original oracle mandate.
"""
from pydantic import BaseModel


class DataOracleReport(BaseModel):
    is_valid: bool
    reason: str


def build_price_feed(
    master_ledger: dict,
    watchlist_data: dict,
    advanced_data: dict,
) -> dict[str, float]:
    """Collect live prices for every asset that appears in the board mega-prompt."""
    prices: dict[str, float] = {}

    for sym, data in master_ledger.items():
        adv = advanced_data.get(sym, {})
        shares = data.get("Shares", 0.0) or 0.0
        raw = adv.get("current_price")
        if raw is not None:
            try:
                prices[sym] = float(raw)
                continue
            except (TypeError, ValueError):
                pass
        total = data.get("Total", 0.0) or 0.0
        prices[sym] = (total / shares) if shares > 0 else 0.0

    for sym, d in watchlist_data.items():
        try:
            prices[sym] = float(d.get("price", 0.0))
        except (TypeError, ValueError):
            prices[sym] = 0.0

    return prices


def validate_price_feed(prices: dict[str, float]) -> dict:
    """Return {'is_valid', 'reason'} — abort the run when any price is <= $0."""
    if not prices:
        return {
            "is_valid": False,
            "reason": "Price feed is empty; no portfolio or watchlist assets to validate.",
        }

    bad = sorted(sym for sym, price in prices.items() if price is None or price <= 0.0)
    if bad:
        return {
            "is_valid": False,
            "reason": f"Current Price is $0.00 or missing for: {', '.join(bad)}.",
        }

    return {
        "is_valid": True,
        "reason": f"All {len(prices)} portfolio/watchlist assets have Current Price > $0.00.",
    }
