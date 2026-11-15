"""Who is using this Mac: Control → People.

Two sources, both read only:
- Board: people are display names. Counted from the messages they sent.
- Board presence: who has the Board open right now (asked over HTTP).

LibreChat keeps its own accounts in its own database (MongoDB). Control does
not read them yet, so LibreChat users are not counted here. See TODO.md section 0.

Control never writes to another app's database.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import requests

from .paths import BOARD_DB_PATH, DEFAULT_BOARD_PORT

ACTIVE_DAYS = 30


def _read_only(path: Path) -> Optional[sqlite3.Connection]:
    if not path.is_file():
        return None
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error:
        return None


def _iso_from_epoch(value: Any) -> Optional[str]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    if number > 1e11:  # milliseconds
        number /= 1000
    return datetime.fromtimestamp(number, tz=timezone.utc).isoformat()


def _recent(iso: Optional[str], cutoff: datetime) -> bool:
    if not iso:
        return False
    try:
        when = datetime.fromisoformat(iso)
    except ValueError:
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when >= cutoff


def board_people() -> dict[str, Any]:
    conn = _read_only(BOARD_DB_PATH)
    if conn is None:
        return {"available": False, "people": [], "error": None}
    try:
        rows = conn.execute(
            """
            SELECT COALESCE(NULLIF(TRIM(json_extract(meta_json, '$.author')), ''), 'Guest') AS name,
                   COUNT(*) AS messages,
                   COUNT(DISTINCT agent_id) AS agents,
                   MIN(created_at) AS first_seen,
                   MAX(created_at) AS last_active
            FROM messages
            WHERE role = 'user'
            GROUP BY name COLLATE NOCASE
            ORDER BY last_active DESC
            """
        ).fetchall()
    except sqlite3.Error as exc:
        return {"available": False, "people": [], "error": str(exc)[:200]}
    finally:
        conn.close()
    return {"available": True, "people": [dict(row) for row in rows], "error": None}


def board_online() -> list[str]:
    port = os.environ.get("PORT", str(DEFAULT_BOARD_PORT))
    try:
        resp = requests.get(f"http://127.0.0.1:{port}/api/presence", timeout=1.5)
        if resp.status_code == 200:
            return list(resp.json().get("people") or [])
    except Exception:
        pass
    return []


def summary() -> dict[str, Any]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=ACTIVE_DAYS)
    board = board_people()
    online = board_online()
    online_lower = {name.lower() for name in online}
    for person in board["people"]:
        person["online"] = person["name"].lower() in online_lower
        person["active"] = _recent(person["last_active"], cutoff)
    names = {p["name"].lower() for p in board["people"] if p["active"] and p["name"] != "Guest"}
    return {
        "active_days": ACTIVE_DAYS,
        "active_people": len(names),
        "online_now": online,
        "board": board,
    }
