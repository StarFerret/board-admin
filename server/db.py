import sqlite3
import threading
from contextlib import contextmanager

from .paths import DATA_DIR, DB_PATH

_local = threading.local()


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def get_conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = _connect()
        _local.conn = conn
    return conn


@contextmanager
def cursor():
    conn = get_conn()
    cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def init_db() -> None:
    with cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS agents (
                id TEXT PRIMARY KEY,
                slug TEXT,
                name TEXT NOT NULL,
                emoji TEXT,
                color TEXT,
                tagline TEXT,
                favicon_svg TEXT,
                system_prompt TEXT,
                notes TEXT,
                status TEXT,
                created_at TEXT,
                archived INTEGER NOT NULL DEFAULT 0,
                workspace_id TEXT,
                effort INTEGER NOT NULL DEFAULT 12
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT,
                meta_json TEXT,
                created_at TEXT,
                FOREIGN KEY(agent_id) REFERENCES agents(id)
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_agent ON messages(agent_id, created_at)"
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS workspaces (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT,
                tools_json TEXT,
                drive_path TEXT,
                rules_json TEXT,
                skills_json TEXT
            )
            """
        )
        columns = {row[1] for row in cur.execute("PRAGMA table_info(agents)")}
        if "archived" not in columns:
            cur.execute("ALTER TABLE agents ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
        if "workspace_id" not in columns:
            cur.execute("ALTER TABLE agents ADD COLUMN workspace_id TEXT")
        if "effort" not in columns:
            cur.execute("ALTER TABLE agents ADD COLUMN effort INTEGER NOT NULL DEFAULT 12")
        ws_columns = {row[1] for row in cur.execute("PRAGMA table_info(workspaces)")}
        if "tools_json" not in ws_columns:
            cur.execute("ALTER TABLE workspaces ADD COLUMN tools_json TEXT")
            cur.execute(
                """
                UPDATE workspaces
                SET tools_json = ?
                WHERE tools_json IS NULL OR tools_json = ''
                """,
                ('["web","office","documents"]',),
            )
        if "drive_path" not in ws_columns:
            cur.execute("ALTER TABLE workspaces ADD COLUMN drive_path TEXT")
        if "rules_json" not in ws_columns:
            cur.execute("ALTER TABLE workspaces ADD COLUMN rules_json TEXT")
            cur.execute(
                """
                UPDATE workspaces
                SET rules_json = ?
                WHERE rules_json IS NULL OR rules_json = ''
                """,
                ('[]',),
            )
        if "skills_json" not in ws_columns:
            cur.execute("ALTER TABLE workspaces ADD COLUMN skills_json TEXT")
            cur.execute(
                """
                UPDATE workspaces
                SET skills_json = ?
                WHERE skills_json IS NULL OR skills_json = ''
                """,
                ('[]',),
            )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schedules (
                id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                instruction TEXT NOT NULL,
                mode TEXT NOT NULL,
                run_at TEXT,
                every_minutes INTEGER,
                enabled INTEGER NOT NULL DEFAULT 1,
                next_run_at TEXT,
                last_run_at TEXT,
                created_at TEXT,
                FOREIGN KEY(agent_id) REFERENCES agents(id)
            )
            """
        )
        # One row per turn. Written by usage.py, read (read only) by Control.
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS usage_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'board',
                person TEXT NOT NULL,
                agent_id TEXT,
                workspace_id TEXT,
                model TEXT,
                model_calls INTEGER NOT NULL DEFAULT 0,
                prompt_tokens INTEGER NOT NULL DEFAULT 0,
                completion_tokens INTEGER NOT NULL DEFAULT 0,
                duration_ms INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'done'
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_usage_created ON usage_events(created_at)")


def get_setting(key: str, default=None):
    with cursor() as cur:
        row = cur.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row is None:
        return default
    return row["value"]


def set_setting(key: str, value: str) -> None:
    with cursor() as cur:
        cur.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def row_to_dict(row) -> dict:
    if row is None:
        return None
    return dict(row)