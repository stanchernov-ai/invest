import os
import json
import logging
import csv
import re
import glob

from src.config.settings import DATA_DIR

logger = logging.getLogger(__name__)

def clean_num(val_str):
    if not val_str or str(val_str).strip() == "" or str(val_str).strip().lower() in ["n/a", "none"]:
        return 0.0
    pattern = r'[^\d\.' + chr(45) + ']'
    cleaned = re.sub(pattern, '', str(val_str))
    try:
        return float(cleaned or 0.0)
    except ValueError:
        return 0.0

def parse_activity_dates():
    data_dir = DATA_DIR
    purchase_dates = {}
    for file in glob.glob(os.path.join(data_dir, "*.csv")):
        if "activity" not in file.lower():
            continue
        try:
            enc = "utf" + chr(45) + "8" + chr(45) + "sig"
            with open(file, mode="r", encoding=enc) as f:
                lines = f.readlines()
            
            header_idx = ~0 + 1
            for i, line in enumerate(lines):
                line_lower = line.lower()
                if "symbol" in line_lower and ("date" in line_lower or "run date" in line_lower):
                    header_idx = i
                    break
            
            if header_idx < 0: continue
            
            reader = csv.DictReader(lines[header_idx:])
            for row in reader:
                sym_key = next((k for k in row.keys() if k and "symbol" in str(k).lower()), None)
                action_key = next((k for k in row.keys() if k and ("action" in str(k).lower() or "transaction" in str(k).lower())), None)
                date_key = next((k for k in row.keys() if k and "date" in str(k).lower()), None)
                
                if not sym_key or not action_key or not date_key: continue
                
                sym = str(row[sym_key]).strip().upper()
                action = str(row[action_key]).strip().lower()
                date_str = str(row[date_key]).strip()
                
                if not sym or "buy" not in action: continue
                
                if sym not in purchase_dates:
                    purchase_dates[sym] = date_str
        except Exception:
            pass
    return purchase_dates

def parse_broker_csv(filepath, broker_type):
    positions = {}
    try:
        enc = "utf" + chr(45) + "8" + chr(45) + "sig"
        with open(filepath, mode="r", encoding=enc) as f:
            lines = f.readlines()
            
        header_idx = ~0 + 1
        found = False
        for i, line in enumerate(lines):
            line_lower = line.lower()
            if "symbol" in line_lower and ("value" in line_lower or "last price" in line_lower):
                if broker_type == "etrade" and "sort by" in line_lower:
                    continue
                header_idx = i
                found = True
                break
                
        if not found:
            logger.warning("Header not found in file.")
            return positions
            
        reader = csv.DictReader(lines[header_idx:])
        for row in reader:
            sym_key = next((k for k in row.keys() if k and "symbol" in str(k).lower()), None)
            if not sym_key: continue
            
            raw_sym = row.get(sym_key)
            sym = str(raw_sym).strip().upper() if raw_sym else ""
            
            if not sym or sym == "NAN" or sym in ["CASH", "CORE", "TOTAL", "PENDING"]: continue
            if "**" in sym or "FDRXX" in sym or "SPAXX" in sym: continue
            
            val_raw, cost_raw, shares_raw = "0", "0", "0"
            name_raw = sym
            
            for key, val in row.items():
                if not key or not val: continue
                k_lower = str(key).lower().strip()
                
                if k_lower in ["value $", "current value", "value"]:
                    val_raw = val
                elif k_lower in ["price paid $", "price paid"]:
                    qty_key = next((k for k in row.keys() if k and "quantity" in str(k).lower()), None)
                    qty_val = row.get(qty_key, "0") if qty_key else "0"
                    cost_raw = str(clean_num(val) * clean_num(qty_val))
                elif k_lower in ["cost basis total", "cost basis"]:
                    cost_raw = val
                elif k_lower in ["quantity"]:
                    shares_raw = val
                elif k_lower in ["description", "name"]:
                    name_raw = val
            
            val_float = clean_num(val_raw)
            cost_float = clean_num(cost_raw)
            shares_float = clean_num(shares_raw)
            
            if val_float == 0 and cost_float == 0:
                continue
                
            positions[sym] = {
                "Shares": shares_float,
                "Total": val_float,
                "Cost_Basis": cost_float,
                "Name": name_raw
            }
    except Exception:
        logger.error("CSV native parsing failure.")
    return positions

def process_portfolios():
    logger.info("Initializing native dictionary brokerage data parsing engine.")
    master_ledger = {}
    total_portfolio_value = 0.0

    data_dir = DATA_DIR
    os.makedirs(data_dir, exist_ok=True)
    
    purchase_dates = parse_activity_dates()

    for file in glob.glob(os.path.join(data_dir, "*.csv")):
        file_lower = file.lower()
        if "activity" in file_lower:
            continue
            
        acc_type = "Taxable"
        if "roth" in file_lower:
            acc_type = "Roth"
        elif "401k" in file_lower:
            acc_type = "401K"
            
        broker = "fidelity" if "fidelity" in file_lower else "etrade"
        positions = parse_broker_csv(file, broker)
        
        for sym, p_data in positions.items():
            if sym not in master_ledger:
                master_ledger[sym] = {
                    "Shares": 0.0, "Total": 0.0, "Cost_Basis": 0.0,
                    "Taxable": 0.0, "Roth": 0.0, "401K": 0.0,
                    "Name": p_data["Name"], "Recent_Activity": "Hold",
                    "Purchase_Date": purchase_dates.get(sym, "Unknown")
                }
            master_ledger[sym]["Shares"] += p_data["Shares"]
            master_ledger[sym]["Total"] += p_data["Total"]
            master_ledger[sym]["Cost_Basis"] += p_data["Cost_Basis"]
            master_ledger[sym][acc_type] += p_data["Total"]
            total_portfolio_value += p_data["Total"]

    for sym, data in master_ledger.items():
        data["Unrealized"] = data["Total"] - data["Cost_Basis"]
        data["Personal_Return_Pct"] = (data["Unrealized"] / data["Cost_Basis"]) * 100 if data["Cost_Basis"] > 0 else 0.0

    logger.info("Brokerage parsing complete. Master ledger synchronized successfully.")
    return master_ledger, total_portfolio_value


# Display order for the per-account allocation charts.
ACCOUNT_ORDER = ["eTrade Taxable", "eTrade Roth IRA", "Fidelity 401K", "Fidelity Roth 401K"]

# Fidelity exports all sub-accounts in one file; map the "Account Name" column to
# Stan's preferred groupings (Fidelity 401K = WORKDAY 401(K) + BrokerageLink).
FIDELITY_ACCOUNT_MAP = {
    "workday 401(k)": "Fidelity 401K",
    "brokeragelink": "Fidelity 401K",
    "brokeragelink roth": "Fidelity Roth 401K",
}


def _get_col(row, names):
    names_l = [n.lower() for n in names]
    for key, val in row.items():
        if key and str(key).lower().strip() in names_l:
            return val
    return ""


def build_account_holdings(data_dir=None):
    """Build symbol-level holdings grouped by individual account for the per-account
    allocation pie charts. Independent of the master ledger's filename-derived
    Taxable/Roth/401K buckets (which cannot split the single Fidelity file).

    Returns: {account_name: {symbol: {"value": float, "return_pct": float}}}
    """
    data_dir = data_dir or DATA_DIR
    holdings = {acct: {} for acct in ACCOUNT_ORDER}
    enc = "utf" + chr(45) + "8" + chr(45) + "sig"

    for file in glob.glob(os.path.join(data_dir, "*.csv")):
        file_lower = file.lower()
        if "activity" in file_lower:
            continue
        broker = "fidelity" if "fidelity" in file_lower else "etrade"

        try:
            with open(file, mode="r", encoding=enc) as f:
                lines = f.readlines()
        except Exception:
            logger.warning("Could not read CSV for account holdings.")
            continue

        header_idx = -1
        for i, line in enumerate(lines):
            line_lower = line.lower()
            if "symbol" in line_lower and ("value" in line_lower or "last price" in line_lower):
                if broker == "etrade" and "sort by" in line_lower:
                    continue
                header_idx = i
                break
        if header_idx < 0:
            continue

        etrade_account = "eTrade Roth IRA" if "roth" in file_lower else "eTrade Taxable"

        reader = csv.DictReader(lines[header_idx:])
        for row in reader:
            sym_key = next((k for k in row.keys() if k and "symbol" in str(k).lower()), None)
            if not sym_key:
                continue
            raw_sym = row.get(sym_key)
            sym = str(raw_sym).strip().upper() if raw_sym else ""
            if not sym or sym == "NAN" or sym in ["CASH", "CORE", "TOTAL", "PENDING"]:
                continue
            if "**" in sym or "FDRXX" in sym or "SPAXX" in sym:
                continue

            if broker == "fidelity":
                acct_name = str(_get_col(row, ["account name"])).strip().lower()
                account = FIDELITY_ACCOUNT_MAP.get(acct_name)
                if not account:
                    continue
                value = clean_num(_get_col(row, ["current value", "value"]))
                ret = clean_num(_get_col(row, ["total gain/loss percent"]))
                shares = clean_num(_get_col(row, ["quantity"]))
            else:
                account = etrade_account
                value = clean_num(_get_col(row, ["value $", "current value", "value"]))
                ret = clean_num(_get_col(row, ["total gain %"]))
                shares = clean_num(_get_col(row, ["quantity"]))

            if value <= 0:
                continue

            bucket = holdings[account].setdefault(sym, {"value": 0.0, "return_pct": ret, "shares": 0.0})
            bucket["value"] += value
            bucket["return_pct"] = ret
            bucket["shares"] += shares

    return holdings

def save_verdict_history(new_verdicts):
    data_dir = DATA_DIR
    os.makedirs(data_dir, exist_ok=True)
    verdict_path = os.path.join(data_dir, "board_verdicts.json")
    
    current_history = {}
    if os.path.exists(verdict_path):
        try:
            with open(verdict_path, "r") as f:
                current_history = json.load(f)
        except Exception:
            pass

    for sym, verdict_data in new_verdicts.items():
        if sym not in current_history:
            current_history[sym] = []
        current_history[sym].append(verdict_data)

    try:
        with open(verdict_path, "w") as f:
            json.dump(current_history, f, indent=4)
        logger.info("Verdict history successfully persisted to local storage.")
    except Exception:
        logger.error("Failed to persist verdict history.")