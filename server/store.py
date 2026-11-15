import json
import shutil
import uuid
from pathlib import Path
from datetime import datetime, timezone

from . import db
from .paths import AGENTS_DIR, agent_dir, ensure_agent_dirs, shared_workspace_dir


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


DEFAULT_FOLDER_TOOLS = ["office", "documents"]


def create_workspace(name: str) -> dict:
    from . import sandbox

    workspace_id = str(uuid.uuid4())
    shared_workspace_dir(workspace_id)
    created = now_iso()
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO workspaces (id, name, created_at, tools_json) VALUES (?, ?, ?, ?)",
            # Files are the point of a folder, so new folders can read and edit them from the start.
            (workspace_id, name.strip() or "Shared", created, json.dumps(DEFAULT_FOLDER_TOOLS)),
        )
    sandbox.ensure_layout(workspace_id)
    return get_workspace(workspace_id)


def get_workspace(workspace_id: str) -> dict | None:
    if not workspace_id:
        return None
    with db.cursor() as cur:
        row = cur.execute("SELECT * FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
    return _public_workspace(db.row_to_dict(row))


def _public_workspace(workspace: dict | None) -> dict | None:
    if not workspace:
        return None
    from . import sandbox

    raw = workspace.get("tools_json")
    if not raw:
        workspace["tools"] = ["web", "office", "documents"]
    else:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = []
        workspace["tools"] = [item for item in parsed if isinstance(item, str)]
    workspace_id = workspace["id"]
    drive = (workspace.get("drive_path") or "").strip()
    workspace["drive_path"] = drive
    try:
        root = sandbox.ensure_layout(workspace_id)
        workspace["root_path"] = str(root)
        workspace["rules"] = sandbox.discover_rules(workspace_id)
        workspace["skills"] = sandbox.discover_skills(workspace_id)
    except Exception:
        workspace["root_path"] = drive or str(shared_workspace_dir(workspace_id))
        workspace["rules"] = []
        workspace["skills"] = []
    workspace.pop("tools_json", None)
    workspace.pop("rules_json", None)
    workspace.pop("skills_json", None)
    return workspace


def workspace_by_name(name: str) -> dict | None:
    wanted = (name or "").strip().lower()
    if not wanted:
        return None
    with db.cursor() as cur:
        rows = cur.execute("SELECT * FROM workspaces ORDER BY created_at ASC").fetchall()
    for row in rows:
        item = db.row_to_dict(row)
        if item["name"].strip().lower() == wanted:
            return item
    return None


def list_workspaces() -> list[dict]:
    with db.cursor() as cur:
        rows = cur.execute("SELECT * FROM workspaces ORDER BY created_at ASC").fetchall()
    active = list_agents(archived=False)
    workspaces = []
    for row in rows:
        item = _public_workspace(db.row_to_dict(row))
        item["agents"] = [agent for agent in active if agent.get("workspace_id") == item["id"]]
        workspaces.append(item)
    return workspaces


def create_agent(payload: dict) -> dict:
    agent_id = str(uuid.uuid4())
    workspace_id = payload.get("workspace_id")
    if not workspace_id:
        workspace_id = create_workspace(payload.get("workspace_name") or payload["name"])["id"]
    elif not get_workspace(workspace_id):
        raise ValueError("workspace not found")
    shared_workspace_dir(workspace_id)
    ensure_agent_dirs(agent_id)
    created = now_iso()
    with db.cursor() as cur:
        cur.execute(
            """
            INSERT INTO agents (id, slug, name, emoji, color, tagline, favicon_svg,
                                system_prompt, notes, status, created_at, workspace_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                agent_id,
                agent_id,
                payload["name"],
                payload.get("emoji"),
                payload.get("color"),
                payload.get("tagline"),
                payload.get("favicon_svg"),
                payload.get("system_prompt") or "",
                payload.get("notes") or "",
                "idle",
                created,
                workspace_id,
            ),
        )
    return get_agent(agent_id)


def migrate_workspaces() -> None:
    with db.cursor() as cur:
        rows = cur.execute(
            "SELECT id, name, workspace_id FROM agents WHERE workspace_id IS NULL OR workspace_id = ''"
        ).fetchall()
    for row in rows:
        agent_id = row["id"]
        workspace = create_workspace(row["name"] or "Shared")
        old = AGENTS_DIR / agent_id / "workspace"
        dest_root = shared_workspace_dir(workspace["id"])
        if old.exists():
            for child in old.iterdir():
                target = dest_root / child.name
                if not target.exists():
                    shutil.move(str(child), str(target))
        with db.cursor() as cur:
            cur.execute(
                "UPDATE agents SET workspace_id = ? WHERE id = ?",
                (workspace["id"], agent_id),
            )


def _public_agent(agent: dict | None) -> dict | None:
    if not agent:
        return None
    agent["archived"] = bool(agent.get("archived"))
    agent["effort"] = clamp_effort(agent.get("effort"))
    workspace = get_workspace(agent.get("workspace_id"))
    agent["workspace_name"] = workspace["name"] if workspace else ""
    return agent


def list_agents(archived: bool = False) -> list[dict]:
    with db.cursor() as cur:
        rows = cur.execute(
            "SELECT * FROM agents WHERE COALESCE(archived, 0) = ? ORDER BY created_at DESC",
            (1 if archived else 0,),
        ).fetchall()
    return [_public_agent(db.row_to_dict(r)) for r in rows]


def get_agent(agent_id: str) -> dict | None:
    with db.cursor() as cur:
        row = cur.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
    return _public_agent(db.row_to_dict(row))


def update_agent(agent_id: str, fields: dict) -> dict | None:
    allowed = {
        "name",
        "system_prompt",
        "notes",
        "status",
        "emoji",
        "color",
        "tagline",
        "archived",
        "workspace_id",
        "effort",
    }
    sets = []
    values = []
    for key, value in fields.items():
        if key in allowed:
            sets.append(f"{key} = ?")
            values.append(value)
    if not sets:
        return get_agent(agent_id)
    values.append(agent_id)
    with db.cursor() as cur:
        cur.execute(f"UPDATE agents SET {', '.join(sets)} WHERE id = ?", values)
    return get_agent(agent_id)


def set_workspace_tools(workspace_id: str, tools: list[str]) -> dict | None:
    if not get_workspace(workspace_id):
        return None
    from . import mcp_builtin

    cleaned = []
    for item in tools:
        if item in cleaned or not mcp_builtin.known_pack(item):
            continue
        cleaned.append(item)
    with db.cursor() as cur:
        cur.execute(
            "UPDATE workspaces SET tools_json = ? WHERE id = ?",
            (json.dumps(cleaned), workspace_id),
        )
    return get_workspace(workspace_id)


def rename_workspace(workspace_id: str, name: str) -> dict | None:
    cleaned = (name or "").strip()
    if not cleaned or not get_workspace(workspace_id):
        return None
    with db.cursor() as cur:
        cur.execute("UPDATE workspaces SET name = ? WHERE id = ?", (cleaned, workspace_id))
    return get_workspace(workspace_id)


def normalize_drive_path(value) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        return ""
    path = Path(cleaned).expanduser().resolve()
    if not path.is_dir():
        raise ValueError("That path is not a folder on this machine.")
    return str(path)


def patch_workspace(workspace_id: str, fields: dict) -> dict | None:
    if not get_workspace(workspace_id):
        return None
    sets = []
    values = []
    if "name" in fields:
        name = (fields.get("name") or "").strip()
        if not name:
            raise ValueError("Name is required.")
        sets.append("name = ?")
        values.append(name)
    if "drive_path" in fields:
        sets.append("drive_path = ?")
        values.append(normalize_drive_path(fields.get("drive_path")))
    if not sets:
        return get_workspace(workspace_id)
    values.append(workspace_id)
    with db.cursor() as cur:
        cur.execute(f"UPDATE workspaces SET {', '.join(sets)} WHERE id = ?", values)
    if "drive_path" in fields:
        from . import sandbox

        sandbox.ensure_layout(workspace_id)
    return get_workspace(workspace_id)


def workspace_agent_count(workspace_id: str) -> int:
    with db.cursor() as cur:
        row = cur.execute(
            "SELECT COUNT(*) AS n FROM agents WHERE workspace_id = ?",
            (workspace_id,),
        ).fetchone()
    return int(row["n"] if row else 0)


def delete_workspace(workspace_id: str) -> bool:
    if workspace_agent_count(workspace_id):
        return False
    with db.cursor() as cur:
        cur.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))
    shutil.rmtree(shared_workspace_dir(workspace_id), ignore_errors=True)
    return True


def delete_agent(agent_id: str) -> None:
    with db.cursor() as cur:
        cur.execute("DELETE FROM schedules WHERE agent_id = ?", (agent_id,))
        cur.execute("DELETE FROM messages WHERE agent_id = ?", (agent_id,))
        cur.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
    shutil.rmtree(agent_dir(agent_id), ignore_errors=True)


def clamp_effort(value) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 12
    return max(1, min(50, number))


def list_schedules(agent_id: str) -> list[dict]:
    with db.cursor() as cur:
        rows = cur.execute(
            "SELECT * FROM schedules WHERE agent_id = ? ORDER BY created_at ASC",
            (agent_id,),
        ).fetchall()
    return [db.row_to_dict(row) for row in rows]


def create_schedule(agent_id: str, fields: dict) -> dict:
    schedule_id = str(uuid.uuid4())
    created = now_iso()
    with db.cursor() as cur:
        cur.execute(
            """
            INSERT INTO schedules (
                id, agent_id, instruction, mode, run_at, every_minutes,
                enabled, next_run_at, last_run_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, NULL, ?)
            """,
            (
                schedule_id,
                agent_id,
                fields["instruction"],
                fields["mode"],
                fields.get("run_at"),
                fields.get("every_minutes"),
                fields["next_run_at"],
                created,
            ),
        )
    return get_schedule(schedule_id)


def get_schedule(schedule_id: str) -> dict | None:
    with db.cursor() as cur:
        row = cur.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,)).fetchone()
    return db.row_to_dict(row)


def delete_schedule(agent_id: str, schedule_id: str) -> bool:
    with db.cursor() as cur:
        cur.execute(
            "DELETE FROM schedules WHERE id = ? AND agent_id = ?",
            (schedule_id, agent_id),
        )
        return cur.rowcount > 0


def claim_due_schedules(now: str) -> list[dict]:
    from datetime import datetime, timedelta, timezone

    claimed = []
    with db.cursor() as cur:
        rows = cur.execute(
            """
            SELECT * FROM schedules
            WHERE enabled = 1 AND next_run_at IS NOT NULL AND next_run_at <= ?
            ORDER BY next_run_at ASC
            """,
            (now,),
        ).fetchall()
        for row in rows:
            job = db.row_to_dict(row)
            agent = cur.execute("SELECT status, archived FROM agents WHERE id = ?", (job["agent_id"],)).fetchone()
            if not agent or agent["archived"] or agent["status"] == "running":
                continue
            if job["mode"] == "once":
                updated = cur.execute(
                    """
                    UPDATE schedules
                    SET enabled = 0, last_run_at = ?, next_run_at = NULL
                    WHERE id = ? AND enabled = 1 AND next_run_at <= ?
                    """,
                    (now, job["id"], now),
                )
            else:
                minutes = max(1, int(job.get("every_minutes") or 60))
                nxt = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()
                updated = cur.execute(
                    """
                    UPDATE schedules
                    SET last_run_at = ?, next_run_at = ?
                    WHERE id = ? AND enabled = 1 AND next_run_at <= ?
                    """,
                    (now, nxt, job["id"], now),
                )
            if updated.rowcount:
                claimed.append(job)
    return claimed


def add_message(agent_id: str, role: str, content: str, meta: dict | None = None) -> dict:
    msg = {
        "id": str(uuid.uuid4()),
        "agent_id": agent_id,
        "role": role,
        "content": content or "",
        "meta_json": json.dumps(meta or {}),
        "created_at": now_iso(),
    }
    with db.cursor() as cur:
        cur.execute(
            """
            INSERT INTO messages (id, agent_id, role, content, meta_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (msg["id"], msg["agent_id"], msg["role"], msg["content"], msg["meta_json"], msg["created_at"]),
        )
    return public_message(msg)


def list_messages(agent_id: str) -> list[dict]:
    with db.cursor() as cur:
        rows = cur.execute(
            "SELECT * FROM messages WHERE agent_id = ? ORDER BY created_at ASC",
            (agent_id,),
        ).fetchall()
    return [public_message(db.row_to_dict(r)) for r in rows]


def public_message(row: dict) -> dict:
    meta = {}
    raw = row.get("meta_json")
    if raw:
        try:
            meta = json.loads(raw)
        except json.JSONDecodeError:
            meta = {}
    return {
        "id": row["id"],
        "agent_id": row["agent_id"],
        "role": row["role"],
        "content": row["content"],
        "meta": meta,
        "created_at": row["created_at"],
    }
