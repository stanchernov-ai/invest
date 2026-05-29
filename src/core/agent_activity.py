"""In-memory per-agent activity ledger for a single pipeline run.

This is the deterministic ground truth the HR Efficiency Consultant needs to
right-size the agent roster: which agents actually fired, how often, on which
model, their error count, and their token footprint (prompt / output / thinking).

Populated by `call_gemini_async` (the single LLM chokepoint) and snapshotted into
telemetry at the end of a run. Don't make the HR reviewer guess utilization from
prose — give it counts.
"""
import logging
import threading

logger = logging.getLogger(__name__)

# asyncio is single-threaded, but the lock keeps this safe if a thread pool is
# ever introduced; it is essentially free under normal async use.
_lock = threading.Lock()
_ledger: dict[str, dict] = {}


def reset() -> None:
    """Clear the ledger at the start of a run."""
    with _lock:
        _ledger.clear()


def _extract_usage(response):
    usage = getattr(response, "usage_metadata", None)
    if not usage:
        return 0, 0, 0, 0
    prompt = getattr(usage, "prompt_token_count", 0) or 0
    output = getattr(usage, "candidates_token_count", 0) or 0
    thoughts = getattr(usage, "thoughts_token_count", 0) or 0
    total = getattr(usage, "total_token_count", 0) or (prompt + output + thoughts)
    return prompt, output, thoughts, total


def record(agent_name: str, model: str, response=None, error: bool = False) -> None:
    """Record one LLM invocation for an agent. Never raises (telemetry must not
    break the pipeline)."""
    try:
        prompt, output, thoughts, total = _extract_usage(response) if response is not None else (0, 0, 0, 0)
        with _lock:
            entry = _ledger.setdefault(agent_name, {
                "agent": agent_name,
                "model": model,
                "invocations": 0,
                "errors": 0,
                "prompt_tokens": 0,
                "output_tokens": 0,
                "thinking_tokens": 0,
                "total_tokens": 0,
            })
            entry["model"] = model
            entry["invocations"] += 1
            if error:
                entry["errors"] += 1
            entry["prompt_tokens"] += prompt
            entry["output_tokens"] += output
            entry["thinking_tokens"] += thoughts
            entry["total_tokens"] += total
    except Exception as e:  # pragma: no cover - defensive
        logger.debug(f"agent_activity.record failed for {agent_name}: {e}")


def snapshot() -> dict[str, dict]:
    """Return a deep-ish copy of the ledger for serialization into telemetry."""
    with _lock:
        return {k: dict(v) for k, v in _ledger.items()}
