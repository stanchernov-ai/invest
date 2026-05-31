"""Run all three phases in-process, sequentially.

Used for local end-to-end runs (`python -m src.main`) and for recovering a run
on one machine without the Azure queue chain. On Azure the phases are chained via
Storage Queues in function_app.py instead, so each gets its own 10-minute budget.
"""
import asyncio
import logging

from src.jobs.prepare import run_prepare
from src.jobs.debate import run_debate
from src.jobs.deliver import run_deliver
from src.logging_setup import configure_logging

logger = configure_logging()


async def run_all(run_id: str = None, user_id: str = "stan") -> dict:
    configure_logging()
    prep = await run_prepare(run_id=run_id, user_id=user_id)
    if prep.get("status") != "success":
        logger.error("Halting after prepare phase failure.")
        return {"run_id": prep.get("run_id"), "status": "failed", "phase": "prepare"}

    run_id = prep["run_id"]
    deb = await run_debate(run_id, user_id=user_id)
    if deb.get("status") != "success":
        logger.error("Halting after debate phase failure.")
        return {"run_id": run_id, "status": "failed", "phase": "debate"}

    deliv = await run_deliver(run_id, user_id=user_id)
    return {"run_id": run_id, "status": deliv.get("status", "failed"), "phase": "deliver"}


if __name__ == "__main__":
    asyncio.run(run_all())
