import logging

logger = logging.getLogger(__name__)

async def collect_symbol_universe(user_id="stan") -> set:
    """Tradeable symbols from current holdings. History CSVs are deprecated."""
    from src.pipeline import build_account_holdings
    holdings = await build_account_holdings(user_id=user_id)
    universe = set()
    for acct, syms in holdings.items():
        for sym in syms.keys():
            universe.add(sym)
    return universe

async def build_account_returns(
    data_dir=None, api_key=None, session=None, window_days=370, eod_cache=None, user_id="stan"
):
    """History engine based on CSVs is deprecated per legal team. 
    Returns empty structures to prevent pipeline crashes.
    """
    logger.info("History engine CSV logic deprecated. Returning empty returns structure.")
    return {
        "updated": "Unknown",
        "method": "deprecated",
        "basis": "none",
        "returns": {},
        "daily_total": {},
        "benchmark_history": {},
    }
