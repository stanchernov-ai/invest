"""Review universe for watchlist debate — manual, Mag7, and Yahoo discovery.

Merged at prepare time; symbols not owned are debated as watchlist (Alpha Pick eligible).
"""
from __future__ import annotations

import json
import logging
import os
from typing import Iterable

from src.config.settings import DATA_DIR
from src import scout

logger = logging.getLogger(__name__)

# Product SSOT — always reviewed when not in portfolio (debated as watchlist, not removable).
MAGNIFICENT_SEVEN: tuple[str, ...] = (
    "AAPL",
    "MSFT",
    "GOOGL",
    "AMZN",
    "NVDA",
    "META",
    "TSLA",
)

# Treat either share class as "owned" for Mag7 dedupe.
_SYMBOL_CLASS_ALIASES: dict[str, str] = {
    "GOOG": "GOOGL",
    "GOOGL": "GOOG",
}

WATCHLIST_ENTRY_DEFAULTS = {"price": 0.0}


def normalize_symbol(symbol: str | None) -> str:
    return (symbol or "").strip().upper()


def _normalize_portfolio(portfolio_symbols: Iterable[str]) -> set[str]:
    return {normalize_symbol(s) for s in portfolio_symbols if normalize_symbol(s)}


def is_owned(symbol: str, portfolio_symbols: set[str]) -> bool:
    """True when symbol or its share-class alias is held."""
    sym = normalize_symbol(symbol)
    if not sym:
        return True
    if sym in portfolio_symbols:
        return True
    alias = _SYMBOL_CLASS_ALIASES.get(sym)
    return bool(alias and alias in portfolio_symbols)


def load_manual_watchlist(data_dir: str | None = None) -> dict[str, dict]:
    """Optional operator-curated names (Phase 1 file; Postgres in Phase 2)."""
    data_dir = data_dir or DATA_DIR
    path = os.path.join(data_dir, "manual_watchlist.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        logger.warning("Could not read manual_watchlist.json.")
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict] = {}
    for sym, meta in raw.items():
        key = normalize_symbol(sym)
        if not key:
            continue
        entry = dict(meta) if isinstance(meta, dict) else {}
        entry.setdefault("source", "manual")
        entry.setdefault("price", 0.0)
        out[key] = entry
    return out


def _mag7_entries(portfolio_symbols: set[str]) -> dict[str, dict]:
    entries: dict[str, dict] = {}
    for sym in MAGNIFICENT_SEVEN:
        if is_owned(sym, portfolio_symbols):
            continue
        entries[sym] = {"source": "mag7", **WATCHLIST_ENTRY_DEFAULTS}
    return entries


def build_review_universe(
    portfolio_symbols: Iterable[str],
    *,
    manual_watchlist: dict[str, dict] | None = None,
    verdicts_history: dict | None = None,
    include_mag7: bool = True,
    include_yahoo: bool = True,
    yahoo_max_symbols: int = 15,
    data_dir: str | None = None,
) -> dict[str, dict]:
    """Build watchlist debate universe: manual ∪ Mag7 ∪ Yahoo, minus portfolio holdings.

    Returns the same shape as legacy ``daily_target_list.json`` entries:
    ``{symbol: {"source": str, "price": float, ...}}``.

    Pass cooldown applies to Yahoo discovery only — Mag7 and manual are never suppressed.
    """
    data_dir = data_dir or DATA_DIR
    owned = _normalize_portfolio(portfolio_symbols)

    merged: dict[str, dict] = {}

    manual = manual_watchlist if manual_watchlist is not None else load_manual_watchlist(data_dir)
    for sym, meta in manual.items():
        key = normalize_symbol(sym)
        if not key or is_owned(key, owned):
            continue
        entry = dict(meta)
        entry.setdefault("source", "manual")
        entry.setdefault("price", 0.0)
        merged[key] = entry

    if include_mag7:
        for sym, entry in _mag7_entries(owned).items():
            merged.setdefault(sym, dict(entry))

    if include_yahoo:
        if verdicts_history is None:
            verdicts_path = os.path.join(data_dir, "board_verdicts.json")
            verdicts_history = scout.load_json(verdicts_path)
        cooldown = scout.build_pass_cooldown_set(verdicts_history or {})
        yahoo = scout.build_yahoo_discovery(
            owned,
            cooldown,
            max_symbols=yahoo_max_symbols,
            data_dir=data_dir,
        )
        for sym, entry in yahoo.items():
            if is_owned(sym, owned):
                continue
            merged.setdefault(sym, dict(entry))

    logger.info(
        "Review universe: %d watchlist symbol(s) "
        "(manual=%d mag7=%d yahoo=%d after merge).",
        len(merged),
        sum(1 for v in merged.values() if v.get("source") == "manual"),
        sum(1 for v in merged.values() if v.get("source") == "mag7"),
        sum(1 for v in merged.values() if v.get("source") in ("yahoo", "Autonomous Scout Engine")),
    )
    return merged


def persist_daily_target_list(watchlist: dict[str, dict], data_dir: str | None = None) -> None:
    """Write merged universe for ops/debug (replaces legacy Scout-only file)."""
    data_dir = data_dir or DATA_DIR
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, "daily_target_list.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(watchlist, f, indent=4)
