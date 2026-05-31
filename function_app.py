import azure.functions as func
import logging
import json
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

# Split pipeline: prepare -> (queue) -> debate -> (queue) -> deliver. Each phase
# runs as its own invocation with an independent 10-minute ceiling and chains the
# next phase via a Storage Queue message carrying the run_id (non-blocking, so the
# producer phase exits immediately instead of holding its budget open).
DEBATE_QUEUE = "boardroom-debate-queue"
DELIVER_QUEUE = "boardroom-deliver-queue"
LOCK_BLOB = "daily_execution.lock"
STATE_CONTAINER = "boardroom-state"

# Self-abort a phase before Azure's hard 10:00 kill so run_status records "failed"
# (with the room left to write status + enqueue) instead of a silent timeout.
PHASE_SOFT_TIMEOUT_SECONDS = 540


def _enqueue_phase(run_id: str, phase: str) -> None:
    """Record that the next phase was handed off to a Storage Queue."""
    from src import storage_client
    from src.config.settings import now_local

    storage_client.mark_phase(run_id, phase, "queued", started_at=now_local().isoformat())


def _guard_timer_prepare() -> bool:
    """Abort stale runs, then skip timer kickoff if another run is still in flight."""
    from src import storage_client

    aborted = storage_client.abort_stale_run_if_needed()
    if aborted:
        logging.warning(
            "Aborted stale run %s before timer prepare: %s",
            aborted.get("run_id"),
            aborted.get("error"),
        )

    in_flight = storage_client.is_run_in_flight()
    if in_flight:
        logging.warning(
            "Timer prepare skipped — run %s still %s in phase %s.",
            in_flight.get("run_id"),
            in_flight.get("status"),
            in_flight.get("phase"),
        )
        return False
    return True


def _new_run_id() -> str:
    from src.config.settings import now_local
    return now_local().strftime('%Y%m%d_%H%M%S')


def _run_phase(coro, run_id: str, phase: str) -> bool:
    """Run a phase coroutine with a soft timeout. Returns True on success.

    On timeout/exception, marks the phase failed in run_status so a monitor never
    hangs on a stale 'running' after an Azure kill."""
    from src import storage_client
    from src.config.settings import now_local

    async def _runner():
        return await asyncio.wait_for(coro, timeout=PHASE_SOFT_TIMEOUT_SECONDS)

    try:
        result = asyncio.run(_runner())
        return bool(result) and result.get("status") == "success"
    except asyncio.TimeoutError:
        logging.error(f"[{phase.upper()}] Soft timeout ({PHASE_SOFT_TIMEOUT_SECONDS}s) hit; marking failed.")
        try:
            storage_client.mark_phase(run_id, phase, "failed",
                                      finished_at=now_local().isoformat(),
                                      error=f"{phase} soft timeout ({PHASE_SOFT_TIMEOUT_SECONDS}s)")
        except Exception as e:
            logging.error(f"Could not record {phase} timeout status: {e}")
        return False
    except Exception as e:
        logging.error(f"[{phase.upper()}] Unhandled error: {e}")
        try:
            storage_client.mark_phase(run_id, phase, "failed",
                                      finished_at=now_local().isoformat(),
                                      error=str(e))
        except Exception as mark_err:
            logging.error(f"Could not record {phase} failure status: {mark_err}")
        return False


# --------------------------------------------------------------------------- #
# Stale-run watchdog — abort runs stuck in 'running' beyond the E2E ceiling.  #
# --------------------------------------------------------------------------- #
@app.timer_trigger(schedule="0 */15 * * * *", arg_name="watchdogTimer", run_on_startup=False, use_monitor=False)
def boardroom_stale_run_watchdog(watchdogTimer: func.TimerRequest) -> None:
    from src import storage_client

    aborted = storage_client.abort_stale_run_if_needed()
    if aborted:
        logging.warning(
            "Stale-run watchdog aborted run %s: %s",
            aborted.get("run_id"),
            aborted.get("error"),
        )


# --------------------------------------------------------------------------- #
# Job 1 - PREPARE (timer entry + manual HTTP). Holds the daily lock.           #
# --------------------------------------------------------------------------- #
def _kickoff_prepare(run_id: str) -> bool:
    """Acquire the daily lock and run the prepare phase. Returns True on success."""
    from azure.storage.blob import BlobServiceClient, BlobLeaseClient
    from azure.core.exceptions import ResourceModifiedError
    from src.jobs.prepare import run_prepare

    conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    if not conn_str:
        logging.error("FATAL. AZURE_STORAGE_CONNECTION_STRING is missing. Halting execution.")
        return False

    try:
        blob_service = BlobServiceClient.from_connection_string(conn_str)
        container = blob_service.get_container_client(STATE_CONTAINER)
        if not container.exists():
            container.create_container()

        blob_client = container.get_blob_client(LOCK_BLOB)
        if not blob_client.exists():
            blob_client.upload_blob("lock_established", overwrite=True)
        else:
            try:
                props = blob_client.get_blob_properties()
                from datetime import datetime, timezone
                age = (datetime.now(timezone.utc) - props.last_modified).total_seconds()
                if age > 3600:
                    BlobLeaseClient(blob_client).break_lease()
                    logging.info("Broke orphaned lease from a previous failed run.")
            except Exception as e:
                logging.warning(f"Could not check or break orphaned lease: {e}")

        lease_client = BlobLeaseClient(blob_client)
        lease_client.acquire(lease_duration=-1)
        blob_client.upload_blob("lock_established", overwrite=True, lease=lease_client)
        logging.info("Distributed lock acquired (infinite lease). Running prepare phase.")

        try:
            return _run_phase(run_prepare(run_id=run_id), run_id, "prepare")
        finally:
            lease_client.release()
            logging.info("Prepare lock released.")

    except ResourceModifiedError:
        logging.warning("Lock acquisition failed. Another container is preparing this window. Terminating safely.")
        return False
    except Exception as e:
        logging.error(f"FATAL. Prepare kickoff failed: {e}")
        return False


# 6:00 AM daily in WEBSITE_TIME_ZONE (set to America/Los_Angeles on the Function App).
# Typical finish ~6:07–6:15; briefing email before the 6:30 market open (Pacific).
@app.timer_trigger(schedule="0 0 6 * * *", arg_name="myTimer", run_on_startup=False, use_monitor=False)
@app.queue_output(arg_name="debateOut", queue_name=DEBATE_QUEUE, connection="AzureWebJobsStorage")
def boardroom_prepare(myTimer: func.TimerRequest, debateOut: func.Out[str]) -> None:
    logging.info("Waking up the Board of Directors. Initiating PREPARE phase.")
    if not _guard_timer_prepare():
        return
    run_id = _new_run_id()
    if _kickoff_prepare(run_id):
        debateOut.set(run_id)
        _enqueue_phase(run_id, "debate")
        logging.info(f"Prepare succeeded; enqueued debate for run {run_id}.")


@app.route(route="prepare", auth_level=func.AuthLevel.FUNCTION)
@app.queue_output(arg_name="debateOut", queue_name=DEBATE_QUEUE, connection="AzureWebJobsStorage")
def boardroom_prepare_http(req: func.HttpRequest, debateOut: func.Out[str]) -> func.HttpResponse:
    """Manual kickoff of the full chain. Rejects concurrent runs (409); re-runs after terminal states OK."""
    from src import storage_client

    aborted = storage_client.abort_stale_run_if_needed()
    if aborted:
        logging.warning(
            "Aborted stale run %s before HTTP prepare: %s",
            aborted.get("run_id"),
            aborted.get("error"),
        )

    in_flight = storage_client.is_run_in_flight()
    if in_flight:
        body = json.dumps({
            "run_id": in_flight.get("run_id"),
            "phase": in_flight.get("phase"),
            "message": "A pipeline run is already in progress.",
        })
        logging.warning(
            "Prepare HTTP rejected — run %s still %s in phase %s.",
            in_flight.get("run_id"), in_flight.get("status"), in_flight.get("phase"),
        )
        return func.HttpResponse(body, status_code=409, mimetype="application/json")

    run_id = _new_run_id()
    from src.jobs.prepare import run_prepare
    ok = _run_phase(run_prepare(run_id=run_id), run_id, "prepare")
    if ok:
        debateOut.set(run_id)
        _enqueue_phase(run_id, "debate")
        return func.HttpResponse(f"prepare ok; debate enqueued for {run_id}", status_code=202)
    return func.HttpResponse(f"prepare failed for {run_id}", status_code=500)


# --------------------------------------------------------------------------- #
# Job 2 - DEBATE (queue trigger + manual HTTP). Chains to deliver queue.       #
# --------------------------------------------------------------------------- #
@app.queue_trigger(arg_name="msg", queue_name=DEBATE_QUEUE, connection="AzureWebJobsStorage")
@app.queue_output(arg_name="deliverOut", queue_name=DELIVER_QUEUE, connection="AzureWebJobsStorage")
def boardroom_debate(msg: func.QueueMessage, deliverOut: func.Out[str]) -> None:
    from src.jobs.debate import run_debate
    run_id = (msg.get_body().decode("utf-8") or "").strip()
    logging.info(f"DEBATE phase triggered for run {run_id}.")
    if _run_phase(run_debate(run_id), run_id, "debate"):
        deliverOut.set(run_id)
        _enqueue_phase(run_id, "deliver")
        logging.info(f"Debate succeeded; enqueued deliver for run {run_id}.")


@app.route(route="debate", auth_level=func.AuthLevel.FUNCTION)
@app.queue_output(arg_name="deliverOut", queue_name=DELIVER_QUEUE, connection="AzureWebJobsStorage")
def boardroom_debate_http(req: func.HttpRequest, deliverOut: func.Out[str]) -> func.HttpResponse:
    from src.jobs.debate import run_debate
    run_id = (req.params.get("run_id") or "").strip()
    if not run_id:
        return func.HttpResponse("missing run_id", status_code=400)
    if _run_phase(run_debate(run_id), run_id, "debate"):
        deliverOut.set(run_id)
        _enqueue_phase(run_id, "deliver")
        return func.HttpResponse(f"debate ok; deliver enqueued for {run_id}", status_code=202)
    return func.HttpResponse(f"debate failed for {run_id}", status_code=500)


# --------------------------------------------------------------------------- #
# Job 3 - DELIVER (queue trigger + manual HTTP). Terminal phase.              #
# --------------------------------------------------------------------------- #
@app.queue_trigger(arg_name="msg", queue_name=DELIVER_QUEUE, connection="AzureWebJobsStorage")
def boardroom_deliver(msg: func.QueueMessage) -> None:
    from src.jobs.deliver import run_deliver
    run_id = (msg.get_body().decode("utf-8") or "").strip()
    logging.info(f"DELIVER phase triggered for run {run_id}.")
    _run_phase(run_deliver(run_id), run_id, "deliver")


@app.route(route="deliver", auth_level=func.AuthLevel.FUNCTION)
def boardroom_deliver_http(req: func.HttpRequest) -> func.HttpResponse:
    from src.jobs.deliver import run_deliver
    run_id = (req.params.get("run_id") or "").strip()
    if not run_id:
        return func.HttpResponse("missing run_id", status_code=400)
    if _run_phase(run_deliver(run_id), run_id, "deliver"):
        return func.HttpResponse(f"deliver ok for {run_id}", status_code=200)
    return func.HttpResponse(f"deliver failed for {run_id}", status_code=500)


# --------------------------------------------------------------------------- #
# Post-deliver retrospective (manual re-run; also runs at end of deliver).     #
# --------------------------------------------------------------------------- #
@app.route(route="retrospective", auth_level=func.AuthLevel.FUNCTION)
def boardroom_retrospective_http(req: func.HttpRequest) -> func.HttpResponse:
    from src.qa.retrospective import execute_retrospective
    run_id = (req.params.get("run_id") or "").strip()
    if not run_id:
        return func.HttpResponse("missing run_id", status_code=400)
    force = (req.params.get("force") or "").lower() in ("1", "true", "yes")
    try:
        result = execute_retrospective(run_id, force=force, write_local_insights=False)
        return func.HttpResponse(json.dumps(result, indent=2), status_code=200,
                                 mimetype="application/json")
    except FileNotFoundError as exc:
        return func.HttpResponse(str(exc), status_code=404)
    except ValueError as exc:
        return func.HttpResponse(str(exc), status_code=400)
    except Exception as exc:
        logging.error(f"Retrospective HTTP failed: {exc}")
        return func.HttpResponse(str(exc), status_code=500)


# --------------------------------------------------------------------------- #
# Standing QA & cost review team (unchanged).                                  #
# --------------------------------------------------------------------------- #
# 7:00 AM daily (same timezone) — standing QA/cost digest after the pipeline window.
@app.timer_trigger(schedule="0 0 7 * * *", arg_name="qaTimer", run_on_startup=False, use_monitor=False)
def qa_review_daily_run(qaTimer: func.TimerRequest) -> None:
    logging.info("Waking up the QA & Cost Review Team. Initiating daily run.")
    try:
        from src.qa_review import run_qa_review_team
        asyncio.run(run_qa_review_team())
    except Exception as e:
        logging.error(f"FATAL. QA Review execution failed. {e}")


# 8:00 AM daily — Legal Counsel codebase audit (SaaS/commercial prompt & copy review).
@app.timer_trigger(schedule="0 0 8 * * *", arg_name="legalCodeTimer", run_on_startup=False, use_monitor=False)
def boardroom_legal_code_audit_daily(legalCodeTimer: func.TimerRequest) -> None:
    logging.info("Legal Counsel daily codebase audit starting.")
    try:
        from src.jobs.legal_code_audit import run_daily_legal_code_audit
        asyncio.run(run_daily_legal_code_audit())
    except Exception as e:
        logging.error(f"FATAL. Legal code audit failed. {e}")


@app.route(route="legal-code-audit", auth_level=func.AuthLevel.FUNCTION)
def boardroom_legal_code_audit_http(req: func.HttpRequest) -> func.HttpResponse:
    """Manual Legal Counsel code audit (function key required)."""
    try:
        from src.jobs.legal_code_audit import run_daily_legal_code_audit
        payload = asyncio.run(run_daily_legal_code_audit())
        report = payload.get("report") or {}
        body = json.dumps({
            "ok": bool(report.get("is_compliant")),
            "summary": report.get("summary"),
            "findings_count": len(report.get("findings") or []),
            "files_scanned": report.get("files_scanned") or [],
        })
        status = 200 if report.get("is_compliant") else 422
        return func.HttpResponse(body, status_code=status, mimetype="application/json")
    except Exception as exc:
        logging.error(f"Legal code audit HTTP failed: {exc}")
        return func.HttpResponse(str(exc), status_code=500)


# --------------------------------------------------------------------------- #
# Human-confirmed QA review (after QA dashboard email).                        #
# --------------------------------------------------------------------------- #
@app.route(route="qa-review", methods=["GET", "POST"], auth_level=func.AuthLevel.ANONYMOUS)
def qa_human_review(req: func.HttpRequest) -> func.HttpResponse:
    from src.qa.human_review import handle_azure_request
    return handle_azure_request(req)
