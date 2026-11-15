"""Fires saved agent schedules. A due job is sent as a normal turn."""

import threading
import time
import traceback

from . import store
from .harness import run_turn


def start(socketio) -> None:
    threading.Thread(target=_loop, args=(socketio,), daemon=True, name="schedules").start()


def _loop(socketio) -> None:
    while True:
        time.sleep(8)
        try:
            for job in store.claim_due_schedules(store.now_iso()):
                room = f"agent:{job['agent_id']}"
                socketio.emit("schedules", store.list_schedules(job["agent_id"]), to=room)
                threading.Thread(
                    target=run_turn,
                    args=(socketio, job["agent_id"], job["instruction"], "Schedule"),
                    daemon=True,
                ).start()
        except Exception:
            traceback.print_exc()
