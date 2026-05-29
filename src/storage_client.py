import os
import json
import logging
from datetime import datetime, timedelta, timezone
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

from src.config.settings import DATA_DIR, OUTPUT_DIR

load_dotenv()
logger = logging.getLogger(__name__)

AZURE_CONN_STR = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
dash = chr(45)
INPUT_CONTAINER = f"boardroom{dash}inputs"
STATE_CONTAINER = f"boardroom{dash}state"
REPORT_CONTAINER = f"boardroom{dash}reports"
RUN_STATUS_BLOB = "run_status.json"

# Phases of the split pipeline (prepare -> debate -> deliver). Each runs as its
# own Azure Function invocation with its own 10-minute ceiling.
PHASES = ("prepare", "debate", "deliver")

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


def save_run_status(payload: dict) -> None:
    """Publish latest pipeline run status to state blob (completion signal for monitors)."""
    client = get_blob_service_client()
    json_str = json.dumps(payload, indent=2)

    filepath = os.path.join(DATA_DIR, RUN_STATUS_BLOB)
    os.makedirs(os.path.dirname(filepath) or DATA_DIR, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(json_str)

    if client:
        try:
            blob_client = client.get_blob_client(container=STATE_CONTAINER, blob=RUN_STATUS_BLOB)
            blob_client.upload_blob(json_str, overwrite=True)
        except Exception:
            logger.error("Failed to publish run_status.json to Azure.")


def load_run_status() -> dict | None:
    """Load run_status.json from Azure state container, falling back to local copy."""
    client = get_blob_service_client()
    if client:
        try:
            blob_client = client.get_blob_client(container=STATE_CONTAINER, blob=RUN_STATUS_BLOB)
            if blob_client.exists():
                return json.loads(blob_client.download_blob().readall())
        except Exception:
            logger.warning("Could not load run_status.json from Azure.")

    filepath = os.path.join(DATA_DIR, RUN_STATUS_BLOB)
    if os.path.exists(filepath):
        try:
            with open(filepath, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None

def get_blob_service_client():
    if not AZURE_CONN_STR:
        return None
    try:
        return BlobServiceClient.from_connection_string(AZURE_CONN_STR)
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
    save_run_status(status)
    return status


def mark_phase(run_id: str, phase: str, phase_status: str, *,
               started_at: str = None, finished_at: str = None,
               duration_seconds: float = None, error: str = None,
               **extra) -> dict:
    """Update one phase's sub-status and the overall run status in one place.

    Overall `status` becomes 'failed' if any phase fails, and 'success' only when
    the deliver phase succeeds. Intermediate phase success keeps overall 'running'
    so existing monitors (wait_for_run.py) wait for the full run."""
    status = load_run_status() or {}
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
    elif phase == "deliver" and phase_status == "success":
        status["status"] = "success"
        status["finished_at"] = finished_at
    else:
        status["status"] = "running"

    save_run_status(status)
    return status

def save_memory(data):
    client = get_blob_service_client()
    json_str = json.dumps(data, indent=4)
    
    filepath = os.path.join(DATA_DIR, "board_verdicts.json")
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w") as f:
        f.write(json_str)
        
    if client:
        try:
            blob_client = client.get_blob_client(container=STATE_CONTAINER, blob="board_verdicts.json")
            blob_client.upload_blob(json_str, overwrite=True)
            logger.info("Memory seamlessly uploaded to Azure Blob Storage.")
        except Exception:
            logger.error("Failed to save memory to Azure.")

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
                if blob.name in ["daily_execution.lock", "board_verdicts.json", "portfolio_history.json"]:
                    continue

                if blob.last_modified and blob.last_modified < cutoff_date:
                    container_client.delete_blob(blob.name)
                    logger.info(f"Purged expired artifact {blob.name} from {container_name}.")
        except Exception:
            logger.error(f"Failed to execute retention policy on {container_name}.")