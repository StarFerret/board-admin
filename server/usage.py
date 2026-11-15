"""Usage log: who asked, which agent, which model, how many tokens.

One row per turn in `usage_events` (data/board.db). Control reads this table
read only to show the Usage page; the Board itself never serves it, because
the Board has no login.

A turn runs in one thread, so the running tally is thread local:
`begin()` at the start of the turn, `note()` after every model reply
(called from ollama_client), `finish()` when the turn ends.
"""

import threading
import time
from datetime import datetime, timezone

from . import db

_local = threading.local()


def begin() -> None:
    _local.tally = {
        "started": time.monotonic(),
        "model": "",
        "model_calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
    }


def note(model: str, result: dict) -> None:
    """Add one model reply to the running turn. Does nothing outside a turn."""
    tally = getattr(_local, "tally", None)
    if tally is None or not isinstance(result, dict):
        return
    tally["model"] = model or tally["model"]
    tally["model_calls"] += 1
    tally["prompt_tokens"] += int(result.get("prompt_eval_count") or 0)
    tally["completion_tokens"] += int(result.get("eval_count") or 0)


def finish(person: str, agent: dict, status: str = "done") -> None:
    """Write the turn to the log. Never raises: usage must not break a turn."""
    tally = getattr(_local, "tally", None)
    _local.tally = None
    if tally is None:
        return
    try:
        with db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO usage_events(
                    created_at, source, person, agent_id, workspace_id, model,
                    model_calls, prompt_tokens, completion_tokens, duration_ms, status
                ) VALUES (?, 'board', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    (person or "Guest").strip()[:40] or "Guest",
                    agent.get("id"),
                    agent.get("workspace_id"),
                    tally["model"],
                    tally["model_calls"],
                    tally["prompt_tokens"],
                    tally["completion_tokens"],
                    int((time.monotonic() - tally["started"]) * 1000),
                    status,
                ),
            )
    except Exception:
        pass
