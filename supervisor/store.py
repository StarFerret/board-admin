import hashlib
import hmac
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from .paths import CONTROL_DB_PATH, ensure_dirs

_local = threading.local()

ROLES = ("admin", "operator", "viewer")
SESSION_DAYS = 14
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 64


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(CONTROL_DB_PATH, check_same_thread=False)
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
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                display_name TEXT,
                created_at TEXT NOT NULL,
                disabled INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
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
            CREATE TABLE IF NOT EXISTS app_state (
                app_id TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 0,
                desired TEXT NOT NULL DEFAULT 'stopped',
                updated_at TEXT
            )
            """
        )


def _ensure_load_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS load_minutes (
            minute INTEGER PRIMARY KEY,
            samples INTEGER NOT NULL DEFAULT 0,
            busy_samples INTEGER NOT NULL DEFAULT 0,
            people_max INTEGER NOT NULL DEFAULT 0
        )
        """
    )


def record_load(at: int, busy: bool, people: Optional[int]) -> None:
    """Add one utilization sample to its minute. Keeps 30 days."""
    minute = int(at) // 60 * 60
    with cursor() as cur:
        _ensure_load_table(cur)
        cur.execute(
            """
            INSERT INTO load_minutes(minute, samples, busy_samples, people_max) VALUES (?, 1, ?, ?)
            ON CONFLICT(minute) DO UPDATE SET
              samples = samples + 1,
              busy_samples = busy_samples + excluded.busy_samples,
              people_max = MAX(people_max, excluded.people_max)
            """,
            (minute, 1 if busy else 0, int(people or 0)),
        )
        if minute % 3600 == 0:
            cur.execute("DELETE FROM load_minutes WHERE minute < ?", (minute - 30 * 86400,))


def delete_load_between(start: int, end: int) -> None:
    """Drop readings from a stretch that was not real use, such as a capacity test."""
    with cursor() as cur:
        _ensure_load_table(cur)
        cur.execute("DELETE FROM load_minutes WHERE minute >= ? AND minute <= ?", (int(start) // 60 * 60, int(end)))


def load_by_hour(since: int) -> list[dict]:
    """Per hour: share of samples the AI was answering, and most people seen at once."""
    with cursor() as cur:
        _ensure_load_table(cur)
        rows = cur.execute(
            """
            SELECT minute / 3600 * 3600 AS hour,
                   SUM(samples) AS samples,
                   SUM(busy_samples) AS busy,
                   MAX(people_max) AS people
            FROM load_minutes WHERE minute >= ? GROUP BY hour ORDER BY hour
            """,
            (int(since),),
        ).fetchall()
    return [
        {
            "hour": int(r["hour"]),
            "samples": int(r["samples"]),
            "busy_percent": round(100 * r["busy"] / r["samples"], 1) if r["samples"] else 0.0,
            "people": int(r["people"] or 0),
        }
        for r in rows
    ]


def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    with cursor() as cur:
        row = cur.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with cursor() as cur:
        cur.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    if salt is None:
        salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt_hex, digest_hex = stored.split("$", 2)
    except ValueError:
        return False
    if algo != "scrypt":
        return False
    salt = bytes.fromhex(salt_hex)
    expected = bytes.fromhex(digest_hex)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return hmac.compare_digest(digest, expected)


def _row_user(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "username": row["username"],
        "role": row["role"],
        "display_name": row["display_name"] or row["username"],
        "created_at": row["created_at"],
        "disabled": bool(row["disabled"]),
    }


def user_count() -> int:
    with cursor() as cur:
        row = cur.execute("SELECT COUNT(*) AS n FROM users").fetchone()
    return int(row["n"] if row else 0)


def bootstrap_needed() -> bool:
    return user_count() == 0


def create_user(username: str, password: str, role: str = "admin", display_name: str = "") -> dict:
    username = (username or "").strip()
    if not username:
        raise ValueError("Username is required")
    if len(password or "") < 8:
        raise ValueError("Password must be at least 8 characters")
    if role not in ROLES:
        raise ValueError(f"Role must be one of {', '.join(ROLES)}")
    user_id = secrets.token_hex(8)
    now = _iso(_utcnow())
    with cursor() as cur:
        cur.execute(
            """
            INSERT INTO users(id, username, password_hash, role, display_name, created_at, disabled)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            (user_id, username, hash_password(password), role, (display_name or username).strip()[:60], now),
        )
    return get_user(user_id)


def get_user(user_id: str) -> Optional[dict]:
    with cursor() as cur:
        row = cur.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _row_user(row) if row else None


def get_user_by_username(username: str) -> Optional[dict]:
    with cursor() as cur:
        row = cur.execute(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE",
            ((username or "").strip(),),
        ).fetchone()
    return _row_user(row) if row else None


def list_users() -> list[dict]:
    with cursor() as cur:
        rows = cur.execute("SELECT * FROM users ORDER BY created_at ASC").fetchall()
    return [_row_user(row) for row in rows]


def set_user_role(user_id: str, role: str) -> dict:
    if role not in ROLES:
        raise ValueError(f"Role must be one of {', '.join(ROLES)}")
    with cursor() as cur:
        cur.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
    user = get_user(user_id)
    if not user:
        raise ValueError("User not found")
    return user


def set_user_disabled(user_id: str, disabled: bool) -> dict:
    with cursor() as cur:
        cur.execute("UPDATE users SET disabled = ? WHERE id = ?", (1 if disabled else 0, user_id))
    user = get_user(user_id)
    if not user:
        raise ValueError("User not found")
    return user


def delete_user(user_id: str) -> None:
    with cursor() as cur:
        cur.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        cur.execute("DELETE FROM users WHERE id = ?", (user_id,))


def reset_all_users() -> None:
    """Wipe Control users + sessions (localhost admin recovery)."""
    with cursor() as cur:
        cur.execute("DELETE FROM sessions")
        cur.execute("DELETE FROM users")


def authenticate(username: str, password: str) -> Optional[dict]:
    with cursor() as cur:
        row = cur.execute(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE",
            ((username or "").strip(),),
        ).fetchone()
    if not row or row["disabled"]:
        return None
    if not verify_password(password, row["password_hash"]):
        return None
    return _row_user(row)


def create_session(user_id: str) -> dict:
    token = secrets.token_urlsafe(32)
    now = _utcnow()
    expires = now + timedelta(days=SESSION_DAYS)
    with cursor() as cur:
        cur.execute(
            "INSERT INTO sessions(token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, user_id, _iso(now), _iso(expires)),
        )
    return {"token": token, "expires_at": _iso(expires)}


def session_user(token: str) -> Optional[dict]:
    if not token:
        return None
    with cursor() as cur:
        row = cur.execute(
            """
            SELECT u.* FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token = ?
            """,
            (token,),
        ).fetchone()
        if not row:
            return None
        exp = cur.execute("SELECT expires_at FROM sessions WHERE token = ?", (token,)).fetchone()
    if not exp:
        return None
    try:
        expires = datetime.fromisoformat(exp["expires_at"])
    except ValueError:
        return None
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < _utcnow() or row["disabled"]:
        revoke_session(token)
        return None
    return _row_user(row)


def revoke_session(token: str) -> None:
    with cursor() as cur:
        cur.execute("DELETE FROM sessions WHERE token = ?", (token,))


def get_app_state(app_id: str) -> dict:
    with cursor() as cur:
        row = cur.execute("SELECT * FROM app_state WHERE app_id = ?", (app_id,)).fetchone()
    if not row:
        return {"app_id": app_id, "enabled": False, "desired": "stopped", "updated_at": None}
    return {
        "app_id": row["app_id"],
        "enabled": bool(row["enabled"]),
        "desired": row["desired"],
        "updated_at": row["updated_at"],
    }


def set_app_state(app_id: str, enabled: Optional[bool] = None, desired: Optional[str] = None) -> dict:
    current = get_app_state(app_id)
    next_enabled = current["enabled"] if enabled is None else bool(enabled)
    next_desired = current["desired"] if desired is None else desired
    now = _iso(_utcnow())
    with cursor() as cur:
        cur.execute(
            """
            INSERT INTO app_state(app_id, enabled, desired, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(app_id) DO UPDATE SET
              enabled = excluded.enabled,
              desired = excluded.desired,
              updated_at = excluded.updated_at
            """,
            (app_id, 1 if next_enabled else 0, next_desired, now),
        )
    return get_app_state(app_id)


def export_meta() -> dict:
    return {
        "control_db": "data/control.db",
        "users": user_count(),
        "bootstrap_needed": bootstrap_needed(),
    }
