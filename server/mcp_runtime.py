"""Talk to MCP servers (stdio or URL) and expose Ollama-shaped tools."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from typing import Any
from urllib.parse import urlparse

import requests

from . import mcp_registry

_lock = threading.Lock()
_tool_cache: dict[str, tuple[float, list[dict]]] = {}
_CACHE_TTL = 60.0


class McpError(Exception):
    pass


def _tool_name(server_id: str, tool: str) -> str:
    safe_server = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in server_id)
    safe_tool = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in tool)
    return f"mcp__{safe_server}__{safe_tool}"


def parse_mcp_tool_name(name: str) -> tuple[str, str] | None:
    if not name.startswith("mcp__"):
        return None
    rest = name[len("mcp__") :]
    if "__" not in rest:
        return None
    server_id, tool = rest.split("__", 1)
    if not server_id or not tool:
        return None
    return server_id, tool


def handles(name: str) -> bool:
    return parse_mcp_tool_name(name) is not None


def _schema_to_ollama(server_id: str, tool: dict) -> dict:
    name = tool.get("name") or "tool"
    description = tool.get("description") or f"MCP tool {name} from {server_id}"
    params = tool.get("inputSchema") or tool.get("parameters") or {
        "type": "object",
        "properties": {},
    }
    return {
        "type": "function",
        "function": {
            "name": _tool_name(server_id, name),
            "description": f"[{server_id}] {description}",
            "parameters": params,
        },
    }


class _StdioSession:
    def __init__(self, server: dict):
        env = os.environ.copy()
        for key, value in (server.get("env") or {}).items():
            env[str(key)] = str(value)
        command = server.get("command") or ""
        args = list(server.get("args") or [])
        self.proc = subprocess.Popen(
            [command, *args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            bufsize=1,
        )
        self._id = 0
        self._initialize()

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _write(self, message: dict) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()

    def _read(self, timeout: float = 20.0) -> dict:
        assert self.proc.stdout is not None
        deadline = time.time() + timeout
        while time.time() < deadline:
            line = self.proc.stdout.readline()
            if not line:
                err = ""
                if self.proc.stderr:
                    err = self.proc.stderr.read() or ""
                raise McpError(f"MCP stdio closed early: {err[:400]}")
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "id" in msg or msg.get("method"):
                return msg
        raise McpError("MCP stdio timed out waiting for a response")

    def _initialize(self) -> None:
        req_id = self._next_id()
        self._write(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "starferret", "version": "0.1.0"},
                },
            }
        )
        while True:
            msg = self._read()
            if msg.get("id") == req_id:
                if msg.get("error"):
                    raise McpError(str(msg["error"]))
                break
        self._write({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def request(self, method: str, params: dict | None = None) -> Any:
        req_id = self._next_id()
        payload = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            payload["params"] = params
        self._write(payload)
        while True:
            msg = self._read()
            if msg.get("id") != req_id:
                continue
            if msg.get("error"):
                raise McpError(str(msg["error"]))
            return msg.get("result")

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.terminate()
            self.proc.wait(timeout=2)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass


def _http_jsonrpc(server: dict, method: str, params: dict | None = None) -> Any:
    url = (server.get("url") or "").strip()
    if not url:
        raise McpError("MCP url is empty")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise McpError("MCP url must be http or https")

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    for key, value in (server.get("headers") or {}).items():
        headers[str(key)] = str(value)

    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params or {},
    }
    # initialize first when listing/calling
    if method != "initialize":
        init = {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "starferret", "version": "0.1.0"},
            },
        }
        init_resp = requests.post(url, headers=headers, json=init, timeout=30)
        if init_resp.status_code >= 400:
            raise McpError(f"MCP initialize HTTP {init_resp.status_code}: {init_resp.text[:300]}")
        # Some servers want the initialized notification
        try:
            requests.post(
                url,
                headers=headers,
                json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                timeout=10,
            )
        except Exception:
            pass

    resp = requests.post(url, headers=headers, json=body, timeout=60)
    if resp.status_code >= 400:
        raise McpError(f"MCP HTTP {resp.status_code}: {resp.text[:400]}")

    text = resp.text.strip()
    # SSE-ish: data: {...}
    if "data:" in text and text.lstrip().startswith("event:") or "\ndata:" in text:
        for line in text.splitlines():
            if line.startswith("data:"):
                payload = line[5:].strip()
                if not payload or payload == "[DONE]":
                    continue
                try:
                    msg = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if msg.get("id") == 1 or (msg.get("result") is not None and "error" not in msg):
                    if msg.get("error"):
                        raise McpError(str(msg["error"]))
                    return msg.get("result")
        raise McpError("MCP SSE response had no usable result")

    try:
        msg = resp.json()
    except Exception as exc:
        raise McpError(f"MCP response was not JSON: {text[:200]}") from exc
    if msg.get("error"):
        raise McpError(str(msg["error"]))
    return msg.get("result")


def _list_tools_raw(server: dict) -> list[dict]:
    transport = server.get("transport") or "stdio"
    if transport == "url":
        result = _http_jsonrpc(server, "tools/list", {})
        return list((result or {}).get("tools") or [])

    session = _StdioSession(server)
    try:
        result = session.request("tools/list", {})
        return list((result or {}).get("tools") or [])
    finally:
        session.close()


def _call_tool_raw(server: dict, tool_name: str, arguments: dict) -> Any:
    transport = server.get("transport") or "stdio"
    params = {"name": tool_name, "arguments": arguments or {}}
    if transport == "url":
        return _http_jsonrpc(server, "tools/call", params)

    session = _StdioSession(server)
    try:
        return session.request("tools/call", params)
    finally:
        session.close()


def list_ollama_tools_for_workspace(workspace_id: str) -> list[dict]:
    tools: list[dict] = []
    now = time.time()
    for server in mcp_registry.servers_for_workspace(workspace_id):
        server_id = server["id"]
        with _lock:
            cached = _tool_cache.get(server_id)
            if cached and now - cached[0] < _CACHE_TTL:
                tools.extend(cached[1])
                continue
        try:
            raw_tools = _list_tools_raw(server)
            shaped = [_schema_to_ollama(server_id, tool) for tool in raw_tools if tool.get("name")]
        except Exception as exc:
            shaped = [
                {
                    "type": "function",
                    "function": {
                        "name": _tool_name(server_id, "unavailable"),
                        "description": f"MCP server {server_id} is unreachable: {exc}",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ]
        with _lock:
            _tool_cache[server_id] = (now, shaped)
        tools.extend(shaped)
    return tools


def blurbs_for_workspace(workspace_id: str) -> list[str]:
    lines = []
    for server in mcp_registry.servers_for_workspace(workspace_id):
        label = server.get("name") or server["id"]
        lines.append(
            f"MCP `{label}` (id {server['id']}): tools are named mcp__{server['id']}__<tool>. "
            "Use them when they help the goal."
        )
    return lines


def call_tool(name: str, arguments: dict) -> str:
    parsed = parse_mcp_tool_name(name)
    if not parsed:
        return json.dumps({"error": f"not an mcp tool: {name}"})
    server_id, tool = parsed
    if tool == "unavailable":
        return json.dumps({"error": f"MCP server {server_id} is not reachable"})
    server = mcp_registry.get_server(server_id)
    if not server:
        return json.dumps({"error": f"MCP server {server_id} not found"})
    try:
        result = _call_tool_raw(server, tool, arguments or {})
        if isinstance(result, (dict, list)):
            return json.dumps(result)
        return json.dumps({"result": result})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def probe_server(server_id: str) -> dict:
    server = mcp_registry.get_server(server_id)
    if not server:
        raise McpError("MCP server not found")
    tools = _list_tools_raw(server)
    with _lock:
        _tool_cache[server_id] = (
            time.time(),
            [_schema_to_ollama(server_id, tool) for tool in tools if tool.get("name")],
        )
    return {
        "ok": True,
        "id": server_id,
        "tools": [
            {"name": t.get("name"), "description": (t.get("description") or "")[:200]}
            for t in tools
        ],
    }
