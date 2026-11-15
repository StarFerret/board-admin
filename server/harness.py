import json
import threading
import traceback

from . import db, mcp_builtin, mcp_runtime, ollama_client, sandbox, store, usage

EFFORT_DEFAULT = 12

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files in the agent workspace. Path is relative to /workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative directory, default ."}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a UTF-8 file from the workspace.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Write a UTF-8 file in the workspace (creates parent dirs). "
                "Put new deliverables under outputs/ so the operator can find them."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path. Prefer outputs/<name>.ext for new work.",
                    },
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a shell command in this folder's workspace directory.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mark_goal_done",
            "description": "Call only when the current goal is fully met. result is the final answer for the user.",
            "parameters": {
                "type": "object",
                "properties": {"result": {"type": "string"}},
                "required": ["result"],
            },
        },
    },
]

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()
_controls: dict[str, "TurnControl"] = {}
_controls_guard = threading.Lock()


class Stopped(Exception):
    """Raised from a stream callback when someone presses Stop."""


class TurnControl:
    def __init__(self) -> None:
        self.cancel = threading.Event()
        self.steers: list[str] = []
        self.lock = threading.Lock()

    def push_steer(self, text: str) -> None:
        cleaned = (text or "").strip()
        if not cleaned:
            return
        with self.lock:
            self.steers.append(cleaned)

    def drain_steers(self) -> list[str]:
        with self.lock:
            items = list(self.steers)
            self.steers.clear()
            return items


def _agent_lock(agent_id: str) -> threading.Lock:
    with _locks_guard:
        if agent_id not in _locks:
            _locks[agent_id] = threading.Lock()
        return _locks[agent_id]


def _turn_control(agent_id: str) -> TurnControl:
    with _controls_guard:
        control = _controls.get(agent_id)
        if not control:
            control = TurnControl()
            _controls[agent_id] = control
        return control


def _rules_blurb(agent: dict) -> str:
    workspace = store.get_workspace(agent.get("workspace_id"))
    rules = (workspace or {}).get("rules") or []
    if not rules:
        return ""
    blocks = []
    for rule in rules:
        body = (rule.get("body") or rule.get("preview") or "").strip()
        name = rule.get("name") or rule.get("path") or "rule"
        if not body:
            continue
        blocks.append(f"### {name}\n{body[:4000]}")
    if not blocks:
        return ""
    return (
        "Environment rules (always on). These live as files in rules/ on disk:\n\n"
        + "\n\n".join(blocks)
    )


def _skills_blurb(agent: dict) -> str:
    workspace = store.get_workspace(agent.get("workspace_id"))
    skills = [
        skill
        for skill in ((workspace or {}).get("skills") or [])
        if skill.get("enabled", True)
    ]
    if not skills:
        return ""
    lines = []
    for skill in skills:
        desc = skill.get("description") or "No description."
        lines.append(f"- {skill['name']} → read_file `{skill['path']}` — {desc}")
    return (
        "Available skills (folders under skills/ with SKILL.md). "
        "When one fits, read that file and follow it:\n"
        + "\n".join(lines)
    )


def _folder_tools(agent: dict) -> list[dict]:
    packs = []
    workspace_id = agent.get("workspace_id")
    mcp_tools: list[dict] = []
    if workspace_id:
        workspace = store.get_workspace(workspace_id)
        if workspace:
            packs = workspace.get("tools") or []
        try:
            mcp_tools = mcp_runtime.list_ollama_tools_for_workspace(workspace_id)
        except Exception:
            mcp_tools = []
    return TOOLS + mcp_builtin.tools_for(packs) + mcp_tools


def _tool_blurb(agent: dict) -> str:
    packs = []
    workspace_id = agent.get("workspace_id")
    workspace = store.get_workspace(workspace_id)
    if workspace:
        packs = workspace.get("tools") or []
    lines = mcp_builtin.blurbs_for(packs)
    if workspace_id:
        lines.extend(mcp_runtime.blurbs_for_workspace(workspace_id))
    if not lines:
        return "This folder has no extra tools. You only have the files in the workspace."
    return "Tools in this folder:\n" + "\n".join(lines)


def _file_index(agent_id: str) -> str:
    files = sandbox.list_files(agent_id, ".")
    if not files:
        return "(empty workspace)"
    lines = []
    for item in files[:200]:
        kind = item["type"]
        lines.append(f"{kind}\t{item['path']}\t{item['size']}")
    return "\n".join(lines)


def _system_message(agent: dict, goal: str, effort: int) -> str:
    name = agent["name"]
    notes = (agent.get("notes") or "").strip()
    custom = (agent.get("system_prompt") or "").strip()
    workspace = agent.get("workspace_name") or "this workspace"
    parts = [
        f"You are {name}, a named agent on a shared board.",
        f'You share the workspace "{workspace}" with the other agents in it. '
        "Any file you read or edit is the same file they see.",
        "You can list, read, and write files in this shared folder.",
        "run_command runs shell commands in that same folder.",
        "Never claim you can access paths outside /workspace.",
        "Outputs folder: save every deliverable you create under outputs/ "
        "(reports, drafts, code, exports, summaries, screenshots of work — anything the operator "
        "should find later). Prefer outputs/<clear-name>.ext. Do not scatter finished work at the "
        "workspace root. Editing an existing file the operator pointed at is fine; new artifacts go "
        "in outputs/. Mention the outputs/ path when you finish.",
        "Rules live as files in rules/. Skills live as skills/<name>/SKILL.md. "
        "Operators add those on disk themselves — do not invent rule/skill files unless asked.",
        _tool_blurb(agent),
        "Thinking is on. Reason in that channel, then act.",
        f"You have {effort} tries. Each reply and each tool call uses one. "
        "Keep using tools until the goal is met. "
        "Call mark_goal_done only when the goal is fully done. "
        "A checker sends you back if you stop early. "
        "If the operator sends a steer, treat it as a mid-run correction for the current goal.",
        f"Current goal:\n{goal}",
        f"Workspace file index:\n{_file_index(agent['id'])}",
    ]
    rules = _rules_blurb(agent)
    if rules:
        parts.append(rules)
    skills = _skills_blurb(agent)
    if skills:
        parts.append(skills)
    if custom:
        parts.append("Operator system prompt:\n" + custom)
    if notes:
        parts.append("Pinned notes:\n" + notes)
    return "\n\n".join(parts)


def _dispatch_tool(agent_id: str, name: str, args: dict, allowed: set[str]) -> str:
    try:
        if name == "mark_goal_done":
            return json.dumps({"ok": True, "result": args.get("result") or ""})
        if name not in allowed:
            return json.dumps({"error": "That tool is not in this folder."})
        if mcp_builtin.handles(name):
            return mcp_builtin.call_tool(agent_id, name, args)
        if mcp_runtime.handles(name):
            return mcp_runtime.call_tool(name, args)
        if name == "list_files":
            return sandbox.tool_list_files(agent_id, args.get("path") or ".")
        if name == "read_file":
            return sandbox.tool_read_file(agent_id, args.get("path") or "")
        if name == "write_file":
            return sandbox.tool_write_file(
                agent_id, args.get("path") or "", args.get("content") or ""
            )
        if name == "run_command":
            return sandbox.tool_run_command(agent_id, args.get("command") or "")
        return json.dumps({"error": f"unknown tool {name}"})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def _tool_call_id(call: dict, index: int) -> str:
    return call.get("id") or f"call_{index}"


def _tool_name(call: dict) -> str:
    if "function" in call:
        return call["function"].get("name") or ""
    return call.get("name") or ""


def _tool_args(call: dict) -> dict:
    raw = {}
    if "function" in call:
        raw = call["function"].get("arguments") or {}
    else:
        raw = call.get("arguments") or {}
    if isinstance(raw, str):
        try:
            return json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return {"_raw": raw}
    return raw or {}


def _emit_goal(socketio, room: str, goal: str, step: int, status: str, effort: int) -> None:
    socketio.emit(
        "goal",
        {"goal": goal, "step": step, "max": effort, "status": status},
        to=room,
    )


def _active_model(preferred: str) -> str:
    return db.get_setting("ollama_model") or preferred


def _notify_model_failover(socketio, room: str, before: str, after: str) -> str:
    after = _active_model(after)
    if before == after:
        return after
    payload = {"from": before, "to": after}
    socketio.emit("ollama_model", payload, to=room)
    socketio.emit("ollama_model", payload, to="board")
    agent_id = room.split(":", 1)[1] if room.startswith("agent:") else ""
    if agent_id:
        # Say it in the chat, so nobody wonders why the work got slower or worse.
        note = store.add_message(
            agent_id,
            "assistant",
            f"Switched to {after}, because {before} could not run on this Mac just now. "
            "Answers may be weaker. Manage this Mac to change the model.",
            {"notice": True, "model_from": before, "model_to": after},
        )
        socketio.emit("message", note, to=room)
    return after


def _parse_json(raw: str) -> dict:
    """JSON from a reply that may wrap it in prose or a code fence (models without JSON mode)."""
    text = (raw or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in reply")
    return json.loads(text[start : end + 1])


def _extract_goal(base_url: str, model: str, request_text: str) -> str:
    try:
        result = ollama_client.chat(
            base_url,
            [
                {
                    "role": "system",
                    "content": (
                        "Extract the single goal from the request. "
                        'Return only JSON {"goal": "a specific outcome that can be checked"}. '
                        "Do not do the task."
                    ),
                },
                {"role": "user", "content": request_text},
            ],
            model=model,
            think=True,
            response_format="json",
            timeout=90,
        )
        raw = (result.get("message") or {}).get("content") or ""
        goal = str(_parse_json(raw).get("goal") or "").strip()
        return goal[:500] or request_text
    except Exception:
        return request_text


def _goal_met(base_url: str, model: str, goal: str, latest: str, agent_id: str) -> dict:
    try:
        result = ollama_client.chat(
            base_url,
            [
                {
                    "role": "system",
                    "content": (
                        "You decide if a goal is fully met. "
                        'Return only JSON {"done": true or false, "missing": "what is still unfinished"}.'
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Goal:\n{goal}\n\nLatest work:\n{latest or '(no answer yet)'}\n\n"
                        f"Files:\n{_file_index(agent_id)}"
                    ),
                },
            ],
            model=model,
            think=True,
            response_format="json",
            timeout=120,
        )
        raw = (result.get("message") or {}).get("content") or ""
        data = _parse_json(raw)
        return {"done": data.get("done") in (True, "true", "True", "yes"), "missing": str(data.get("missing") or "").strip()}
    except Exception:
        return {"done": False, "missing": "The goal still needs a check. Continue the work."}


def _inject_steers(socketio, room, agent_id, control: TurnControl, ollama_messages: list) -> None:
    steers = control.drain_steers()
    for text in steers:
        ollama_messages.append(
            {
                "role": "user",
                "content": (
                    "Operator steer — adjust the current goal with this guidance, "
                    f"then keep working:\n{text}"
                ),
            }
        )
        socketio.emit("goal", {"status": "steered", "steer": text}, to=room)


def _pursue_goal(
    socketio, room, agent_id, base_url, model, goal, effort, ollama_messages, tools, control: TurnControl
) -> tuple[str, str]:
    allowed = {tool["function"]["name"] for tool in tools}
    spent = 0
    last_thinking = ""
    while spent < effort:
        if control.cancel.is_set():
            return "Interrupted by operator.", last_thinking
        _inject_steers(socketio, room, agent_id, control, ollama_messages)
        model = _active_model(model)
        spent += 1
        step = spent
        _emit_goal(socketio, room, goal, step, "working", effort)
        socketio.emit("thinking", {"reset": True, "text": ""}, to=room)
        acc = {"text": "", "thinking": ""}

        def on_token(piece: str, acc=acc):
            if control.cancel.is_set():
                raise Stopped()
            acc["text"] += piece
            socketio.emit("token", {"text": piece}, to=room)

        def on_thinking(piece: str, acc=acc):
            if control.cancel.is_set():
                raise Stopped()
            acc["thinking"] += piece
            socketio.emit("thinking", {"text": piece}, to=room)

        def on_retry(fallback: str, before=model):
            _notify_model_failover(socketio, room, before, fallback)

        try:
            result = ollama_client.chat_stream(
                base_url,
                ollama_messages,
                model=model,
                tools=tools,
                think=True,
                on_token=on_token,
                on_thinking=on_thinking,
                on_retry=on_retry,
            )
        except Stopped:
            return "Interrupted by operator.", last_thinking
        if control.cancel.is_set():
            return "Interrupted by operator.", last_thinking
        model = _notify_model_failover(socketio, room, model, _active_model(model))
        message = result.get("message") or {}
        content = message.get("content") or acc["text"] or ""
        thinking = message.get("thinking") or acc["thinking"] or ""
        last_thinking = thinking
        tool_calls = message.get("tool_calls") or []
        saved_thinking = False
        claimed = ""
        if tool_calls:
            ollama_messages.append(
                {"role": "assistant", "content": content, "tool_calls": tool_calls}
            )
            if content.strip():
                stored = store.add_message(
                    agent_id,
                    "assistant",
                    content,
                    {"tool_calls": tool_calls, "thinking": thinking, "step": step},
                )
                socketio.emit("message", stored, to=room)
                socketio.emit("thinking", {"reset": True, "text": ""}, to=room)
                saved_thinking = True
            for call in tool_calls:
                if control.cancel.is_set():
                    return "Interrupted by operator.", last_thinking
                if spent >= effort:
                    break
                spent += 1
                step = spent
                _emit_goal(socketio, room, goal, step, "working", effort)
                name = _tool_name(call)
                args = _tool_args(call)
                if name == "mark_goal_done":
                    claimed = str(args.get("result") or content or "").strip()
                socketio.emit("tool", {"name": name, "args": args, "status": "running"}, to=room)
                output = _dispatch_tool(agent_id, name, args, allowed)
                tool_msg = store.add_message(agent_id, "tool", output, {"name": name, "args": args})
                socketio.emit("message", tool_msg, to=room)
                socketio.emit(
                    "tool",
                    {"name": name, "args": args, "status": "done", "output": output[:4000]},
                    to=room,
                )
                ollama_messages.append({"role": "tool", "tool_name": name, "content": output})
            socketio.emit(
                "files",
                {"files": sandbox.list_files(agent_id)},
                to=sandbox.files_room(agent_id),
            )
            if not claimed:
                if spent >= effort:
                    break
                continue
            latest = claimed
        else:
            latest = content

        if control.cancel.is_set():
            return "Interrupted by operator.", last_thinking
        _inject_steers(socketio, room, agent_id, control, ollama_messages)
        _emit_goal(socketio, room, goal, step, "checking", effort)
        verdict = _goal_met(base_url, model, goal, latest, agent_id)
        model = _notify_model_failover(socketio, room, model, _active_model(model))
        if verdict["done"]:
            return latest or "Done.", "" if saved_thinking else last_thinking
        missing = verdict["missing"] or "The goal is not finished."
        if not tool_calls:
            ollama_messages.append({"role": "assistant", "content": latest})
        ollama_messages.append(
            {
                "role": "user",
                "content": (
                    f"The goal is not met yet. Still missing: {missing}\n"
                    f"Tries left: {effort - spent}. "
                    "Keep working. Call mark_goal_done only when it is actually done."
                ),
            }
        )
        note = store.add_message(
            agent_id,
            "assistant",
            f"Still working. {missing}",
            {"thinking": thinking, "step": step, "continue": True},
        )
        socketio.emit("message", note, to=room)
        if spent >= effort:
            break
        socketio.emit("token", {"reset": True}, to=room)
    return f"Stopped before the goal was met. The work limit is {effort} tries.", last_thinking


def stop_turn(socketio, agent_id: str) -> None:
    """Stop the running turn without starting a new one. Safe to call when idle."""
    room = f"agent:{agent_id}"
    control = _turn_control(agent_id)
    if _agent_lock(agent_id).locked():
        control.cancel.set()
        socketio.emit("goal", {"status": "stopping"}, to=room)
        return
    # Nothing is running here. Clear a status left over from a crash or restart.
    agent = store.get_agent(agent_id)
    if agent and agent.get("status") == "running":
        store.update_agent(agent_id, {"status": "idle"})
        socketio.emit("status", {"id": agent_id, "status": "idle"}, to=room)
        socketio.emit("status", {"id": agent_id, "status": "idle"}, to="board")


def run_turn(
    socketio, agent_id: str, user_text: str, author: str = "Guest", mode: str = "send"
) -> None:
    mode = (mode or "send").strip().lower()
    if mode not in {"send", "steer", "interrupt"}:
        mode = "send"
    room = f"agent:{agent_id}"
    control = _turn_control(agent_id)
    lock = _agent_lock(agent_id)

    if mode == "steer":
        if lock.locked():
            user_msg = store.add_message(
                agent_id, "user", user_text, {"author": author, "steer": True}
            )
            socketio.emit("message", user_msg, to=room)
            control.push_steer(user_text)
            return
        mode = "send"

    if mode in {"send", "interrupt"}:
        control.cancel.set()
        acquired = lock.acquire(timeout=45)
        if not acquired:
            socketio.emit(
                "error",
                {"message": "Could not interrupt the current turn. Try again."},
                to=room,
            )
            return
        control.cancel.clear()
        control.drain_steers()
        try:
            _run_turn(socketio, agent_id, user_text, author, control)
        finally:
            lock.release()


def _finish_stopped(socketio, agent_id: str, goal: str) -> None:
    room = f"agent:{agent_id}"
    note = store.add_message(agent_id, "assistant", "Stopped.", {"notice": True, "goal": goal})
    socketio.emit("message", note, to=room)
    store.update_agent(agent_id, {"status": "idle"})
    socketio.emit("status", {"id": agent_id, "status": "idle"}, to=room)
    socketio.emit("status", {"id": agent_id, "status": "idle"}, to="board")
    socketio.emit("goal", {"goal": goal, "status": "interrupted"}, to=room)


def _run_turn(
    socketio, agent_id: str, user_text: str, author: str, control: TurnControl
) -> None:
    room = f"agent:{agent_id}"
    agent = store.get_agent(agent_id)
    if not agent:
        socketio.emit("error", {"message": "Agent not found"}, to=room)
        return
    base_url = db.get_setting("ollama_base_url")
    if not base_url:
        socketio.emit("error", {"message": "Ollama is not configured"}, to=room)
        return

    user_msg = store.add_message(agent_id, "user", user_text, {"author": author})
    socketio.emit("message", user_msg, to=room)
    usage.begin()
    outcome = "done"
    store.update_agent(agent_id, {"status": "running"})
    socketio.emit("status", {"id": agent_id, "status": "running"}, to=room)
    socketio.emit("status", {"id": agent_id, "status": "running"}, to="board")

    model = db.get_setting("ollama_model") or ollama_client.DEFAULT_MODEL
    effort = store.clamp_effort(agent.get("effort"))
    _emit_goal(socketio, room, "Reading the request…", 0, "extracting", effort)
    goal = _extract_goal(base_url, model, user_text)
    model = _notify_model_failover(socketio, room, model, _active_model(model))
    if control.cancel.is_set():
        _finish_stopped(socketio, agent_id, goal)
        usage.finish(author, agent, "interrupted")
        return
    _emit_goal(socketio, room, goal, 0, "working", effort)

    history = store.list_messages(agent_id)
    ollama_messages = [{"role": "system", "content": _system_message(agent, goal, effort)}]
    for msg in history:
        role = msg["role"]
        meta = msg.get("meta") or {}
        if meta.get("notice") or meta.get("continue"):
            # "Stopped.", "Switched to…", and checker progress notes are for people, not the model.
            continue
        if role == "tool":
            ollama_messages.append(
                {
                    "role": "tool",
                    "content": msg["content"],
                    "tool_name": meta.get("name") or "tool",
                }
            )
        elif role in {"user", "assistant", "system"}:
            content = msg["content"]
            if role == "user" and meta.get("steer"):
                content = f"[Steer] {content}"
            ollama_messages.append({"role": role, "content": content})

    try:
        assistant_text, thinking = _pursue_goal(
            socketio,
            room,
            agent_id,
            base_url,
            model,
            goal,
            effort,
            ollama_messages,
            _folder_tools(agent),
            control,
        )
        if control.cancel.is_set():
            outcome = "interrupted"
            _finish_stopped(socketio, agent_id, goal)
            return
        meta = {"goal": goal, "effort": effort}
        if thinking:
            meta["thinking"] = thinking
        final = store.add_message(agent_id, "assistant", assistant_text, meta)
        socketio.emit("message", final, to=room)
        socketio.emit("goal", {"goal": goal, "step": effort, "max": effort, "status": "done"}, to=room)
        store.update_agent(agent_id, {"status": "idle"})
        socketio.emit("status", {"id": agent_id, "status": "idle"}, to=room)
        socketio.emit("status", {"id": agent_id, "status": "idle"}, to="board")
    except Exception as exc:
        outcome = "error"
        traceback.print_exc()
        # A missing model is a normal state right after install, not a crash: say it plainly.
        text = str(exc) if isinstance(exc, ollama_client.ModelNotReady) else f"Harness error: {exc}"
        err = store.add_message(agent_id, "assistant", text, {"error": True})
        socketio.emit("message", err, to=room)
        store.update_agent(agent_id, {"status": "error"})
        socketio.emit("status", {"id": agent_id, "status": "error"}, to=room)
        socketio.emit("status", {"id": agent_id, "status": "error"}, to="board")
        socketio.emit("error", {"message": str(exc)}, to=room)
    finally:
        usage.finish(author, agent, outcome)
