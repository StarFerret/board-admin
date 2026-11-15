import json
import os
import socket
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory, send_file
from flask_cors import CORS
from flask_socketio import SocketIO, join_room, leave_room
from werkzeug.utils import secure_filename

from . import db, identity, mcp_builtin, mcp_registry, mcp_runtime, ollama_client, sandbox, store
from .harness import run_turn, stop_turn
from .paths import DEFAULT_PORT, WEB_DIST, ensure_agent_dirs
from .scheduler import start as start_scheduler

app = Flask(__name__, static_folder=None)
CORS(app, resources={r"/api/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

db.init_db()
store.migrate_workspaces()
mcp_registry.ensure_dirs()
start_scheduler(socketio)


def _broadcast_model_failover(before: str, after: str) -> None:
    payload = {"from": before, "to": after}
    socketio.emit("ollama_model", payload, to="board")
    # Also fan out to any open agent rooms listening on the board socket.
    for agent in store.list_agents(archived=False):
        socketio.emit("ollama_model", payload, to=f"agent:{agent['id']}")


ollama_client.set_failover_listener(_broadcast_model_failover)

_presence: dict[str, dict] = {}
_board_sids: set[str] = set()
_presence_lock = threading.Lock()


def _clean_name(value) -> str:
    name = (value or "").strip()
    return (name[:40] or "Guest")


def _agent_roster(agent_id: str) -> list[str]:
    with _presence_lock:
        names = [
            entry["name"]
            for entry in _presence.values()
            if entry.get("agent_id") == agent_id
        ]
    return sorted(set(names))


def _board_roster() -> list[str]:
    with _presence_lock:
        names = [entry["name"] for sid, entry in _presence.items() if sid in _board_sids]
    return sorted(set(names))


def _workspace_roster(workspace_id: str) -> list[str]:
    with _presence_lock:
        names = [
            entry["name"]
            for entry in _presence.values()
            if entry.get("workspace_id") == workspace_id
        ]
    return sorted(set(names))


def _presence_count(agent_id: str) -> int:
    return len(_agent_roster(agent_id))


def _emit_presence(agent_id: str) -> None:
    people = _agent_roster(agent_id)
    socketio.emit(
        "presence",
        {"id": agent_id, "count": len(people), "people": people},
        to=f"agent:{agent_id}",
    )


def _board_count() -> int:
    return len(_board_roster())


def _emit_board_presence() -> None:
    people = _board_roster()
    socketio.emit(
        "presence",
        {"board": True, "count": len(people), "people": people},
        to="board",
    )


def _emit_workspace_presence(workspace_id: str | None) -> None:
    if not workspace_id:
        return
    people = _workspace_roster(workspace_id)
    socketio.emit(
        "presence",
        {"workspace": workspace_id, "count": len(people), "people": people},
        to=f"workspace:{workspace_id}",
    )


def _default_route_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return ""
    finally:
        sock.close()


def host_ips() -> list[str]:
    override = (os.environ.get("STARFERRET_HOST") or "").strip()
    if override:
        return [override]
    found: list[str] = []
    primary = _default_route_ip()
    if primary:
        found.append(primary)
    try:
        _name, _aliases, ips = socket.gethostbyname_ex(socket.gethostname())
        found.extend(ips)
    except OSError:
        pass
    ordered: list[str] = []
    for ip in found:
        if ip.startswith("127.") or ip.startswith("169.254."):
            continue
        if ip not in ordered:
            ordered.append(ip)
    return ordered or ["127.0.0.1"]


def _port_available(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _accepts_connections(ip: str, port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.4)
    try:
        sock.connect((ip, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def lan_ip() -> str:
    port = int(os.environ.get("PORT", str(DEFAULT_PORT)))
    if request:
        host = request.host or ""
        if ":" in host and host.split(":")[-1].isdigit():
            port = int(host.split(":")[-1])
    ips = host_ips()
    for ip in ips:
        if _accepts_connections(ip, port):
            return ip
    return ips[0]


def share_origin() -> str:
    hostname = (request.host or "").split(":")[0]
    local = hostname in {"127.0.0.1", "localhost", "::1"}
    if local:
        port = (
            request.host.split(":")[-1]
            if ":" in (request.host or "")
            else str(DEFAULT_PORT)
        )
        return f"http://{lan_ip()}:{port}"
    return f"{request.scheme}://{request.host}"


def ollama_status() -> dict:
    installed = ollama_client.cli_installed()
    saved = db.get_setting("ollama_base_url")
    base_url = saved
    reachable = False
    models = []
    error = None

    candidates = []
    if saved:
        candidates.append(saved)
    candidates.append(ollama_client.DEFAULT_LOCAL)

    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        result = ollama_client.probe(candidate)
        if result["ok"]:
            reachable = True
            models = result["models"]
            base_url = candidate
            if saved != candidate:
                db.set_setting("ollama_base_url", candidate)
            error = None
            break
        error = result["error"]

    preferred = db.get_setting("ollama_model") or os.environ.get("OLLAMA_MODEL")
    model = ollama_client.resolve_model(models, preferred)
    if reachable and model:
        db.set_setting("ollama_model", model)

    return {
        "installed": installed,
        "reachable": reachable,
        "base_url": base_url if reachable else saved,
        "models": models,
        "error": error,
        "model": model,
        "docker": sandbox.docker_available(),
        "failover_ladder": ollama_client.FAILOVER_LADDER,
    }


DEFAULT_BOARD_NAME = "Workspaces"


def board_name() -> str:
    saved = (db.get_setting("board_name") or "").strip()
    return saved[:48] or DEFAULT_BOARD_NAME


@app.get("/api/presence")
def get_presence():
    """Display names with the Board open right now. Control → People reads this."""
    with _presence_lock:
        names = sorted({entry["name"] for entry in _presence.values() if entry.get("name")})
    return jsonify({"people": names, "count": len(names)})


@app.get("/api/settings/host")
def get_share_host():
    origin = share_origin()
    control_port = int(os.environ.get("CONTROL_PORT", "7411"))
    return jsonify(
        {
            "origin": origin,
            "lan_ip": lan_ip(),
            "board_name": board_name(),
            "control_port": control_port,
        }
    )


@app.post("/api/settings/board")
def set_board_name():
    body = request.get_json(force=True, silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Name is required"}), 400
    name = name[:48]
    db.set_setting("board_name", name)
    socketio.emit("board_name", {"name": name}, to="board")
    return jsonify({"name": name})


@app.get("/api/settings/ollama")
def get_ollama_settings():
    return jsonify(ollama_status())


@app.post("/api/settings/ollama")
def set_ollama_settings():
    body = request.get_json(force=True, silent=True) or {}
    raw = (body.get("base_url") or body.get("url") or "").strip()
    requested_model = (body.get("model") or "").strip()
    if raw:
        try:
            normalized = ollama_client.normalize_base_url(raw)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
    else:
        normalized = db.get_setting("ollama_base_url")
        if not normalized:
            return jsonify({"error": "Set an Ollama host first."}), 400
    result = ollama_client.probe(normalized, timeout=5)
    if not result["ok"]:
        return jsonify({"error": f"Could not reach Ollama at {normalized}: {result['error']}"}), 400
    db.set_setting("ollama_base_url", normalized)
    if requested_model:
        if requested_model not in result["models"]:
            chain = ollama_client.failover_model_chain(requested_model, result["models"])
            fallback_model = next((name for name in chain if name != requested_model), None)
            if not fallback_model and result["models"]:
                fallback_model = sorted(
                    result["models"], key=ollama_client.estimate_model_billions
                )[0]
            if fallback_model:
                db.set_setting("ollama_model", fallback_model)
                status = ollama_status()
                status["switched_from"] = requested_model
                status["fallback"] = True
                return jsonify(status)
            return jsonify({"error": "No models available on Ollama"}), 400
        db.set_setting("ollama_model", requested_model)
    elif not raw:
        return jsonify({"error": "Choose a model or a host."}), 400
    return jsonify(ollama_status())


@app.get("/api/workspaces")
def api_list_workspaces():
    return jsonify({"workspaces": store.list_workspaces()})


@app.post("/api/workspaces")
def api_create_workspace():
    body = request.get_json(force=True, silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Name is required"}), 400
    existing = store.workspace_by_name(name)
    if existing:
        return jsonify(existing)
    created = store.create_workspace(name)
    socketio.emit("workspace", created, to="board")
    return jsonify(created), 201


def _folder_path(folder: str, filename: str) -> str | None:
    name = secure_filename(filename or "")
    if not name:
        return None
    parts = []
    for piece in (folder or "").replace("\\", "/").split("/"):
        cleaned = secure_filename(piece)
        if cleaned:
            parts.append(cleaned)
    return "/".join(parts + [name])


def _emit_folder_files(workspace_id: str) -> list[dict]:
    files = sandbox.list_workspace_files(workspace_id)
    socketio.emit("files", {"files": files}, to=f"workspace:{workspace_id}")
    return files


@app.get("/api/tools")
def api_tools():
    return jsonify(mcp_builtin.catalog())


@app.get("/api/mcp/servers")
def api_list_mcp_servers():
    return jsonify({"servers": mcp_registry.list_servers(), "example": mcp_registry.example_json()})


@app.post("/api/mcp/servers")
def api_create_mcp_server():
    body = request.get_json(force=True, silent=True) or {}
    try:
        if "mcpServers" in body:
            saved = mcp_registry.import_cursor_json(body)
            return jsonify({"servers": saved}), 201
        saved = mcp_registry.save_server(body)
        return jsonify(saved), 201
    except (ValueError, json.JSONDecodeError) as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/mcp/servers/import")
def api_import_mcp_servers():
    body = request.get_json(force=True, silent=True) or {}
    blob = body.get("json", body)
    if isinstance(blob, str):
        try:
            blob = json.loads(blob)
        except json.JSONDecodeError as exc:
            return jsonify({"error": f"Invalid JSON: {exc}"}), 400
    try:
        saved = mcp_registry.import_cursor_json(blob)
        return jsonify({"servers": saved}), 201
    except (ValueError, json.JSONDecodeError) as exc:
        return jsonify({"error": str(exc)}), 400


@app.patch("/api/mcp/servers/<server_id>")
def api_patch_mcp_server(server_id: str):
    body = request.get_json(force=True, silent=True) or {}
    raw = mcp_registry.get_server(server_id)
    if not raw:
        return jsonify({"error": "Not found"}), 404
    try:
        payload = {**raw, **body, "id": server_id}
        if "workspaces" in body:
            payload["workspaces"] = body["workspaces"]
        return jsonify(mcp_registry.save_server(payload))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.put("/api/mcp/servers/<server_id>/workspaces")
def api_set_mcp_workspaces(server_id: str):
    body = request.get_json(force=True, silent=True) or {}
    ids = body.get("workspaces")
    if not isinstance(ids, list):
        return jsonify({"error": "workspaces must be a list"}), 400
    try:
        return jsonify(mcp_registry.set_workspaces(server_id, ids))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/mcp/servers/<server_id>/probe")
def api_probe_mcp_server(server_id: str):
    try:
        return jsonify(mcp_runtime.probe_server(server_id))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.delete("/api/mcp/servers/<server_id>")
def api_delete_mcp_server(server_id: str):
    if not mcp_registry.delete_server(server_id):
        return jsonify({"error": "Not found"}), 404
    return jsonify({"ok": True})


@app.post("/api/workspaces/<workspace_id>/share")
def api_share_workspace(workspace_id: str):
    """Return the share URL for this folder (LAN origin when available)."""
    if not store.get_workspace(workspace_id):
        return jsonify({"error": "Not found"}), 404
    origin = share_origin()
    url = f"{origin}/w/{workspace_id}"
    return jsonify({"url": url, "origin": origin})


@app.get("/api/workspaces/<workspace_id>")
def api_get_workspace(workspace_id: str):
    workspace = store.get_workspace(workspace_id)
    if not workspace:
        return jsonify({"error": "Not found"}), 404
    agents = [
        agent
        for agent in store.list_agents(archived=False)
        if agent.get("workspace_id") == workspace_id
    ]
    workspace["agents"] = agents
    workspace["files"] = sandbox.list_workspace_files(workspace_id)
    workspace["mcp_servers"] = [
        {"id": s["id"], "name": s.get("name") or s["id"]}
        for s in mcp_registry.servers_for_workspace(workspace_id)
    ]
    return jsonify(workspace)


@app.post("/api/workspaces/<workspace_id>/tools")
def api_add_workspace_tool(workspace_id: str):
    workspace = store.get_workspace(workspace_id)
    if not workspace:
        return jsonify({"error": "Not found"}), 404
    body = request.get_json(force=True, silent=True) or {}
    pack_id = (body.get("id") or "").strip()
    if not mcp_builtin.known_pack(pack_id):
        return jsonify({"error": "Unknown tool"}), 400
    tools = list(workspace.get("tools") or [])
    if pack_id not in tools:
        tools.append(pack_id)
    updated = store.set_workspace_tools(workspace_id, tools)
    socketio.emit("workspace", updated, to="board")
    socketio.emit("workspace", updated, to=f"workspace:{workspace_id}")
    return jsonify(updated)


@app.delete("/api/workspaces/<workspace_id>/tools/<pack_id>")
def api_remove_workspace_tool(workspace_id: str, pack_id: str):
    workspace = store.get_workspace(workspace_id)
    if not workspace:
        return jsonify({"error": "Not found"}), 404
    tools = [item for item in (workspace.get("tools") or []) if item != pack_id]
    updated = store.set_workspace_tools(workspace_id, tools)
    socketio.emit("workspace", updated, to="board")
    socketio.emit("workspace", updated, to=f"workspace:{workspace_id}")
    return jsonify(updated)


@app.post("/api/workspaces/<workspace_id>/files")
def api_upload_workspace_files(workspace_id: str):
    if not store.get_workspace(workspace_id):
        return jsonify({"error": "Not found"}), 404
    uploaded = request.files.getlist("files") or []
    if "file" in request.files:
        uploaded.append(request.files["file"])
    if not uploaded:
        return jsonify({"error": "No files"}), 400
    folder = request.form.get("folder") or ""
    saved = []
    for fh in uploaded:
        if not fh or not fh.filename:
            continue
        rel = _folder_path(folder, fh.filename)
        if not rel:
            continue
        dest = sandbox.workspace_jail(workspace_id, rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        fh.save(dest)
        saved.append(rel)
    files = _emit_folder_files(workspace_id)
    return jsonify({"saved": saved, "files": files}), 201


@app.get("/api/workspaces/<workspace_id>/files/<path:relpath>")
def api_download_workspace_file(workspace_id: str, relpath: str):
    if not store.get_workspace(workspace_id):
        return jsonify({"error": "Not found"}), 404
    try:
        path = sandbox.workspace_jail(workspace_id, relpath)
    except sandbox.SandboxError:
        return jsonify({"error": "Invalid path"}), 400
    if not path.is_file():
        return jsonify({"error": "Not found"}), 404
    return send_file(path, as_attachment=True, download_name=path.name)


@app.delete("/api/workspaces/<workspace_id>/files/<path:relpath>")
def api_delete_workspace_file(workspace_id: str, relpath: str):
    if not store.get_workspace(workspace_id):
        return jsonify({"error": "Not found"}), 404
    try:
        sandbox.delete_workspace_entry(workspace_id, relpath)
    except sandbox.SandboxError as exc:
        return jsonify({"error": str(exc)}), 400
    files = _emit_folder_files(workspace_id)
    listing = sandbox.list_dir(workspace_id, str(Path(relpath).parent).replace("\\", "/"))
    return jsonify({"files": files, "browse": listing})


@app.get("/api/workspaces/<workspace_id>/browse")
def api_browse_workspace(workspace_id: str):
    if not store.get_workspace(workspace_id):
        return jsonify({"error": "Not found"}), 404
    rel = (request.args.get("path") or "").strip() or "."
    try:
        return jsonify(sandbox.list_dir(workspace_id, rel))
    except sandbox.SandboxError as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/workspaces/<workspace_id>/mkdir")
def api_mkdir_workspace(workspace_id: str):
    if not store.get_workspace(workspace_id):
        return jsonify({"error": "Not found"}), 404
    body = request.get_json(force=True, silent=True) or {}
    rel = (body.get("path") or "").strip()
    if not rel:
        return jsonify({"error": "Path is required"}), 400
    try:
        listing = sandbox.mkdir(workspace_id, rel)
    except sandbox.SandboxError as exc:
        return jsonify({"error": str(exc)}), 400
    files = _emit_folder_files(workspace_id)
    listing["files"] = files
    return jsonify(listing), 201


@app.patch("/api/workspaces/<workspace_id>")
def api_patch_workspace(workspace_id: str):
    body = request.get_json(force=True, silent=True) or {}
    try:
        updated = store.patch_workspace(workspace_id, body)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if not updated:
        return jsonify({"error": "Could not update that folder"}), 400
    socketio.emit("workspace", updated, to="board")
    socketio.emit("workspace", updated, to=f"workspace:{workspace_id}")
    return jsonify(updated)


@app.delete("/api/workspaces/<workspace_id>")
def api_delete_workspace(workspace_id: str):
    if not store.get_workspace(workspace_id):
        return jsonify({"error": "Not found"}), 404
    if not store.delete_workspace(workspace_id):
        return jsonify({"error": "Move the agents out before deleting this folder."}), 400
    socketio.emit("workspace_deleted", {"id": workspace_id}, to="board")
    return jsonify({"ok": True})


@app.get("/api/agents")
def api_list_agents():
    archived = request.args.get("archived") in {"1", "true", "yes"}
    return jsonify({"agents": store.list_agents(archived=archived)})


@app.post("/api/agents")
def api_create_agent():
    body = request.get_json(force=True, silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Name is required"}), 400
    workspace_id = (body.get("workspace_id") or "").strip()
    workspace_name = (body.get("workspace_name") or "").strip()
    if workspace_id:
        if not store.get_workspace(workspace_id):
            return jsonify({"error": "Workspace not found"}), 400
    elif workspace_name:
        existing = store.workspace_by_name(workspace_name)
        workspace_id = existing["id"] if existing else store.create_workspace(workspace_name)["id"]
    else:
        workspace_id = store.create_workspace(name)["id"]
    minted = identity.mint_identity(name)
    svg = identity.favicon_svg(minted["emoji"], minted["color"])
    default_prompt = (
        f"You are {name}. Be useful, concise, and use workspace tools when files or commands help."
    )
    agent = store.create_agent(
        {
            "name": name,
            "emoji": minted["emoji"],
            "color": minted["color"],
            "tagline": minted["tagline"],
            "favicon_svg": svg,
            "system_prompt": default_prompt,
            "notes": "",
            "workspace_id": workspace_id,
        }
    )
    socketio.emit("agent", agent, to="board")
    return jsonify(agent), 201


@app.get("/api/agents/<agent_id>")
def api_get_agent(agent_id: str):
    agent = store.get_agent(agent_id)
    if not agent:
        return jsonify({"error": "Not found"}), 404
    files = sandbox.list_files(agent_id)
    messages = store.list_messages(agent_id)
    return jsonify({"agent": agent, "messages": messages, "files": files})


@app.patch("/api/agents/<agent_id>")
def api_patch_agent(agent_id: str):
    agent = store.get_agent(agent_id)
    if not agent:
        return jsonify({"error": "Not found"}), 404
    body = request.get_json(force=True, silent=True) or {}
    allowed = {k: body[k] for k in ("name", "system_prompt", "notes") if k in body}
    if "effort" in body:
        allowed["effort"] = store.clamp_effort(body.get("effort"))
    updated = store.update_agent(agent_id, allowed)
    socketio.emit("agent", updated, to=f"agent:{agent_id}")
    socketio.emit("agent", updated, to="board")
    return jsonify(updated)


def _broadcast_agent(agent: dict) -> None:
    socketio.emit("agent", agent, to=f"agent:{agent['id']}")
    socketio.emit("agent", agent, to="board")


@app.post("/api/agents/<agent_id>/move")
def api_move_agent(agent_id: str):
    agent = store.get_agent(agent_id)
    if not agent:
        return jsonify({"error": "Not found"}), 404
    body = request.get_json(force=True, silent=True) or {}
    workspace_id = (body.get("workspace_id") or "").strip()
    if not store.get_workspace(workspace_id):
        return jsonify({"error": "Folder not found"}), 400
    old_workspace = agent.get("workspace_id")
    updated = store.update_agent(agent_id, {"workspace_id": workspace_id})
    if old_workspace and old_workspace != workspace_id:
        with _presence_lock:
            sids = [sid for sid, entry in _presence.items() if entry.get("agent_id") == agent_id]
        for sid in sids:
            socketio.server.leave_room(sid, f"workspace:{old_workspace}", namespace="/")
            socketio.server.enter_room(sid, f"workspace:{workspace_id}", namespace="/")
    _broadcast_agent(updated)
    return jsonify(updated)


@app.post("/api/agents/<agent_id>/archive")
def api_archive_agent(agent_id: str):
    if not store.get_agent(agent_id):
        return jsonify({"error": "Not found"}), 404
    updated = store.update_agent(agent_id, {"archived": 1, "status": "idle"})
    _broadcast_agent(updated)
    return jsonify(updated)


@app.post("/api/agents/<agent_id>/restore")
def api_restore_agent(agent_id: str):
    if not store.get_agent(agent_id):
        return jsonify({"error": "Not found"}), 404
    updated = store.update_agent(agent_id, {"archived": 0})
    _broadcast_agent(updated)
    return jsonify(updated)


@app.delete("/api/agents/<agent_id>")
def api_delete_agent(agent_id: str):
    if not store.get_agent(agent_id):
        return jsonify({"error": "Not found"}), 404
    store.delete_agent(agent_id)
    socketio.emit("agent_deleted", {"id": agent_id}, to="board")
    socketio.emit("agent_deleted", {"id": agent_id}, to=f"agent:{agent_id}")
    return jsonify({"ok": True})


@app.get("/api/agents/<agent_id>/favicon.svg")
def api_favicon(agent_id: str):
    agent = store.get_agent(agent_id)
    if not agent:
        return jsonify({"error": "Not found"}), 404
    svg = agent.get("favicon_svg") or identity.favicon_svg(
        agent.get("emoji") or "◆", agent.get("color") or "#4C8DFF"
    )
    return app.response_class(svg, mimetype="image/svg+xml")


def _parse_when(value: str) -> datetime:
    text = (value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    when = datetime.fromisoformat(text)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc)


def _emit_schedules(agent_id: str) -> None:
    socketio.emit("schedules", store.list_schedules(agent_id), to=f"agent:{agent_id}")


@app.get("/api/agents/<agent_id>/schedules")
def api_list_schedules(agent_id: str):
    if not store.get_agent(agent_id):
        return jsonify({"error": "Not found"}), 404
    return jsonify(store.list_schedules(agent_id))


@app.post("/api/agents/<agent_id>/schedules")
def api_create_schedule(agent_id: str):
    agent = store.get_agent(agent_id)
    if not agent:
        return jsonify({"error": "Not found"}), 404
    if agent.get("archived"):
        return jsonify({"error": "This agent is archived."}), 400
    body = request.get_json(force=True, silent=True) or {}
    instruction = (body.get("instruction") or "").strip()
    if not instruction:
        return jsonify({"error": "Say what the agent should do."}), 400
    mode = body.get("mode")
    fields = {"instruction": instruction, "mode": mode}
    if mode == "once":
        try:
            when = _parse_when(body.get("run_at") or "")
        except ValueError:
            return jsonify({"error": "Pick a time."}), 400
        if when < datetime.now(timezone.utc) - timedelta(seconds=30):
            return jsonify({"error": "That time has already passed."}), 400
        stamp = when.isoformat()
        fields["run_at"] = stamp
        fields["next_run_at"] = stamp
    elif mode == "every":
        try:
            minutes = int(body.get("every_minutes"))
        except (TypeError, ValueError):
            return jsonify({"error": "Say how many minutes between runs."}), 400
        if minutes < 1 or minutes > 10080:
            return jsonify({"error": "Repeat between 1 minute and 7 days."}), 400
        fields["every_minutes"] = minutes
        fields["next_run_at"] = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()
    else:
        return jsonify({"error": "Choose once or every."}), 400
    created = store.create_schedule(agent_id, fields)
    _emit_schedules(agent_id)
    return jsonify(created), 201


@app.delete("/api/agents/<agent_id>/schedules/<schedule_id>")
def api_delete_schedule(agent_id: str, schedule_id: str):
    if not store.delete_schedule(agent_id, schedule_id):
        return jsonify({"error": "Not found"}), 404
    _emit_schedules(agent_id)
    return jsonify({"ok": True})


@app.post("/api/agents/<agent_id>/messages")
def api_post_message(agent_id: str):
    agent = store.get_agent(agent_id)
    if not agent:
        return jsonify({"error": "Not found"}), 404
    if agent.get("archived"):
        return jsonify({"error": "This agent is archived. Restore it to chat."}), 400
    status = ollama_status()
    if not status["reachable"]:
        return jsonify({"error": "Ollama is not connected"}), 400
    body = request.get_json(force=True, silent=True) or {}
    text = (body.get("content") or body.get("text") or "").strip()
    if not text:
        return jsonify({"error": "Message is empty"}), 400
    author = _clean_name(body.get("author") or body.get("from") or body.get("name"))
    mode = (body.get("mode") or "send").strip().lower()
    if mode not in {"send", "steer", "interrupt"}:
        mode = "send"
    thread = threading.Thread(
        target=run_turn,
        args=(socketio, agent_id, text, author, mode),
        daemon=True,
    )
    thread.start()
    return jsonify({"ok": True, "status": "running", "mode": mode}), 202


@app.post("/api/agents/<agent_id>/stop")
def api_stop_agent(agent_id: str):
    if not store.get_agent(agent_id):
        return jsonify({"error": "Not found"}), 404
    stop_turn(socketio, agent_id)
    return jsonify({"ok": True})


@app.get("/api/agents/<agent_id>/files")
def api_list_files(agent_id: str):
    if not store.get_agent(agent_id):
        return jsonify({"error": "Not found"}), 404
    return jsonify({"files": sandbox.list_files(agent_id)})


@app.post("/api/agents/<agent_id>/files")
def api_upload_files(agent_id: str):
    if not store.get_agent(agent_id):
        return jsonify({"error": "Not found"}), 404
    ensure_agent_dirs(agent_id)
    uploaded = request.files.getlist("files") or []
    if "file" in request.files:
        uploaded.append(request.files["file"])
    if not uploaded:
        return jsonify({"error": "No files"}), 400
    folder = request.form.get("folder") or ""
    saved = []
    for fh in uploaded:
        if not fh or not fh.filename:
            continue
        rel = _folder_path(folder, fh.filename)
        if not rel:
            continue
        dest = sandbox.jail(agent_id, rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        fh.save(dest)
        saved.append(rel)
    files = sandbox.list_files(agent_id)
    socketio.emit("files", {"files": files}, to=sandbox.files_room(agent_id))
    return jsonify({"saved": saved, "files": files}), 201


@app.get("/api/agents/<agent_id>/files/<path:relpath>")
def api_download_file(agent_id: str, relpath: str):
    if not store.get_agent(agent_id):
        return jsonify({"error": "Not found"}), 404
    try:
        path = sandbox.jail(agent_id, relpath)
    except sandbox.SandboxError:
        return jsonify({"error": "Invalid path"}), 400
    if not path.is_file():
        return jsonify({"error": "Not found"}), 404
    return send_file(path, as_attachment=True, download_name=path.name)


@app.delete("/api/agents/<agent_id>/files/<path:relpath>")
def api_delete_file(agent_id: str, relpath: str):
    if not store.get_agent(agent_id):
        return jsonify({"error": "Not found"}), 404
    try:
        sandbox.delete_file(agent_id, relpath)
    except sandbox.SandboxError as exc:
        return jsonify({"error": str(exc)}), 400
    files = sandbox.list_files(agent_id)
    socketio.emit("files", {"files": files}, to=sandbox.files_room(agent_id))
    return jsonify({"files": files})


@socketio.on("join")
def on_join(data):
    data = data or {}
    agent_id = data.get("id")
    workspace_id = data.get("workspace")
    name = _clean_name(data.get("name"))
    join_room("board")
    folder_id = workspace_id if workspace_id and store.get_workspace(workspace_id) else None
    if folder_id:
        join_room(f"workspace:{folder_id}")
    if agent_id:
        join_room(f"agent:{agent_id}")
        joined = store.get_agent(agent_id)
        if joined and joined.get("workspace_id"):
            folder_id = folder_id or joined["workspace_id"]
            join_room(f"workspace:{joined['workspace_id']}")
        with _presence_lock:
            _board_sids.discard(request.sid)
            _presence[request.sid] = {
                "name": name,
                "agent_id": agent_id,
                "workspace_id": folder_id,
            }
        _emit_presence(agent_id)
        _emit_workspace_presence(folder_id)
    else:
        with _presence_lock:
            _board_sids.add(request.sid)
            _presence[request.sid] = {
                "name": name,
                "agent_id": None,
                "workspace_id": folder_id,
            }
        _emit_board_presence()
        _emit_workspace_presence(folder_id)


@socketio.on("leave")
def on_leave(data):
    data = data or {}
    agent_id = data.get("id")
    if not agent_id:
        return
    leave_room(f"agent:{agent_id}")
    with _presence_lock:
        entry = _presence.get(request.sid)
        if entry and entry.get("agent_id") == agent_id:
            _presence.pop(request.sid, None)
    _emit_presence(agent_id)
    if entry and entry.get("workspace_id"):
        _emit_workspace_presence(entry["workspace_id"])


@socketio.on("disconnect")
def on_disconnect():
    with _presence_lock:
        entry = _presence.pop(request.sid, None)
        was_on_board = request.sid in _board_sids
        _board_sids.discard(request.sid)
    agent_id = entry.get("agent_id") if entry else None
    folder_id = entry.get("workspace_id") if entry else None
    if agent_id:
        _emit_presence(agent_id)
    if was_on_board:
        _emit_board_presence()
    _emit_workspace_presence(folder_id)


def _spa_index():
    index = WEB_DIST / "index.html"
    if index.exists():
        return send_from_directory(WEB_DIST, "index.html")
    return (
        jsonify(
            {
                "error": "Frontend not built. Run npm install && npm run build in web/, or use the Vite dev server.",
            }
        ),
        503,
    )


@app.get("/assets/<path:asset>")
def spa_assets(asset: str):
    assets = WEB_DIST / "assets"
    return send_from_directory(assets, asset)


@app.get("/control")
@app.get("/control/<path:rest>")
def control_bookmark_redirect(rest: str = ""):
    """Old Board bookmarks for Control → the Control site on its own port."""
    control_port = int(os.environ.get("CONTROL_PORT", "7411"))
    host = request.host.split(":")[0]
    target = f"{request.scheme}://{host}:{control_port}/{rest}".rstrip("/")
    if rest:
        target = f"{request.scheme}://{host}:{control_port}/{rest}"
    else:
        target = f"{request.scheme}://{host}:{control_port}/"
    if request.query_string:
        target = f"{target}?{request.query_string.decode()}"
    return Response(status=302, headers={"Location": target})


@app.get("/", defaults={"rest": ""})
@app.get("/<path:rest>")
def spa_catch_all(rest: str):
    if rest.startswith("api/"):
        return jsonify({"error": "Not found"}), 404
    candidate = WEB_DIST / rest
    if rest and candidate.is_file():
        return send_from_directory(WEB_DIST, rest)
    return _spa_index()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", str(DEFAULT_PORT)))
    if not _port_available(port):
        raise SystemExit(
            f"Port {port} is already in use. Stop the other process and try again."
        )
    # macOS can hang forever in socket.getfqdn → gethostbyaddr during bind.
    socket.getfqdn = lambda name="": "localhost"
    socketio.run(app, host="0.0.0.0", port=port, allow_unsafe_werkzeug=True)
