"""Board-wide MCP servers stored as JSON files under data/mcp/servers/.

Each server can be assigned to one or more workspaces (or all). Agents in those
folders get the server's tools during a turn.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .paths import DATA_DIR

MCP_DIR = DATA_DIR / "mcp"
SERVERS_DIR = MCP_DIR / "servers"

_SAFE = re.compile(r"[^a-zA-Z0-9._-]+")


def ensure_dirs() -> Path:
    SERVERS_DIR.mkdir(parents=True, exist_ok=True)
    return SERVERS_DIR


def _slug(name: str) -> str:
    cleaned = _SAFE.sub("-", (name or "server").strip().lower()).strip("-")
    return cleaned[:48] or "server"


def _path_for(server_id: str) -> Path:
    return SERVERS_DIR / f"{server_id}.json"


def _public(server: dict) -> dict:
    out = {
        "id": server.get("id"),
        "name": server.get("name") or server.get("id"),
        "transport": server.get("transport") or "stdio",
        "workspaces": list(server.get("workspaces") or []),
        "created_at": server.get("created_at"),
    }
    if out["transport"] == "url":
        out["url"] = server.get("url") or ""
        out["has_headers"] = bool(server.get("headers"))
    else:
        out["command"] = server.get("command") or ""
        out["args"] = list(server.get("args") or [])
        out["has_env"] = bool(server.get("env"))
    return out


def _read(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not data.get("id"):
        return None
    return data


def list_servers() -> list[dict]:
    ensure_dirs()
    items = []
    for path in sorted(SERVERS_DIR.glob("*.json")):
        raw = _read(path)
        if raw:
            items.append(_public(raw))
    return items


def get_server(server_id: str) -> dict | None:
    ensure_dirs()
    return _read(_path_for(server_id))


def get_server_public(server_id: str) -> dict | None:
    raw = get_server(server_id)
    return _public(raw) if raw else None


def save_server(payload: dict) -> dict:
    ensure_dirs()
    name = (payload.get("name") or "").strip()
    if not name:
        raise ValueError("Name is required")

    server_id = (payload.get("id") or "").strip() or _slug(name)
    server_id = _slug(server_id)

    transport = (payload.get("transport") or "").strip().lower()
    url = (payload.get("url") or "").strip()
    command = (payload.get("command") or "").strip()
    if not transport:
        transport = "url" if url else "stdio"
    if transport not in {"url", "stdio"}:
        raise ValueError("transport must be url or stdio")

    existing = get_server(server_id) or {}
    workspaces = payload.get("workspaces")
    if workspaces is None:
        workspaces = existing.get("workspaces") or []
    if not isinstance(workspaces, list):
        raise ValueError("workspaces must be a list of folder ids (or ['*'])")
    workspaces = [str(item).strip() for item in workspaces if str(item).strip()]

    record: dict[str, Any] = {
        "id": server_id,
        "name": name,
        "transport": transport,
        "workspaces": workspaces,
        "created_at": existing.get("created_at") or payload.get("created_at"),
    }
    if not record["created_at"]:
        from datetime import datetime, timezone

        record["created_at"] = datetime.now(timezone.utc).isoformat()

    if transport == "url":
        if not url:
            raise ValueError("url is required for url transport")
        record["url"] = url
        headers = payload.get("headers")
        if headers is None:
            headers = existing.get("headers") or {}
        if not isinstance(headers, dict):
            raise ValueError("headers must be an object")
        record["headers"] = {str(k): str(v) for k, v in headers.items()}
    else:
        if not command:
            raise ValueError("command is required for stdio transport")
        record["command"] = command
        args = payload.get("args")
        if args is None:
            args = existing.get("args") or []
        if not isinstance(args, list):
            raise ValueError("args must be a list")
        record["args"] = [str(a) for a in args]
        env = payload.get("env")
        if env is None:
            env = existing.get("env") or {}
        if not isinstance(env, dict):
            raise ValueError("env must be an object")
        record["env"] = {str(k): str(v) for k, v in env.items()}

    path = _path_for(server_id)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return _public(record)


def delete_server(server_id: str) -> bool:
    path = _path_for(server_id)
    if not path.is_file():
        return False
    path.unlink()
    return True


def set_workspaces(server_id: str, workspace_ids: list[str]) -> dict:
    raw = get_server(server_id)
    if not raw:
        raise ValueError("MCP server not found")
    cleaned = [str(item).strip() for item in workspace_ids if str(item).strip()]
    raw["workspaces"] = cleaned
    path = _path_for(server_id)
    path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    return _public(raw)


def import_cursor_json(blob: dict | list | str) -> list[dict]:
    """Accept Cursor-style { mcpServers: { name: config } } or a single server object."""
    if isinstance(blob, str):
        blob = json.loads(blob)
    if isinstance(blob, list):
        return [save_server(item) for item in blob]

    if not isinstance(blob, dict):
        raise ValueError("JSON must be an object")

    block = blob.get("mcpServers") if "mcpServers" in blob else None
    if isinstance(block, dict):
        saved = []
        for name, cfg in block.items():
            if not isinstance(cfg, dict):
                continue
            payload = {
                "id": _slug(name),
                "name": name,
                "workspaces": blob.get("workspaces") or ["*"],
                **cfg,
            }
            if cfg.get("url"):
                payload["transport"] = "url"
            else:
                payload["transport"] = "stdio"
            saved.append(save_server(payload))
        if not saved:
            raise ValueError("mcpServers was empty")
        return saved

    # Single server document
    if blob.get("command") or blob.get("url") or blob.get("name"):
        return [save_server(blob)]

    raise ValueError(
        'Expected { "mcpServers": { "name": { "command"|"url": ... } } } or one server object'
    )


def servers_for_workspace(workspace_id: str) -> list[dict]:
    """Raw server records enabled for this workspace."""
    ensure_dirs()
    out = []
    for path in sorted(SERVERS_DIR.glob("*.json")):
        raw = _read(path)
        if not raw:
            continue
        assigned = raw.get("workspaces") or []
        if "*" in assigned or workspace_id in assigned:
            out.append(raw)
    return out


def example_json() -> dict:
    return {
        "mcpServers": {
            "example-remote": {
                "url": "https://mcp.example.com/sse",
                "headers": {"Authorization": "Bearer YOUR_TOKEN"},
            },
            "example-local": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-memory"],
                "env": {},
            },
        }
    }
