"""Control API — runs as a sibling process to the Board (default port 7411)."""

from __future__ import annotations

import hmac
import os
import secrets
import threading
from functools import wraps

from flask import Flask, jsonify, request, send_from_directory

from . import apps, capacity, health, metrics, models, people, process_board, store, updater, usage
from .paths import CONTROL_WEB_DIST, DEFAULT_BOARD_PORT, DEFAULT_CONTROL_PORT, LOCAL_KEY_PATH, SETUP_TOKEN_PATH, ensure_dirs

# Control SPA is same-origin with this API; nothing in the browser calls 7411 from elsewhere.
app = Flask(__name__, static_folder=None)

COOKIE = "starferret_control"
ensure_dirs()
store.init_db()
_bootstrap_lock = threading.Lock()


def _secret_file(path) -> str:
    """Read a secret kept on disk, or make one (mode 600) the first time."""
    try:
        token = path.read_text(encoding="utf-8").strip()
        if token:
            return token
    except OSError:
        pass
    token = secrets.token_urlsafe(24)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(token + "\n")
    return token


def _setup_token() -> str:
    """The one time secret for creating the first admin from another machine.

    Kept on disk so the installer can read it and a restart does not change the
    link. Gone once an admin exists.
    """
    return _secret_file(SETUP_TOKEN_PATH)


def _drop_setup_token() -> None:
    try:
        SETUP_TOKEN_PATH.unlink()
    except OSError:
        pass


if store.bootstrap_needed():
    _setup_token()
else:
    _drop_setup_token()
# Anyone who can read this file is already this Mac's user, so it grants no new power.
# It lets the installer start and watch the first model download without an admin password.
_LOCAL_KEY = _secret_file(LOCAL_KEY_PATH)
LOCAL_KEY_HEADER = "X-StarFerret-Local-Key"


def _token_from_request() -> str:
    header = request.headers.get("Authorization") or ""
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.cookies.get(COOKIE) or ""


def _current_user():
    user = store.session_user(_token_from_request())
    if user:
        return user
    given = request.headers.get(LOCAL_KEY_HEADER) or ""
    if given and _request_is_local() and hmac.compare_digest(given, _LOCAL_KEY):
        return {"id": "local", "username": "installer", "role": "admin", "display_name": "Installer on this Mac"}
    return None


def require_auth(*roles: str):
    def decorator(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            user = _current_user()
            if not user:
                return jsonify({"error": "Sign in required", "auth_required": True}), 401
            if roles and user["role"] not in roles:
                return jsonify({"error": "Insufficient role", "role": user["role"]}), 403
            request.control_user = user  # type: ignore[attr-defined]
            return fn(*args, **kwargs)

        return wrapped

    return decorator


@app.get("/api/control/health")
def control_health():
    return jsonify({"ok": True, "service": "starferret-control", "bootstrap_needed": store.bootstrap_needed()})


@app.get("/api/control/meta")
def control_meta():
    user = _current_user()
    board_port = int(os.environ.get("PORT") or os.environ.get("BOARD_PORT") or DEFAULT_BOARD_PORT)
    return jsonify(
        {
            **store.export_meta(),
            "user": user,
            "signed_in": bool(user),
            "board_port": board_port,
            # True when the first admin can be made from this browser without the setup link.
            "setup_local": _request_is_local(),
        }
    )


def _auth_response(user: dict, session: dict):
    resp = jsonify(
        {
            "user": user,
            "token": session["token"],
            "expires_at": session["expires_at"],
        }
    )
    resp.set_cookie(
        COOKIE,
        session["token"],
        httponly=True,
        samesite="Lax",
        max_age=14 * 24 * 3600,
    )
    return resp


_LOCAL_NAMES = {"127.0.0.1", "::1", "::ffff:127.0.0.1", "localhost"}


def _request_is_local() -> bool:
    """True only for a request made on this Mac, to this Mac, not on behalf of another site.

    The address alone is not enough: a web page open in this Mac's browser also
    connects from 127.0.0.1. So the Host must be a local name (stops DNS rebinding),
    and a browser's Origin, when sent, must be Control itself (stops other sites).
    """
    if (request.remote_addr or "").strip() not in _LOCAL_NAMES:
        return False
    host = (request.host or "").strip().lower()
    host = host[1:].split("]")[0] if host.startswith("[") else host.rsplit(":", 1)[0]
    if host not in _LOCAL_NAMES:
        return False
    origin = (request.headers.get("Origin") or "").strip().lower()
    if origin and origin != f"{request.scheme}://{request.host}".lower():
        return False
    return True


@app.post("/api/control/bootstrap")
def bootstrap():
    """Create the first admin. Only from this Mac, or with the installer's setup link.

    Control listens on the office network, so without this check whoever opened
    port 7411 first would become the admin.
    """
    body = request.get_json(force=True, silent=True) or {}
    with _bootstrap_lock:
        if not store.bootstrap_needed():
            return jsonify({"error": "Admin already exists"}), 400
        given = str(body.get("token") or "")
        if not _request_is_local() and not (given and hmac.compare_digest(given, _setup_token())):
            return jsonify(
                {
                    "error": "Create the first admin on the Mac itself, or open the setup link the installer printed.",
                    "setup_link_required": True,
                }
            ), 403
        try:
            user = store.create_user(
                username=body.get("username") or "admin",
                password=body.get("password") or "",
                role="admin",
                display_name=body.get("display_name") or "Admin",
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        _drop_setup_token()
    session = store.create_session(user["id"])
    return _auth_response(user, session)


@app.post("/api/control/login")
def login():
    body = request.get_json(force=True, silent=True) or {}
    user = store.authenticate(body.get("username") or "", body.get("password") or "")
    if not user:
        return jsonify({"error": "Invalid username or password"}), 401
    session = store.create_session(user["id"])
    return _auth_response(user, session)


@app.post("/api/control/reset-admin")
def reset_admin():
    """Localhost-only escape hatch when the only admin password is unknown."""
    if not _request_is_local():
        return jsonify({"error": "Admin reset is only allowed from this machine (localhost)."}), 403
    body = request.get_json(force=True, silent=True) or {}
    password = body.get("password") or ""
    username = (body.get("username") or "admin").strip() or "admin"
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    store.reset_all_users()
    try:
        user = store.create_user(
            username=username,
            password=password,
            role="admin",
            display_name=body.get("display_name") or "Admin",
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    session = store.create_session(user["id"])
    return _auth_response(user, session)


@app.post("/api/control/logout")
def logout():
    store.revoke_session(_token_from_request())
    resp = jsonify({"ok": True})
    resp.delete_cookie(COOKIE)
    return resp


@app.get("/api/control/me")
@require_auth()
def me():
    return jsonify({"user": request.control_user})  # type: ignore[attr-defined]


@app.get("/api/control/users")
@require_auth("admin")
def list_users():
    return jsonify({"users": store.list_users()})


@app.post("/api/control/users")
@require_auth("admin")
def create_user():
    body = request.get_json(force=True, silent=True) or {}
    try:
        user = store.create_user(
            username=body.get("username") or "",
            password=body.get("password") or "",
            role=body.get("role") or "operator",
            display_name=body.get("display_name") or "",
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"user": user})


@app.patch("/api/control/users/<user_id>")
@require_auth("admin")
def patch_user(user_id: str):
    body = request.get_json(force=True, silent=True) or {}
    try:
        user = None
        if "role" in body:
            user = store.set_user_role(user_id, body.get("role") or "")
        if "disabled" in body:
            user = store.set_user_disabled(user_id, bool(body.get("disabled")))
        if user is None:
            user = store.get_user(user_id)
            if not user:
                return jsonify({"error": "User not found"}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"user": user})


@app.delete("/api/control/users/<user_id>")
@require_auth("admin")
def delete_user(user_id: str):
    me_user = request.control_user  # type: ignore[attr-defined]
    if me_user["id"] == user_id:
        return jsonify({"error": "Cannot delete your own account"}), 400
    if not store.get_user(user_id):
        return jsonify({"error": "User not found"}), 404
    store.delete_user(user_id)
    return jsonify({"ok": True})


@app.get("/api/control/apps")
@require_auth("admin", "operator", "viewer")
def list_apps():
    state = apps.docker_state()
    return jsonify(
        {
            "apps": apps.list_manifests(),
            "docker": state["running"],
            "docker_state": state,
            "categories": apps.CATEGORIES,
        }
    )


@app.get("/api/control/usage")
@require_auth("admin", "operator", "viewer")
def usage_summary():
    try:
        days = int(request.args.get("days") or 30)
    except ValueError:
        days = 30
    return jsonify(usage.summary(days))


@app.post("/api/control/apps/<app_id>/start")
@require_auth("admin", "operator")
def start_app(app_id: str):
    try:
        result = apps.start_app(app_id)
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(result)


@app.post("/api/control/apps/<app_id>/stop")
@require_auth("admin", "operator")
def stop_app(app_id: str):
    try:
        result = apps.stop_app(app_id)
    except (ValueError, RuntimeError) as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(result)


@app.post("/api/control/apps/<app_id>/update")
@require_auth("admin")
def update_app(app_id: str):
    try:
        result = apps.update_app(app_id)
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(result)


@app.get("/api/control/models")
@require_auth("admin", "operator", "viewer")
def list_models():
    base = request.args.get("base_url")
    return jsonify(models.list_models(base))


@app.post("/api/control/models/pull")
@require_auth("admin", "operator")
def pull_model():
    body = request.get_json(force=True, silent=True) or {}
    try:
        result = models.pull_model(body.get("name") or "", body.get("base_url"))
    except (ValueError, RuntimeError) as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(result), 202


@app.get("/api/control/models/pulls")
@require_auth()
def model_pulls():
    return jsonify({"pulls": models.list_pulls()})


@app.post("/api/control/models/delete")
@require_auth("admin")
def delete_model():
    body = request.get_json(force=True, silent=True) or {}
    try:
        result = models.delete_model(body.get("name") or "", body.get("base_url"))
    except (ValueError, RuntimeError) as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(result)


@app.post("/api/control/models/default")
@require_auth("admin", "operator")
def set_default_model():
    body = request.get_json(force=True, silent=True) or {}
    name = (body.get("name") or body.get("model") or "").strip()
    if not name:
        return jsonify({"error": "Model name is required"}), 400
    result = models.set_board_default_model(name, body.get("board_origin"))
    if not result.get("ok"):
        return jsonify({"error": result.get("error") or "Could not update Board default"}), 400
    return jsonify(result)


@app.get("/api/control/board/ollama")
@require_auth("admin", "operator", "viewer")
def board_ollama_get():
    result = models.board_ollama_status(request.args.get("board_origin"))
    if not result.get("ok"):
        return jsonify({"error": result.get("error") or "Board is not answering."}), 503
    return jsonify(result)


@app.post("/api/control/board/ollama")
@require_auth("admin", "operator")
def board_ollama_set():
    body = request.get_json(force=True, silent=True) or {}
    try:
        return jsonify(models.set_board_ollama(body, body.get("board_origin")))
    except (ValueError, RuntimeError) as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/control/machine")
@require_auth("admin", "operator", "viewer")
def machine():
    return jsonify(health.snapshot())


@app.get("/api/control/metrics")
@require_auth("admin", "operator", "viewer")
def utilization():
    return jsonify(metrics.snapshot())


@app.get("/api/control/capacity")
@require_auth("admin", "operator", "viewer")
def capacity_summary():
    return jsonify(capacity.summary())


@app.post("/api/control/capacity/measure")
@require_auth("admin", "operator")
def capacity_measure():
    body = request.get_json(force=True, silent=True) or {}
    capacity.start_test("all" if body.get("models") == "all" else "default")
    return jsonify(capacity.summary())


@app.get("/api/control/people")
@require_auth("admin")
def people_summary():
    return jsonify({**people.summary(), "admins": store.list_users()})


@app.get("/api/control/board")
@require_auth("admin", "operator", "viewer")
def board_status():
    return jsonify(process_board.status())


@app.post("/api/control/board/start")
@require_auth("admin")
def board_start():
    return jsonify(process_board.start())


@app.post("/api/control/board/stop")
@require_auth("admin")
def board_stop():
    return jsonify(process_board.stop())


@app.get("/api/control/board/logs")
@require_auth("admin")
def board_logs():
    lines = int(request.args.get("lines") or 80)
    return jsonify({"log": process_board.tail_log(lines)})


@app.get("/api/control/updates")
@require_auth("admin", "operator", "viewer")
def updates():
    return jsonify(updater.info())


def _update_action(action):
    try:
        action()
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(updater.info())


@app.post("/api/control/updates/check")
@require_auth("admin", "operator")
def updates_check():
    return _update_action(updater.check)


@app.post("/api/control/updates/apply")
@require_auth("admin")
def updates_apply():
    return _update_action(updater.start_update)


@app.post("/api/control/updates/back")
@require_auth("admin")
def updates_back():
    return _update_action(updater.go_back)


def _spa_index():
    index = CONTROL_WEB_DIST / "index.html"
    if index.exists():
        return send_from_directory(CONTROL_WEB_DIST, "index.html")
    return (
        jsonify(
            {
                "error": "Control frontend not built. Run npm install && npm run build in control-web/.",
            }
        ),
        503,
    )


@app.get("/assets/<path:asset>")
def spa_assets(asset: str):
    assets = CONTROL_WEB_DIST / "assets"
    return send_from_directory(assets, asset)


@app.get("/", defaults={"rest": ""})
@app.get("/<path:rest>")
def spa_catch_all(rest: str):
    if rest.startswith("api/"):
        return jsonify({"error": "Not found"}), 404
    candidate = CONTROL_WEB_DIST / rest
    if rest and candidate.is_file():
        return send_from_directory(CONTROL_WEB_DIST, rest)
    return _spa_index()


def create_app() -> Flask:
    return app


def main() -> None:
    metrics.ensure_sampler()
    port = int(os.environ.get("CONTROL_PORT", str(DEFAULT_CONTROL_PORT)))
    app.run(host="0.0.0.0", port=port, threaded=True)


if __name__ == "__main__":
    main()
