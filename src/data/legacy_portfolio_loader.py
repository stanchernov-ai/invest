"""One-time loader: Stan's brokerage CSV extracts → Postgres-shaped portfolios.

Source files (SSOT): src/data/extracts/*.csv (eTrade + Fidelity exports).
Used by scripts/admin_provision_user.py — not invoked by the daily pipeline.
"""
from __future__ import annotations

import csv
import glob
import logging
import os
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

REPO_EXTRACTS_DIR = Path(__file__).resolve().parent / "extracts"

ACCOUNT_ORDER = [
    "eTrade Taxable",
    "eTrade Roth IRA",
    "Fidelity 401K",
    "Fidelity Roth 401K",
]

BUCKET_BY_ACCOUNT = {
    "eTrade Taxable": "taxable",
    "eTrade Roth IRA": "roth",
    "Fidelity 401K": "401k",
    "Fidelity Roth 401K": "roth",
}

FIDELITY_ACCOUNT_MAP = {
    "workday 401(k)": "Fidelity 401K",
    "brokeragelink": "Fidelity 401K",
    "brokeragelink roth": "Fidelity Roth 401K",
}

SKIP_SYMBOLS = frozenset({"CASH", "CORE", "TOTAL", "PENDING", "NAN"})


def _clean_num(val_str) -> float:
    if not val_str or str(val_str).strip().lower() in ("n/a", "none", ""):
        return 0.0
    cleaned = re.sub(r"[^\d.\-]", "", str(val_str))
    try:
        return float(cleaned or 0.0)
    except ValueError:
        return 0.0


def _get_col(row: dict, names: list[str]) -> str:
    names_l = [n.lower() for n in names]
    for key, val in row.items():
        if key and str(key).lower().strip() in names_l:
            return val or ""
    return ""


def _parse_purchase_dates(data_dir: Path) -> dict[str, str]:
    purchase_dates: dict[str, str] = {}
    for file in glob.glob(str(data_dir / "*.csv")):
        if "activity" not in file.lower():
            continue
        try:
            with open(file, encoding="utf-8-sig") as f:
                lines = f.readlines()
            header_idx = -1
            for i, line in enumerate(lines):
                lower = line.lower()
                if "symbol" in lower and ("date" in lower or "run date" in lower):
                    header_idx = i
                    break
            if header_idx < 0:
                continue
            reader = csv.DictReader(lines[header_idx:])
            for row in reader:
                sym = _get_col(row, ["symbol"]).strip().upper()
                action = _get_col(row, ["action", "transaction type"]).lower()
                if not sym or "buy" not in action:
                    continue
                if sym not in purchase_dates:
                    purchase_dates[sym] = _get_col(row, ["date", "run date"]).strip()
        except OSError:
            logger.warning("Could not read activity file %s", file)
    return purchase_dates


def _parse_etrade_file(filepath: Path) -> dict[str, dict]:
    positions: dict[str, dict] = {}
    with open(filepath, encoding="utf-8-sig") as f:
        lines = f.readlines()
    header_idx = -1
    for i, line in enumerate(lines):
        lower = line.lower()
        if "symbol" in lower and "value" in lower:
            if "sort by" in lower:
                continue
            header_idx = i
            break
    if header_idx < 0:
        return positions
    reader = csv.DictReader(lines[header_idx:])
    for row in reader:
        sym = _get_col(row, ["symbol"]).strip().upper()
        if not sym or sym in SKIP_SYMBOLS or "**" in sym or "FDRXX" in sym:
            continue
        val = _clean_num(_get_col(row, ["value $", "value"]))
        shares = _clean_num(_get_col(row, ["quantity"]))
        price_paid = _clean_num(_get_col(row, ["price paid $", "price paid"]))
        cost = _clean_num(_get_col(row, ["cost basis total", "cost basis"]))
        if cost == 0 and price_paid and shares:
            cost = price_paid * shares
        if val == 0 and cost == 0:
            continue
        positions[sym] = {
            "symbol": sym,
            "shares": shares,
            "cost_basis": cost,
        }
    return positions


def _parse_fidelity_file(filepath: Path) -> dict[str, dict[str, dict]]:
    """account_name -> symbol -> position"""
    by_account: dict[str, dict[str, dict]] = {a: {} for a in ACCOUNT_ORDER}
    with open(filepath, encoding="utf-8-sig") as f:
        lines = f.readlines()
    header_idx = -1
    for i, line in enumerate(lines):
        lower = line.lower()
        if "symbol" in lower and ("current value" in lower or "last price" in lower):
            header_idx = i
            break
    if header_idx < 0:
        return by_account
    reader = csv.DictReader(lines[header_idx:])
    for row in reader:
        sym = _get_col(row, ["symbol"]).strip().upper()
        if not sym or sym in SKIP_SYMBOLS or "**" in sym or "FDRXX" in sym:
            continue
        if sym.startswith("922") or "BROKERAGELINK" in sym:
            continue
        acct_key = _get_col(row, ["account name"]).strip().lower()
        account = FIDELITY_ACCOUNT_MAP.get(acct_key)
        if not account:
            continue
        value = _clean_num(_get_col(row, ["current value", "value"]))
        shares = _clean_num(_get_col(row, ["quantity"]))
        cost = _clean_num(_get_col(row, ["cost basis total", "cost basis"]))
        if value <= 0 and cost <= 0:
            continue
        existing = by_account[account].get(sym)
        if existing:
            existing["shares"] += shares
            existing["cost_basis"] += cost
        else:
            by_account[account][sym] = {
                "symbol": sym,
                "shares": shares,
                "cost_basis": cost,
            }
    return by_account


def _parse_date_optional(raw: str) -> str | None:
    if not raw or raw.lower() == "unknown":
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(raw.strip()[:10], fmt).date().isoformat()
        except ValueError:
            continue
    return None


def load_holdings_from_extracts(extracts_dir: str | Path | None = None) -> list[dict]:
    """
    Returns list of portfolios, each:
      {name, bucket_type, sort_order, positions: [{symbol, shares, cost_basis, purchase_date?}]}
    """
    data_dir = Path(extracts_dir or REPO_EXTRACTS_DIR)
    if not data_dir.is_dir():
        raise FileNotFoundError(f"Extracts directory not found: {data_dir}")

    purchase_dates = _parse_purchase_dates(data_dir)
    account_positions: dict[str, dict[str, dict]] = {a: {} for a in ACCOUNT_ORDER}

    for file in sorted(glob.glob(str(data_dir / "*.csv"))):
        path = Path(file)
        lower = path.name.lower()
        if "activity" in lower:
            continue
        if "fidelity" in lower:
            for acct, pos_map in _parse_fidelity_file(path).items():
                for sym, pos in pos_map.items():
                    if sym in account_positions[acct]:
                        account_positions[acct][sym]["shares"] += pos["shares"]
                        account_positions[acct][sym]["cost_basis"] += pos["cost_basis"]
                    else:
                        account_positions[acct][sym] = dict(pos)
        elif "etrade" in lower:
            acct = "eTrade Roth IRA" if "roth" in lower else "eTrade Taxable"
            for sym, pos in _parse_etrade_file(path).items():
                if sym in account_positions[acct]:
                    account_positions[acct][sym]["shares"] += pos["shares"]
                    account_positions[acct][sym]["cost_basis"] += pos["cost_basis"]
                else:
                    account_positions[acct][sym] = dict(pos)

    portfolios = []
    for sort_order, name in enumerate(ACCOUNT_ORDER):
        positions = []
        for sym, pos in sorted(account_positions[name].items()):
            pdate = _parse_date_optional(purchase_dates.get(sym, ""))
            entry = {
                "symbol": sym,
                "shares": pos["shares"],
                "cost_basis": round(pos["cost_basis"], 2),
            }
            if pdate:
                entry["purchase_date"] = pdate
            positions.append(entry)
        portfolios.append(
            {
                "name": name,
                "bucket_type": BUCKET_BY_ACCOUNT[name],
                "sort_order": sort_order,
                "positions": positions,
            }
        )
        logger.info("%s: %d positions", name, len(positions))

    return portfolios
