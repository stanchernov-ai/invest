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

def sync_inputs_from_cloud():
    client = get_blob_service_client()
    if not client:
        logger.info("No Azure connection string found. Relying on local data files.")
        return 
    
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
                if blob.name.endswith(".json"):
                    file_path = os.path.join(data_dir, blob.name)
                    with open(file_path, "wb") as f:
                        f.write(state_client.download_blob(blob.name).readall())
                        
        logger.info("Successfully synced all inputs and state from Azure.")
            
    except Exception:
        logger.warning("Failed to sync inputs from Azure. Falling back to local files.")

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