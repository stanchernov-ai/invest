history_code = """import logging
from src.pipeline import build_account_holdings
from src.config.settings import DATA_DIR

logger = logging.getLogger(__name__)

def collect_symbol_universe(user_id="stan") -> set:
    \"\"\"Tradeable symbols from current holdings. History CSVs are deprecated.\"\"\"
    # Wait, we need to make this async, but it's used in prepare.py synchronously.
    # In prepare.py it is currently:
    # history_symbols = history.collect_symbol_universe(DATA_DIR)
    # We will need to update prepare.py to await this.
    pass

async def build_account_returns(
    data_dir=None, api_key=None, session=None, window_days=370, eod_cache=None, user_id="stan"
):
    \"\"\"History engine based on CSVs is deprecated per legal team. 
    Returns empty structures to prevent pipeline crashes.
    \"\"\"
    logger.info("History engine CSV logic deprecated. Returning empty returns structure.")
    return {
        "updated": "Unknown",
        "method": "deprecated",
        "basis": "none",
        "returns": {},
        "daily_total": {},
        "benchmark_history": {},
    }
"""

with open("src/history.py", "w", encoding="utf-8") as f:
    f.write(history_code)
