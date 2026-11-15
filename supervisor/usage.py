"""Usage summary for Control → Usage: who is using AI, how much, and where.

Reads the Board's `usage_events` table (data/board.db) read only. The Board
writes one row per turn (see server/usage.py). Only Board activity is counted
today; other apps talk to the model runtime directly and are not seen here.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Any

from .paths import BOARD_DB_PATH

MAX_DAYS = 90
SOURCES = ["board"]


def _empty(days: int) -> dict[str, Any]:
    today = datetime.now().date()
    return {
        "days": days,
        "sources": SOURCES,
        "totals": {"messages": 0, "people": 0, "tokens_in": 0, "tokens_out": 0, "tokens": 0},
        "by_day": [
            {"day": (today - timedelta(days=offset)).isoformat(), "messages": 0, "tokens": 0}
            for offset in range(days - 1, -1, -1)
        ],
        "people": [],
        "folders": [],
        "models": [],
    }


def _connect() -> sqlite3.Connection | None:
    if not BOARD_DB_PATH.is_file():
        return None
    conn = sqlite3.connect(f"file:{BOARD_DB_PATH}?mode=ro", uri=True, timeout=3)
    conn.row_factory = sqlite3.Row
    return conn


def summary(days: int = 30) -> dict[str, Any]:
    days = max(1, min(int(days or 30), MAX_DAYS))
    out = _empty(days)
    try:
        conn = _connect()
    except sqlite3.Error:
        return out
    if conn is None:
        return out
    # Days are the machine's local calendar days, today included.
    since = f"-{days - 1} days"
    where = "date(u.created_at, 'localtime') >= date('now', 'localtime', ?)"
    tokens = "COALESCE(SUM(u.prompt_tokens + u.completion_tokens), 0)"
    try:
        row = conn.execute(
            f"""
            SELECT COUNT(*) AS messages, COUNT(DISTINCT u.person) AS people,
                   COALESCE(SUM(u.prompt_tokens), 0) AS tokens_in,
                   COALESCE(SUM(u.completion_tokens), 0) AS tokens_out
            FROM usage_events u WHERE {where}
            """,
            (since,),
        ).fetchone()
        out["totals"] = {
            "messages": row["messages"],
            "people": row["people"],
            "tokens_in": row["tokens_in"],
            "tokens_out": row["tokens_out"],
            "tokens": row["tokens_in"] + row["tokens_out"],
        }
        per_day = {
            r["day"]: r
            for r in conn.execute(
                f"""
                SELECT date(u.created_at, 'localtime') AS day, COUNT(*) AS messages, {tokens} AS tokens
                FROM usage_events u WHERE {where} GROUP BY day
                """,
                (since,),
            )
        }
        for item in out["by_day"]:
            hit = per_day.get(item["day"])
            if hit:
                item["messages"] = hit["messages"]
                item["tokens"] = hit["tokens"]
        out["people"] = [
            dict(r)
            for r in conn.execute(
                f"""
                SELECT u.person AS name, COUNT(*) AS messages, {tokens} AS tokens,
                       MAX(u.created_at) AS last_active
                FROM usage_events u WHERE {where}
                GROUP BY u.person ORDER BY messages DESC, name ASC LIMIT 200
                """,
                (since,),
            )
        ]
        out["folders"] = [
            dict(r)
            for r in conn.execute(
                f"""
                SELECT u.workspace_id AS id, COALESCE(w.name, 'Deleted folder') AS name,
                       COUNT(*) AS messages, COUNT(DISTINCT u.person) AS people, {tokens} AS tokens
                FROM usage_events u LEFT JOIN workspaces w ON w.id = u.workspace_id
                WHERE {where}
                GROUP BY u.workspace_id ORDER BY messages DESC LIMIT 50
                """,
                (since,),
            )
        ]
        out["models"] = [
            dict(r)
            for r in conn.execute(
                f"""
                SELECT COALESCE(NULLIF(u.model, ''), 'No reply') AS name,
                       COUNT(*) AS messages, {tokens} AS tokens
                FROM usage_events u WHERE {where}
                GROUP BY name ORDER BY messages DESC LIMIT 20
                """,
                (since,),
            )
        ]
    except sqlite3.Error:
        # An older Board that has not created the table yet: show an empty page.
        return _empty(days)
    finally:
        conn.close()
    return out
