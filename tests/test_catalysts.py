"""Tests for deterministic catalyst enrichment."""
from datetime import date

from src.core.catalysts import (
    build_upcoming_events_from_advanced_data,
    catalyst_symbol_universe,
    ensure_chairman_catalysts,
)


def test_build_events_from_earnings_dates():
    advanced = {
        "NVDA": {
            "next_earnings": "2026-06-05",
            "fcs_score": 3,
            "fcs_rationale": "Imminent Earnings Catalyst (+1)",
            "eps_estimated": 1.25,
        },
        "META": {
            "next_earnings": "2026-07-29",
            "fcs_score": 4,
            "fcs_rationale": "High Implied Upside (+2)",
            "eps_estimated": "N/A",
        },
        "QQQ": {"next_earnings": "Unknown", "fcs_rationale": "ETF Structural Exemption."},
    }
    events = build_upcoming_events_from_advanced_data(
        advanced,
        {"NVDA", "META", "QQQ"},
        as_of=date(2026, 5, 30),
        horizon_days=90,
    )
    assert len(events) == 2
    assert events[0]["symbol"] == "NVDA"
    assert "2026-06-05" in events[0]["event_detail"]
    assert "Imminent Earnings" in events[0]["impact"]


def test_ensure_chairman_catalysts_skips_when_present():
    chairman = {"upcoming_events": [{"symbol": "AAPL", "event_detail": "x", "impact": "y"}]}
    out = ensure_chairman_catalysts(chairman, {"AAPL": {"next_earnings": "2026-06-01"}}, set())
    assert out is chairman


def test_ensure_chairman_catalysts_fills_empty():
    chairman = {
        "portfolio_positions": [{"symbol": "NVDA"}],
        "watchlist_positions": [],
        "upcoming_events": [],
    }
    advanced = {
        "NVDA": {
            "next_earnings": "2026-06-05",
            "fcs_score": 2,
            "fcs_rationale": "Bullish Analyst Consensus (+2)",
        },
    }
    out = ensure_chairman_catalysts(chairman, advanced, {"NVDA"})
    assert len(out["upcoming_events"]) == 1
    assert out["upcoming_events"][0]["symbol"] == "NVDA"


def test_catalyst_symbol_universe_excludes_benchmarks():
    chairman = {
        "portfolio_positions": [{"symbol": "QQQ"}, {"symbol": "NVDA"}],
        "watchlist_positions": [],
    }
    syms = catalyst_symbol_universe(chairman, {"SPY"})
    assert syms == {"NVDA"}
