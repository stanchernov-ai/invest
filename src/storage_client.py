import os
import json
import logging
from datetime import datetime, timedelta, timezone
from azure.storage.blob import BlobServiceClient

from src.config.settings import DATA_DIR, OUTPUT_DIR, settings

logger = logging.getLogger(__name__)
dash = chr(45)
INPUT_CONTAINER = f"boardroom{dash}inputs"
STATE_CONTAINER = f"boardroom{dash}state"
REPORT_CONTAINER = f"boardroom{dash}reports"
RUN_STATUS_BLOB = "run_status.json"
RUN_STATUS_CURRENT_BLOB = "run_status_current.json"


def _run_status_blob_for_run(run_id: str) -> str:
    return f"run_status_{run_id}.json"


def _run_status_local_path(filename: str) -> str:
    return os.path.join(DATA_DIR, filename)

# Phases of the split pipeline (prepare -> debate -> deliver). Each runs as its
# own Azure Function invocation with its own 10-minute ceiling.
PHASES = ("prepare", "debate", "deliver")

# End-to-end ceiling: 3 phases × 540s soft timeout + queue/hand-off slack.
STALE_RUN_MAX_SECONDS = 45 * 60

# Only these state singletons are pulled on a sync. Historical run artifacts
# (api_telemetry_*.json, qa_dashboard_*, raw_debate_log_*, and the runs/ phase
# checkpoints) are intentionally excluded — downloading every past telemetry
# blob on each run was wasting time and tripping rate limits on cold start.
STATE_SYNC_ALLOWLIST = (
    "board_verdicts.json",
    "portfolio_history.json",
    "portfolio_returns.json",
    RUN_STATUS_BLOB,
)


def _write_run_status_local(filename: str, json_str: str) -> None:
    filepath = _run_status_local_path(filename)
    os.makedirs(os.path.dirname(filepath) or DATA_DIR, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(json_str)


def _upload_run_status_blob(client, blob_name: str, json_str: str) -> None:
    try:
        blob_client = client.get_blob_client(container=STATE_CONTAINER, blob=blob_name)
        blob_client.upload_blob(json_str, overwrite=True)
    except Exception:
        logger.error("Failed to publish %s to Azure.", blob_name)


def _load_run_status_blob(blob_name: str) -> dict | None:
    client = get_blob_service_client()
    if client:
        try:
            blob_client = client.get_blob_client(container=STATE_CONTAINER, blob=blob_name)
            if blob_client.exists():
                return json.loads(blob_client.download_blob().readall())
        except Exception:
            logger.warning("Could not load %s from Azure.", blob_name)

    filepath = _run_status_local_path(blob_name)
    if os.path.exists(filepath):
        try:
            with open(filepath, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def save_run_status_for_run(run_id: str, payload: dict) -> None:
    """Persist phased status for one run_id (survives overlapping kicks)."""
    json_str = json.dumps(payload, indent=2)
    per_run_blob = _run_status_blob_for_run(run_id)
    _write_run_status_local(per_run_blob, json_str)

    client = get_blob_service_client()
    if client:
        _upload_run_status_blob(client, per_run_blob, json_str)


def save_run_status(payload: dict) -> None:
    """Publish the current-run pointer (monitors + HTTP guards read this)."""
    client = get_blob_service_client()
    json_str = json.dumps(payload, indent=2)

    for filename in (RUN_STATUS_BLOB, RUN_STATUS_CURRENT_BLOB):
        _write_run_status_local(filename, json_str)

    run_id = payload.get("run_id")
    if run_id:
        save_run_status_for_run(run_id, payload)

    if client:
        for blob_name in (RUN_STATUS_BLOB, RUN_STATUS_CURRENT_BLOB):
            _upload_run_status_blob(client, blob_name, json_str)


def load_run_status() -> dict | None:
    """Load the current pipeline pointer (run_status_current.json, then run_status.json)."""
    return _load_run_status_blob(RUN_STATUS_CURRENT_BLOB) or _load_run_status_blob(RUN_STATUS_BLOB)


def load_run_status_for_run(run_id: str) -> dict | None:
    """Load phased status for a specific run_id."""
    return _load_run_status_blob(_run_status_blob_for_run(run_id))


def is_run_in_flight() -> dict | None:
    """Return current status dict when overall status is 'running', else None."""
    status = load_run_status()
    if status and status.get("status") == "running":
        return status
    return None


def _parse_iso_datetime(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def abort_run(run_id: str, *, reason: str, finished_at: str) -> dict:
    """Mark a run as aborted (terminal). Used when a watchdog detects a stale run."""
    status = load_run_status_for_run(run_id) or {}
    if status.get("run_id") != run_id:
        status = _base_run_status(run_id, finished_at)

    status["status"] = "aborted"
    status["error"] = reason
    status["finished_at"] = finished_at

    phase = status.get("phase")
    if phase in PHASES:
        entry = status.get(phase) or {}
        if entry.get("status") in (None, "running", "queued"):
            entry["status"] = "aborted"
            entry["finished_at"] = finished_at
            entry["error"] = reason
            status[phase] = entry

    save_run_status_for_run(run_id, status)
    current = load_run_status()
    if not current or current.get("run_id") == run_id:
        save_run_status(status)
    return status


def abort_stale_run_if_needed(max_age_seconds: int = STALE_RUN_MAX_SECONDS) -> dict | None:
    """If the current pointer run has been non-terminal too long, mark it aborted."""
    from src.config.settings import now_local

    status = load_run_status()
    if not status or status.get("status") != "running":
        return None

    run_id = status.get("run_id")
    started = _parse_iso_datetime(status.get("started_at"))
    if not run_id or started is None:
        return None

    now = now_local()
    if started.tzinfo is None and now.tzinfo is not None:
        started = started.replace(tzinfo=now.tzinfo)
    elif started.tzinfo is not None and now.tzinfo is None:
        now = now.replace(tzinfo=started.tzinfo)

    age = (now - started).total_seconds()
    if age <= max_age_seconds:
        return None

    reason = (
        f"stale run: no terminal status after {int(age)}s "
        f"(limit {max_age_seconds}s)"
    )
    return abort_run(run_id, reason=reason, finished_at=now.isoformat())

def get_blob_service_client():
    if not settings.AZURE_CONN_STR:
        return None
    try:
        return BlobServiceClient.from_connection_string(settings.AZURE_CONN_STR)
    except Exception:
        logger.error("Failed to connect to Azure.")
        return None

def sync_inputs_from_cloud(state_allowlist=None):
    """Pull brokerage/watchlist inputs and a curated set of state singletons.

    `state_allowlist` defaults to STATE_SYNC_ALLOWLIST; pass an explicit list to
    override. Historical artifacts (telemetry, dashboards, run checkpoints) are
    never pulled here — they are not needed to run a fresh pipeline."""
    client = get_blob_service_client()
    if not client:
        logger.info("No Azure connection string found. Relying on local data files.")
        return

    allowlist = set(STATE_SYNC_ALLOWLIST if state_allowlist is None else state_allowlist)

    try:
        data_dir = DATA_DIR
        os.makedirs(data_dir, exist_ok=True)

        input_client = client.get_container_client(INPUT_CONTAINER)
        if input_client.exists():
            for blob in input_client.list_blobs():
                file_path = os.path.join(data_dir, blob.name)
                with open(file_path, "wb") as f:
                    f.write(input_client.download_blob(blob.name).readall())

        state_client = client.get_container_client(STATE_CONTAINER)
        if state_client.exists():
            for blob in state_client.list_blobs():
                if blob.name in allowlist:
                    file_path = os.path.join(data_dir, blob.name)
                    os.makedirs(os.path.dirname(file_path) or data_dir, exist_ok=True)
                    with open(file_path, "wb") as f:
                        f.write(state_client.download_blob(blob.name).readall())

        logger.info("Successfully synced inputs and curated state from Azure.")

    except Exception:
        logger.warning("Failed to sync inputs from Azure. Falling back to local files.")


def _checkpoint_blob_name(run_id: str, phase: str) -> str:
    return f"runs/{run_id}/{phase}.json"


def save_checkpoint(run_id: str, phase: str, payload: dict) -> None:
    """Persist a phase's hand-off payload so the next job can resume the run.

    Written to STATE_CONTAINER under runs/{run_id}/{phase}.json (and cached
    locally for dev). This is the contract between prepare -> debate -> deliver."""
    data = json.dumps(payload, default=str)

    local = os.path.join(DATA_DIR, "runs", run_id, f"{phase}.json")
    os.makedirs(os.path.dirname(local), exist_ok=True)
    with open(local, "w", encoding="utf-8") as f:
        f.write(data)

    client = get_blob_service_client()
    if client:
        try:
            blob_client = client.get_blob_client(
                container=STATE_CONTAINER, blob=_checkpoint_blob_name(run_id, phase)
            )
            blob_client.upload_blob(data, overwrite=True)
            logger.info(f"Checkpoint '{phase}' for run {run_id} persisted to Azure.")
        except Exception:
            logger.error(f"Failed to persist '{phase}' checkpoint for run {run_id} to Azure.")


def load_checkpoint(run_id: str, phase: str) -> dict | None:
    """Load a phase hand-off payload written by save_checkpoint (Azure first,
    local cache as fallback)."""
    client = get_blob_service_client()
    if client:
        try:
            blob_client = client.get_blob_client(
                container=STATE_CONTAINER, blob=_checkpoint_blob_name(run_id, phase)
            )
            if blob_client.exists():
                return json.loads(blob_client.download_blob().readall())
        except Exception:
            logger.warning(f"Could not load '{phase}' checkpoint for run {run_id} from Azure.")

    local = os.path.join(DATA_DIR, "runs", run_id, f"{phase}.json")
    if os.path.exists(local):
        try:
            with open(local, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def _base_run_status(run_id: str, started_at: str) -> dict:
    return {
        "run_id": run_id,
        "phase": "prepare",
        "status": "running",          # overall; only 'success' once deliver finishes
        "started_at": started_at,
        "finished_at": None,
        "error": None,
        "briefing_blob": None,
        "qa_blob": None,
        "prepare": None,
        "debate": None,
        "deliver": None,
    }


def begin_run_status(run_id: str, started_at: str) -> dict:
    """Initialize (or reset) the phased run status blob at the start of a run."""
    status = _base_run_status(run_id, started_at)
    save_run_status_for_run(run_id, status)
    save_run_status(status)
    return status


def mark_phase(run_id: str, phase: str, phase_status: str, *,
               started_at: str = None, finished_at: str = None,
               duration_seconds: float = None, error: str = None,
               **extra) -> dict:
    """Update one phase's sub-status and the overall run status in one place.

    Overall `status` becomes 'failed' if any phase fails, 'aborted' when explicitly
    aborted, and 'success' only when the deliver phase succeeds. Intermediate phase
    success or 'queued' keeps overall 'running' so monitors wait for the full run."""
    status = load_run_status_for_run(run_id) or {}
    if status.get("run_id") != run_id:
        status = _base_run_status(run_id, started_at or finished_at or "")

    entry = status.get(phase) or {}
    entry["status"] = phase_status
    if started_at is not None:
        entry["started_at"] = started_at
    if finished_at is not None:
        entry["finished_at"] = finished_at
    if duration_seconds is not None:
        entry["duration_seconds"] = duration_seconds
    if error is not None:
        entry["error"] = error
    entry.update(extra)
    status[phase] = entry

    status["phase"] = phase
    if phase_status == "failed":
        status["status"] = "failed"
        status["error"] = error
        status["finished_at"] = finished_at
    elif phase_status == "aborted":
        status["status"] = "aborted"
        status["error"] = error
        status["finished_at"] = finished_at
    elif phase == "deliver" and phase_status == "success":
        status["status"] = "success"
        status["finished_at"] = finished_at
    else:
        status["status"] = "running"

    save_run_status_for_run(run_id, status)
    current = load_run_status()
    if not current or current.get("run_id") == run_id:
        save_run_status(status)
    return status


def load_state_blob(filename: str):
    """Load a JSON or text blob from STATE_CONTAINER (Azure first, local OUTPUT_DIR fallback)."""
    client = get_blob_service_client()
    if client:
        try:
            blob_client = client.get_blob_client(container=STATE_CONTAINER, blob=filename)
            if blob_client.exists():
                raw = blob_client.download_blob().readall()
                if filename.endswith(".json"):
                    return json.loads(raw)
                return raw.decode("utf-8")
        except Exception:
            logger.warning(f"Could not load state blob {filename} from Azure.")

    filepath = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(filepath):
        filepath = os.path.join(DATA_DIR, filename)
    if os.path.exists(filepath):
        try:
            with open(filepath, encoding="utf-8") as f:
                if filename.endswith(".json"):
                    return json.load(f)
                return f.read()
        except Exception:
            pass
    return None


def save_state_blob(filename: str, payload) -> None:
    """Persist JSON or text to STATE_CONTAINER and local OUTPUT_DIR."""
    if filename.endswith(".json"):
        content = json.dumps(payload, indent=2, default=str)
    else:
        content = payload if isinstance(payload, str) else str(payload)

    filepath = os.path.join(OUTPUT_DIR, filename)
    os.makedirs(os.path.dirname(filepath) or OUTPUT_DIR, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    client = get_blob_service_client()
    if client:
        try:
            blob_client = client.get_blob_client(container=STATE_CONTAINER, blob=filename)
            blob_client.upload_blob(content, overwrite=True)
            logger.info(f"State blob {filename} uploaded to Azure.")
        except Exception:
            logger.error(f"Failed to save state blob {filename} to Azure.")


def save_report(filename, content):
    client = get_blob_service_client()
    
    filepath = os.path.join(OUTPUT_DIR, filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf" + chr(45) + "8") as f:
        f.write(content)
        
    if client:
        try:
            if filename.endswith(".json"):
                blob_client = client.get_blob_client(container=STATE_CONTAINER, blob=filename)
            else:
                blob_client = client.get_blob_client(container=REPORT_CONTAINER, blob=filename)
            blob_client.upload_blob(content, overwrite=True)
            logger.info("Payload uploaded to Azure Blob Storage.")
        except Exception:
            logger.error("Failed to save payload to Azure.")

def execute_retention_policy(days_to_keep=14):
    client = get_blob_service_client()
    if not client:
        return

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
    containers_to_clean = [STATE_CONTAINER, REPORT_CONTAINER]

    for container_name in containers_to_clean:
        try:
            container_client = client.get_container_client(container_name)
            if not container_client.exists():
                continue

            for blob in container_client.list_blobs():
                if blob.name in [
                    "daily_execution.lock",
                    "board_verdicts.json",
                    "portfolio_history.json",
                    "qa_human_reviews_ledger.json",
                    RUN_STATUS_BLOB,
                    RUN_STATUS_CURRENT_BLOB,
                ]:
                    continue

                if blob.last_modified and blob.last_modified < cutoff_date:
                    container_client.delete_blob(blob.name)
                    logger.info(f"Purged expired artifact {blob.name} from {container_name}.")
        except Exception:
            logger.error(f"Failed to execute retention policy on {container_name}.")