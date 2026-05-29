"""Cross-run watchlist verdict memory for the Scout cooldown.

Only chairman **Pass** verdicts from compliance-approved runs are persisted.
"""
from __future__ import annotations

import json
import logging
import os

from src.config.settings import DATA_DIR, now_local
from src.storage_client import STATE_CONTAINER, get_blob_service_client, load_state_blob

logger = logging.getLogger(__name__)

BOARD_VERDICTS_FILE = "board_verdicts.json"


def _verdict_path() -> str:
    return os.path.join(DATA_DIR, BOARD_VERDICTS_FILE)


def _read_local_board_verdicts() -> dict | None:
    path = _verdict_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        logger.warning("Could not read local board_verdicts.json.")
        return None


def _cache_board_verdicts_local(history: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(_verdict_path(), "w", encoding="utf-8") as f:
        json.dump(history, f, indent=4)


def load_board_verdicts() -> dict:
    """Azure state first (Functions cold start), then local DATA_DIR copy."""
    cloud = load_state_blob(BOARD_VERDICTS_FILE)
    if isinstance(cloud, dict) and cloud:
        _cache_board_verdicts_local(cloud)
        return cloud

    local = _read_local_board_verdicts()
    return local if local is not None else {}


def save_board_verdicts(history: dict) -> None:
    if not isinstance(history, dict):
        history = {}
    if not history:
        prior = _read_local_board_verdicts()
        if not prior:
            prior_cloud = load_state_blob(BOARD_VERDICTS_FILE)
            prior = prior_cloud if isinstance(prior_cloud, dict) else None
        if prior:
            logger.warning(
                "Refusing to save empty board_verdicts.json over %d existing symbol(s).",
                len(prior),
            )
            return

    _cache_board_verdicts_local(history)

    client = get_blob_service_client()
    if not client:
        return
    try:
        blob_client = client.get_blob_client(container=STATE_CONTAINER, blob=BOARD_VERDICTS_FILE)
        blob_client.upload_blob(json.dumps(history, indent=4), overwrite=True)
        logger.info("board_verdicts.json uploaded to Azure state container.")
    except Exception:
        logger.error("Failed to upload board_verdicts.json to Azure.")


def extract_watchlist_pass_entries(
    chairman_data: dict,
    run_id: str,
    *,
    watchlist_symbols: list[str] | None = None,
) -> dict[str, list[dict]]:
    """Build append-only Pass records from chairman watchlist positions.

    The chairman JSON often omits non-actionable Pass rows; when ``watchlist_symbols``
    is supplied, symbols not assigned Buy/Strong Buy are treated as implicit Pass."""
    if not chairman_data and not watchlist_symbols:
        return {}

    date_str = run_id[:8] if len(run_id) >= 8 and run_id[:8].isdigit() else now_local().strftime("%Y%m%d")
    entries: dict[str, list[dict]] = {}
    actionable: set[str] = set()

    for pos in chairman_data.get("watchlist_positions") or []:
        sym = (pos.get("symbol") or "").strip().upper()
        if not sym:
            continue
        verdict = (pos.get("final_verdict") or "").strip()
        if verdict.upper() == "PASS":
            entries.setdefault(sym, []).append(
                {"verdict": "Pass", "date": date_str, "unanimous_pass": False}
            )
        elif verdict.upper() in ("BUY", "STRONG BUY"):
            actionable.add(sym)

    if watchlist_symbols:
        for sym in watchlist_symbols:
            sym = (sym or "").strip().upper()
            if not sym or sym in actionable or sym in entries:
                continue
            entries.setdefault(sym, []).append(
                {"verdict": "Pass", "date": date_str, "unanimous_pass": False}
            )

    return entries


def persist_chairman_watchlist_passes(
    chairman_data: dict,
    run_id: str,
    *,
    is_approved: bool,
    watchlist_symbols: list[str] | None = None,
) -> int:
    """Append Pass cooldown entries after a compliant debate. Returns symbols updated."""
    if not is_approved:
        logger.info("Skipping verdict memory — debate not compliance-approved.")
        return 0

    new_entries = extract_watchlist_pass_entries(
        chairman_data, run_id, watchlist_symbols=watchlist_symbols
    )
    if not new_entries:
        return 0

    history = load_board_verdicts()
    for sym, records in new_entries.items():
        history.setdefault(sym, []).extend(records)
    save_board_verdicts(history)
    logger.info("Persisted %d watchlist Pass verdict(s) to board_verdicts.json.", len(new_entries))
    return len(new_entries)
