"""Human-architect lock — overnight runner exits when another session owns the repo."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.overnight.constants import LOCK_PATH


def read_lock() -> dict[str, Any] | None:
    if not LOCK_PATH.exists():
        return None
    try:
        data = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"owner": "unknown", "reason": "invalid LOCK file"}
    return data


def is_locked() -> tuple[bool, str]:
    lock = read_lock()
    if not lock:
        return False, ""
    owner = lock.get("owner") or "unknown"
    reason = lock.get("reason") or "active human session"
    until = lock.get("until")
    if until:
        try:
            expiry = datetime.fromisoformat(until.replace("Z", "+00:00"))
            if expiry < datetime.now(timezone.utc):
                return False, ""
        except ValueError:
            pass
    return True, f"LOCK held by {owner!r}: {reason}"


def write_lock(owner: str, reason: str, *, until: str | None = None) -> Path:
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "owner": owner,
        "reason": reason,
        "until": until,
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    LOCK_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return LOCK_PATH


def clear_lock() -> None:
    if LOCK_PATH.exists():
        LOCK_PATH.unlink()
