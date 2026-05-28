import azure.functions as func
import logging
import os
import sys
import asyncio

root_path = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(root_path, "src")
core_path = os.path.join(src_path, "core")
output_path = os.path.join(src_path, "output")
data_path = os.path.join(src_path, "data")

for path_dir in [src_path, root_path, core_path, output_path, data_path]:
    if path_dir not in sys.path:
        sys.path.insert(0, path_dir)

app = func.FunctionApp()

@app.timer_trigger(schedule="0 0 11 * * 1-5", arg_name="myTimer", run_on_startup=False, use_monitor=False)
def boardroom_daily_run(myTimer: func.TimerRequest) -> None:
    logging.info("Waking up the Board of Directors. Initiating daily run.")
    
    try:
        from azure.storage.blob import BlobServiceClient, BlobLeaseClient
        from azure.core.exceptions import ResourceModifiedError
        from src.main import main_batch
    except Exception as e:
        logging.error(f"FATAL STARTUP OR IMPORT ERROR: {e}")
        raise e

    conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    if not conn_str:
        logging.error("FATAL. AZURE_STORAGE_CONNECTION_STRING is missing. Halting execution.")
        return

    try:
        blob_service = BlobServiceClient.from_connection_string(conn_str)
        container = blob_service.get_container_client("boardroom-state")
        
        if not container.exists():
            container.create_container()
            
        blob_client = container.get_blob_client("daily_execution.lock")

        if not blob_client.exists():
            blob_client.upload_blob("lock_established", overwrite=True)

        lease_client = BlobLeaseClient(blob_client)
        
        lease_client.acquire(lease_duration=60)
        logging.info("Distributed lock acquired. Guaranteeing idempotent execution.")
        
        asyncio.run(main_batch())
        
        lease_client.release()
        logging.info("Pipeline execution complete. Lock released successfully.")
        
    except ResourceModifiedError:
        logging.warning("Lock acquisition failed. Another container is processing this window. Terminating safely.")
    except Exception as e:
        logging.error(f"FATAL. Boardroom execution failed during locked transaction. {e}")