import json
import os
import re
import shutil
import subprocess
import threading
from typing import Any, Callable, Optional
from urllib.parse import urlparse, urlunparse

import requests
from requests import HTTPError, Response

from . import usage

DEFAULT_LOCAL = "http://127.0.0.1:11434"
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3.8:27b")

# Preferred auto-downgrade ladder (largest → smallest). Exactly three models.
# qwen3.8:27b is the official 4-bit (Q4_K_M) build.
FAILOVER_LADDER = [
    "qwen3.8:27b",       # 27B 4-bit (Q4_K_M) — primary
    "gemma4:latest",     # mid
    "gemma4:12b-mlx",    # Gemma 4 12B, MLX (~7.7GB) — last resort, and the installer's pick under 24GB
]

# Ladder entries that are not MLX builds. Failover never falls back to one, and
# never downloads one. StarFerret ships MLX builds only.
NOT_MLX: set[str] = set()

FAILOVER_HTTP_STATUS = {408, 429, 500, 502, 503, 504}
_pull_lock = threading.Lock()
_on_failover: Optional[Callable[[str, str], None]] = None


class ModelFailed(Exception):
    """This model could not complete the request. Try a smaller one."""


def set_failover_listener(callback: Optional[Callable[[str, str], None]]) -> None:
    """Register (from_model, to_model) notifier. Wired from app.py to Socket.IO."""
    global _on_failover
    _on_failover = callback


def normalize_base_url(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        raise ValueError("Ollama address is empty")
    if "://" not in text:
        text = "http://" + text
    parsed = urlparse(text)
    scheme = parsed.scheme or "http"
    host = parsed.hostname
    if not host:
        raise ValueError("Ollama address has no host")
    if host == "localhost":
        host = "127.0.0.1"
    port = parsed.port
    if port is None and scheme == "http":
        port = 11434
    netloc = f"{host}:{port}" if port else host
    path = (parsed.path or "").rstrip("/")
    if path == "/":
        path = ""
    return urlunparse((scheme, netloc, path, "", "", ""))


def cli_installed() -> bool:
    return shutil.which("ollama") is not None


def probe(base_url: str, timeout: float = 2.5) -> dict:
    url = normalize_base_url(base_url).rstrip("/") + "/api/tags"
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        models = [m.get("name") for m in data.get("models", []) if m.get("name")]
        not_mlx = [
            m.get("name")
            for m in data.get("models", [])
            if m.get("name") and not _is_mlx(m.get("details") or {})
        ]
        return {"ok": True, "models": models, "not_mlx": not_mlx, "error": None}
    except Exception as exc:
        return {"ok": False, "models": [], "not_mlx": [], "error": str(exc)}


def _is_mlx(details: dict) -> bool:
    runner = str(details.get("runner") or "").lower()
    if runner:
        return runner == "mlx"
    return str(details.get("format") or "").lower() != "gguf"


def resolve_model(models: list[str] | None = None, preferred: str | None = None) -> str:
    models = models or []
    for candidate in (preferred, DEFAULT_MODEL):
        if not candidate:
            continue
        for name in models:
            if name == candidate or name.startswith(candidate + ":"):
                return name
        if not models:
            return candidate
    return models[0] if models else DEFAULT_MODEL


def estimate_model_billions(name: str) -> float:
    """Rough size rank for failover (smaller models tried after the primary)."""
    n = (name or "").lower()
    ladder_rank = _ladder_index(n)
    if ladder_rank is not None:
        # Space ladder entries so order beats fuzzy parsing.
        return 1000.0 - ladder_rank

    qwen = re.search(r"qwen\d*\.(\d+)", n)
    if qwen:
        return float(qwen.group(1))
    for pattern in (r"(\d+(?:\.\d+)?)\s*b\b", r":(\d+(?:\.\d+)?)\s*b\b"):
        match = re.search(pattern, n)
        if match:
            return float(match.group(1))
    match = re.search(r"(\d+(?:\.\d+)?)\s*m\b", n)
    if match:
        return float(match.group(1)) / 1000.0
    stem = n.split(":")[0]
    gemma = re.search(r"gemma(\d+)", stem)
    if gemma:
        return float(gemma.group(1)) * 4
    for piece in reversed(re.findall(r"\d+(?:\.\d+)?", stem)):
        value = float(piece)
        if 0.05 <= value <= 200:
            return value
    return 50.0


def _ladder_index(name: str) -> int | None:
    n = (name or "").strip().lower()
    if not n:
        return None
    # An exact rung first: two rungs can share a family (gemma4:latest, gemma4:12b-mlx).
    for idx, item in enumerate(FAILOVER_LADDER):
        if n == item.lower():
            return idx
    # Otherwise the first rung of the same family ("qwen3.8", "qwen3.8:27b-q8").
    stem = n.split(":")[0]
    for idx, item in enumerate(FAILOVER_LADDER):
        if stem == item.lower().split(":")[0]:
            return idx
    return None


def _match_installed(wanted: str, installed: list[str]) -> str | None:
    wanted = (wanted or "").strip()
    if not wanted:
        return None
    for name in installed:
        if name == wanted:
            return name
    # Same family counts as a match, but never another rung of the ladder, or a
    # gemma4:latest download would pass for gemma4:12b-mlx and the reverse.
    other_rungs = {item.lower() for item in FAILOVER_LADDER} - {wanted.lower()}
    stem = wanted.split(":")[0]
    for name in installed:
        if name.lower() in other_rungs:
            continue
        if name == stem or name.startswith(stem + ":"):
            return name
    return None


def failover_model_chain(primary: str, installed: list[str] | None) -> list[str]:
    """Primary first, then smaller ladder/installed models (smallest last among retries)."""
    primary = (primary or DEFAULT_MODEL).strip() or DEFAULT_MODEL
    installed = installed or []
    seen: set[str] = set()
    chain: list[str] = []

    def add(name: str) -> None:
        name = (name or "").strip()
        if not name or name in seen:
            return
        seen.add(name)
        chain.append(name)

    add(primary)
    ceiling = estimate_model_billions(primary)

    # Walk the curated ladder below the primary.
    primary_idx = _ladder_index(primary)
    if primary_idx is not None:
        for item in FAILOVER_LADDER[primary_idx + 1 :]:
            matched = _match_installed(item, installed)
            if matched:
                add(matched)

    # Any other installed model smaller than primary, smallest first.
    others = sorted(
        (
            name
            for name in set(installed)
            if name != primary and estimate_model_billions(name) < ceiling
        ),
        key=lambda item: (estimate_model_billions(item), item),
    )
    for name in others:
        add(name)

    return chain


def next_pull_candidate(primary: str, installed: list[str] | None) -> str | None:
    """Next ladder model below primary that is not installed yet."""
    installed = installed or []
    primary_idx = _ladder_index(primary)
    start = (primary_idx + 1) if primary_idx is not None else 0
    for item in FAILOVER_LADDER[start:]:
        if item in NOT_MLX:
            continue
        if not _match_installed(item, installed):
            return item
    return None


def pull_model(name: str, timeout: float = 600) -> bool:
    """Pull a model via the local ollama CLI. Returns True on success."""
    if not name or not cli_installed():
        return False
    with _pull_lock:
        try:
            proc = subprocess.run(
                ["ollama", "pull", name],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            return proc.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False


def delete_model(name: str, timeout: float = 120) -> bool:
    """Delete a model via the local ollama CLI. Returns True on success."""
    if not name or not cli_installed():
        return False
    with _pull_lock:
        try:
            proc = subprocess.run(
                ["ollama", "rm", name],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            return proc.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False


class ModelNotReady(RuntimeError):
    """Ollama answers but has no model yet, usually because the first download is still running."""


NO_MODEL_MESSAGE = (
    "No AI model is ready on this Mac yet. If StarFerret was just installed, the model is "
    "still downloading. Control shows the progress under Models. Try again when it says Ready."
)


def _installed_models(base_url: str) -> list[str]:
    result = probe(base_url, timeout=3)
    return result["models"] if result.get("ok") else []


def _persist_model_choice(model: str) -> None:
    from . import db

    db.set_setting("ollama_model", model)


def _notify_failover(before: str, after: str) -> None:
    if before == after:
        return
    _persist_model_choice(after)
    if _on_failover:
        try:
            _on_failover(before, after)
        except Exception:
            pass


def _should_failover(exc: BaseException) -> bool:
    if isinstance(exc, ModelFailed):
        return True
    if isinstance(exc, HTTPError):
        code = exc.response.status_code if exc.response is not None else 500
        return code in FAILOVER_HTTP_STATUS or code >= 500
    if isinstance(
        exc,
        (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
            requests.exceptions.ChunkedEncodingError,
        ),
    ):
        return True
    text = str(exc).lower()
    if any(token in text for token in ("out of memory", "oom", "cuda", "resource", "unavailable")):
        return True
    return False


def _response_failover(resp: Response) -> bool:
    if resp.status_code in FAILOVER_HTTP_STATUS or resp.status_code >= 500:
        return True
    if resp.status_code == 404:
        return True
    return False


_think_ok: dict[str, bool] = {}
# Ollama's MLX runner rejects format=json with 501 "structured output is unavailable".
# Those models get the same prompt without the flag; callers parse JSON from plain text.
_format_ok: dict[str, bool] = {}


def _no_structured_output(resp: Response) -> bool:
    if resp.status_code not in {400, 501}:
        return False
    try:
        return "structured output" in (resp.json().get("error") or "").lower()
    except ValueError:
        return False


def _payload(model: str, messages: list[dict], *, tools, response_format, think: bool, stream: bool) -> dict:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": stream,
    }
    if tools:
        payload["tools"] = tools
    if response_format and _format_ok.get(model, True):
        payload["format"] = response_format
    if think and _think_ok.get(model, True):
        payload["think"] = True
    return payload


def _post_chat(base_url: str, payload: dict, *, timeout: float, stream: bool):
    return requests.post(
        normalize_base_url(base_url) + "/api/chat",
        json=payload,
        timeout=timeout,
        stream=stream,
    )


def _chat_once(
    base_url: str,
    payload: dict,
    *,
    chosen: str,
    timeout: float,
) -> dict:
    resp = _post_chat(base_url, payload, timeout=timeout, stream=False)
    if payload.get("format") and _no_structured_output(resp):
        _format_ok[chosen] = False
        payload.pop("format", None)
        resp = _post_chat(base_url, payload, timeout=timeout, stream=False)
    if resp.status_code == 400 and payload.get("think"):
        _think_ok[chosen] = False
        payload.pop("think", None)
        resp = _post_chat(base_url, payload, timeout=timeout, stream=False)
    if _response_failover(resp):
        raise ModelFailed(f"Model {chosen} failed: {resp.status_code}")
    if resp.status_code >= 400:
        resp.raise_for_status()
    return resp.json()


def _chat_stream_once(
    base_url: str,
    payload: dict,
    *,
    chosen: str,
    timeout: float,
    on_token: Optional[Callable[[str], None]],
    on_thinking: Optional[Callable[[str], None]],
) -> dict:
    resp = _post_chat(base_url, payload, timeout=timeout, stream=True)
    if resp.status_code == 400 and payload.get("think"):
        _think_ok[chosen] = False
        payload.pop("think", None)
        resp.close()
        resp = _post_chat(base_url, payload, timeout=timeout, stream=True)
    if _response_failover(resp):
        resp.close()
        raise ModelFailed(f"Model {chosen} failed: {resp.status_code}")
    if resp.status_code >= 400:
        resp.raise_for_status()
    content = ""
    thinking = ""
    tool_calls: list[dict] = []
    role = "assistant"
    counts: dict[str, int] = {}
    try:
        for line in resp.iter_lines():
            if not line:
                continue
            chunk = json.loads(line.decode("utf-8"))
            if chunk.get("error"):
                raise ModelFailed(str(chunk.get("error")))
            msg = chunk.get("message") or {}
            role = msg.get("role") or role
            thought = msg.get("thinking") or ""
            if thought:
                thinking += thought
                if on_thinking:
                    on_thinking(thought)
            piece = msg.get("content") or ""
            if piece:
                content += piece
                if on_token:
                    on_token(piece)
            if msg.get("tool_calls"):
                tool_calls.extend(msg["tool_calls"])
            if chunk.get("done"):
                for key in ("prompt_eval_count", "eval_count"):
                    if chunk.get(key) is not None:
                        counts[key] = chunk[key]
                break
    except ModelFailed:
        resp.close()
        raise
    except (requests.exceptions.RequestException, json.JSONDecodeError) as exc:
        resp.close()
        raise ModelFailed(str(exc)) from exc
    except BaseException:
        # A caller stopping mid stream (the Stop button). Close so Ollama stops generating.
        resp.close()
        raise
    result = {"role": role, "content": content, "thinking": thinking}
    if tool_calls:
        result["tool_calls"] = tool_calls
    return {"message": result, "done": True, **counts}


def _run_with_failover(
    base_url: str,
    primary: str,
    attempt,
    *,
    on_retry: Optional[Callable[[str], None]] = None,
    allow_pull: bool = True,
):
    probe_result = probe(base_url, timeout=3)
    installed = probe_result["models"] if probe_result.get("ok") else []
    skip = set(probe_result.get("not_mlx") or []) | NOT_MLX
    # Ollama is up but empty: the installer (through Control) is almost certainly still
    # downloading the first model. Do not start a second multi GB download from here.
    if probe_result.get("ok") and not installed:
        raise ModelNotReady(NO_MODEL_MESSAGE)
    last_exc: BaseException | None = None
    tried: set[str] = set()

    def try_chain(chain: list[str]):
        nonlocal last_exc
        for index, chosen in enumerate(chain):
            if chosen in tried:
                continue
            tried.add(chosen)
            try:
                if index and on_retry:
                    on_retry(chosen)
                result = attempt(chosen)
                if chosen != primary:
                    _notify_failover(primary, chosen)
                return result
            except Exception as exc:
                last_exc = exc
                if not _should_failover(exc):
                    raise
        return None

    # Fall back only to MLX builds. The primary is whatever the owner chose, so it always gets a try.
    chain = [
        name
        for index, name in enumerate(failover_model_chain(primary, installed))
        if index == 0 or name not in skip
    ]
    result = try_chain(chain)
    if result is not None:
        return result

    if allow_pull:
        candidate = next_pull_candidate(primary, installed)
        if candidate and pull_model(candidate):
            installed = _installed_models(base_url)
            matched = _match_installed(candidate, installed)
            if matched:
                if on_retry:
                    on_retry(matched)
                try:
                    result = attempt(matched)
                    _notify_failover(primary, matched)
                    return result
                except Exception as exc:
                    last_exc = exc
                    if not _should_failover(exc):
                        raise

    if last_exc:
        raise last_exc
    raise RuntimeError("Ollama chat failed with no models to try")


def chat(
    base_url: str,
    messages: list[dict],
    *,
    model: Optional[str] = None,
    tools: Optional[list] = None,
    timeout: float = 180,
    response_format: Optional[str] = None,
    think: bool = False,
) -> dict:
    primary = model or DEFAULT_MODEL

    def attempt(chosen: str):
        payload = _payload(
            chosen, messages, tools=tools, response_format=response_format, think=think, stream=False
        )
        result = _chat_once(base_url, payload, chosen=chosen, timeout=timeout)
        usage.note(chosen, result)
        return result

    return _run_with_failover(base_url, primary, attempt)


def chat_stream(
    base_url: str,
    messages: list[dict],
    *,
    model: Optional[str] = None,
    tools: Optional[list] = None,
    timeout: float = 300,
    think: bool = False,
    on_token: Optional[Callable[[str], None]] = None,
    on_thinking: Optional[Callable[[str], None]] = None,
    on_retry: Optional[Callable[[str], None]] = None,
) -> dict:
    primary = model or DEFAULT_MODEL

    def attempt(chosen: str):
        payload = _payload(chosen, messages, tools=tools, response_format=None, think=think, stream=True)
        result = _chat_stream_once(
            base_url,
            payload,
            chosen=chosen,
            timeout=timeout,
            on_token=on_token,
            on_thinking=on_thinking,
        )
        usage.note(chosen, result)
        return result

    return _run_with_failover(base_url, primary, attempt, on_retry=on_retry)
