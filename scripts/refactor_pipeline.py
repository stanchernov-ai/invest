import os

pipeline_code = """import logging
from src.data.db import fetch_query

logger = logging.getLogger(__name__)

async def process_portfolios(user_id="stan"):
    logger.info("Initializing database portfolio query.")
    master_ledger = {}
    
    query = \"\"\"
        SELECT p.symbol, p.shares, p.cost_basis, p.purchase_date,
               port.bucket_type, port.name as portfolio_name
        FROM positions p
        JOIN portfolios port ON p.portfolio_id = port.id
        WHERE port.user_id = $1
    \"\"\"
    try:
        rows = await fetch_query(query, user_id)
    except Exception as e:
        logger.error(f"Failed to query portfolios: {e}")
        return master_ledger, 0.0

    for row in rows:
        sym = row['symbol'].upper()
        shares = float(row['shares']) if row['shares'] else 0.0
        cost = float(row['cost_basis']) if row['cost_basis'] else 0.0
        b_type = str(row['bucket_type']).lower()
        p_date = row['purchase_date'].isoformat() if row['purchase_date'] else "Unknown"

        if sym not in master_ledger:
            master_ledger[sym] = {
                "Shares": 0.0, "Total": 0.0, "Cost_Basis": 0.0,
                "Taxable": 0.0, "Roth": 0.0, "401K": 0.0,
                "Name": sym, "Recent_Activity": "Hold",
                "Purchase_Date": p_date,
                "_shares_by_bucket": {"taxable": 0.0, "roth": 0.0, "401k": 0.0, "custom": 0.0}
            }
        
        master_ledger[sym]["Shares"] += shares
        master_ledger[sym]["Cost_Basis"] += cost
        if b_type in master_ledger[sym]["_shares_by_bucket"]:
            master_ledger[sym]["_shares_by_bucket"][b_type] += shares
        else:
            master_ledger[sym]["_shares_by_bucket"]["custom"] += shares

    # We return total_portfolio_value = 0.0 here, prepare.py will compute it properly
    return master_ledger, 0.0

async def build_account_holdings(user_id="stan"):
    \"\"\"Build symbol-level holdings grouped by individual account for the per-account
    allocation pie charts.
    Returns: {account_name: {symbol: {"value": float, "return_pct": float, "shares": float}}}
    \"\"\"
    holdings = {}
    
    query = \"\"\"
        SELECT p.symbol, p.shares, p.cost_basis, port.name as portfolio_name
        FROM positions p
        JOIN portfolios port ON p.portfolio_id = port.id
        WHERE port.user_id = $1
    \"\"\"
    try:
        rows = await fetch_query(query, user_id)
    except Exception as e:
        logger.error(f"Failed to query account holdings: {e}")
        return holdings

    for row in rows:
        acct = row['portfolio_name']
        sym = row['symbol'].upper()
        shares = float(row['shares']) if row['shares'] else 0.0
        cost = float(row['cost_basis']) if row['cost_basis'] else 0.0
        
        if acct not in holdings:
            holdings[acct] = {}
        
        if sym not in holdings[acct]:
            holdings[acct][sym] = {"value": 0.0, "return_pct": 0.0, "shares": 0.0, "cost": 0.0}
            
        holdings[acct][sym]["shares"] += shares
        holdings[acct][sym]["cost"] += cost
        
    return holdings
"""

with open("src/pipeline.py", "w", encoding="utf-8") as f:
    f.write(pipeline_code)
