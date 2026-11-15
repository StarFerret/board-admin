"""Capacity in plain terms for Control → Overview: how many people this Mac can serve.

This is measured per model, not guessed. `start_test()` runs in the background
and, for each model it is asked to test:

1. **What the model is.** Name, size, quantization, and which engine runs it
   (llama.cpp or MLX, both on the Mac's GPU through Metal), read from Ollama.
2. **Does it fit at all.** The model is unloaded and this Mac's memory in use
   by everything else is read three times and averaged. A model whose file is
   bigger than what is left is not loaded; it is reported as not fitting.
3. **Memory.** The model is loaded sized for 1, 2, 3, 4, 6, then 8
   conversations of CONTEXT tokens. After each load we read what Ollama really
   allocated and whether all of it is on the GPU. The largest size that fits
   in memory and stays fully on the GPU is the memory limit. (An earlier
   version worked this out from the difference between two loads. Ollama's
   figure moves between loads, so that was unreliable. Do not go back to it.)
4. **Speed.** 1, 2, 3, 4, 6, then 8 questions sent at the same moment. Each
   level runs ROUNDS times and is averaged. Every question is timed from send
   to finish, queueing included, so it is the speed a person feels. The most
   at once that still averages COMFORT_SPEED is the speed limit.
5. **Answers at once** is the smaller of the two limits.

One number is still an assumption, a planning estimate rather than a
measurement: PEOPLE_PER_ANSWER named people share each answer slot. It depends
on how real people behave and needs usage data. The UI says so.
"""

from __future__ import annotations

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

import requests

from . import metrics, people, store
from .paths import DEFAULT_BOARD_PORT

COMFORT_SPEED = 10.0  # tokens per second a waiting person should feel, queueing included
PEOPLE_PER_ANSWER = 10  # named people per answer slot. A planning estimate. Not measured.
CONTEXT = 8192  # conversation size the capacity estimates assume
LEVELS = (1, 2, 3, 4, 6, 8)
ROUNDS = 3
ANSWER_TOKENS = 64
SETTING_KEY = "capacity_by_model"
TEST_PROMPT = "Write five plain sentences about how a small team shares work."
GB = 1024**3
ENGINES = {"ggml": "llama.cpp", "llamacpp": "llama.cpp", "mlx": "MLX"}

_state: dict[str, Any] = {"running": False, "step": "", "error": None}
_state_lock = threading.Lock()


def _base() -> str:
    return metrics._ollama_base()


def _default_model() -> Optional[str]:
    """The model the Board uses by default, else the first one Ollama has."""
    port = os.environ.get("PORT", str(DEFAULT_BOARD_PORT))
    try:
        data = requests.get(f"http://127.0.0.1:{port}/api/settings/ollama", timeout=2).json()
        name = (data.get("model") or "").strip()
        if name:
            return name
    except Exception:
        pass
    name = (os.environ.get("OLLAMA_MODEL") or "").strip()
    if name:
        return name
    models = installed_models()
    return models[0]["name"] if models else None


def installed_models() -> list[dict[str, Any]]:
    """Every model on this Mac with a plain description of what kind it is."""
    try:
        tags = requests.get(f"{_base()}/api/tags", timeout=3).json().get("models") or []
    except Exception:
        return []
    out = []
    for item in tags:
        details = item.get("details") or {}
        engine = ENGINES.get((details.get("runner") or "").lower())
        if not engine:
            engine = "MLX" if details.get("format") == "safetensors" else "llama.cpp"
        out.append(
            {
                "name": item.get("name"),
                "file_gb": round(int(item.get("size") or 0) / GB, 1),
                "parameters": details.get("parameter_size") or None,
                "quantization": details.get("quantization_level") or None,
                "engine": engine,
                "format": details.get("format") or None,
                "family": details.get("family") or None,
            }
        )
    return out


def saved() -> dict[str, Any]:
    raw = store.get_setting(SETTING_KEY)
    try:
        data = json.loads(raw) if raw else {}
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def _step(text: str) -> None:
    with _state_lock:
        _state["step"] = text


def _ask(model: str, context: int, tokens: int) -> dict[str, Any]:
    """One question. Returns tokens written and wall seconds, queue time included."""
    started = time.monotonic()
    resp = requests.post(
        f"{_base()}/api/generate",
        json={
            "model": model,
            "prompt": TEST_PROMPT,
            "stream": False,
            "options": {"num_predict": tokens, "num_ctx": context},
        },
        timeout=900,
    )
    wall = time.monotonic() - started
    resp.raise_for_status()
    return {"tokens": int(resp.json().get("eval_count") or 0), "seconds": wall}


def _loaded(model: str) -> Optional[dict[str, Any]]:
    data = requests.get(f"{_base()}/api/ps", timeout=5).json()
    for item in data.get("models") or []:
        if item.get("name") == model or item.get("model") == model:
            return item
    return None


def _unload_everything() -> None:
    try:
        for item in requests.get(f"{_base()}/api/ps", timeout=5).json().get("models") or []:
            requests.post(f"{_base()}/api/generate", json={"model": item.get("name"), "keep_alive": 0}, timeout=60)
    except requests.RequestException:
        pass
    time.sleep(2)


def _memory_without_ai() -> float:
    """Bytes in use by macOS and other apps with no model loaded. Three readings, averaged."""
    _unload_everything()
    readings = []
    for _ in range(3):
        readings.append(metrics._memory()["used_gb"] * GB)
        time.sleep(1)
    return sum(readings) / len(readings)


def _max_context(model: str) -> Optional[int]:
    try:
        info = requests.post(f"{_base()}/api/show", json={"model": model}, timeout=10).json().get("model_info") or {}
    except Exception:
        return None
    sizes = [v for k, v in info.items() if k.endswith(".context_length") and isinstance(v, int)]
    return max(sizes) if sizes else None


def _measure_memory(model: str, total: float, other: float) -> dict[str, Any]:
    room = total - other
    longest = _max_context(model)
    levels: list[dict[str, Any]] = []
    for count in LEVELS:
        if longest and CONTEXT * count > longest:
            break
        _step(f"{model}: loading it sized for {count} {'conversation' if count == 1 else 'conversations'}")
        _ask(model, CONTEXT * count, 1)
        item = _loaded(model) or {}
        size = int(item.get("size") or 0)
        vram = int(item.get("size_vram") or 0)
        if not size:
            raise RuntimeError(f"Could not read how much memory {model} uses. Try again.")
        on_gpu = vram >= size
        level = {
            "at_once": count,
            "gb": round(size / GB, 2),
            "on_gpu_percent": round(100 * vram / size),
            "fits": on_gpu and size <= room,
        }
        levels.append(level)
        if not level["fits"]:
            break
    # Some engines (MLX today) report the same figure whatever the conversation size.
    # Then the reading says the model fits, but not how many conversations do.
    grows = len(levels) < 3 or levels[-1]["gb"] - levels[0]["gb"] >= 0.1
    return {
        "total_gb": round(total / GB, 1),
        "other_gb": round(other / GB, 1),
        "room_gb": round(room / GB, 1),
        "levels": levels,
        "measured": grows,
        "fits": max([lv["at_once"] for lv in levels if lv["fits"]], default=0),
    }


def _measure_speed(model: str) -> list[dict[str, Any]]:
    levels: list[dict[str, Any]] = []
    _ask(model, CONTEXT, 8)  # warm up so loading time is not counted
    for count in LEVELS:
        felt: list[float] = []
        total: list[float] = []
        for round_no in range(1, ROUNDS + 1):
            _step(f"{model}: {count} {'person' if count == 1 else 'people'} asking at once, run {round_no} of {ROUNDS}")
            started = time.monotonic()
            with ThreadPoolExecutor(max_workers=count) as pool:
                results = list(pool.map(lambda _: _ask(model, CONTEXT, ANSWER_TOKENS), range(count)))
            wall = time.monotonic() - started
            speeds = [r["tokens"] / r["seconds"] for r in results if r["tokens"] > 0 and r["seconds"] > 0]
            if not speeds:
                raise RuntimeError(f"{model} gave empty answers during the test. Try again.")
            felt.append(sum(speeds) / len(speeds))
            total.append(sum(r["tokens"] for r in results) / wall)
        level = {
            "at_once": count,
            "speed_each": round(sum(felt) / len(felt), 1),  # averaged over the rounds
            "speed_total": round(sum(total) / len(total), 1),
            "comfortable": sum(felt) / len(felt) >= COMFORT_SPEED,
        }
        levels.append(level)
        if level["speed_each"] < COMFORT_SPEED / 2:
            break  # far past the limit; more load teaches nothing
    return levels


def _test_one(info: dict[str, Any], total: float, other: float) -> dict[str, Any]:
    model = info["name"]
    result: dict[str, Any] = {
        "model": model,
        "details": info,
        "chip": metrics.static_info().get("chip"),
        "measured_at": int(time.time()),
        "rounds": ROUNDS,
        "context": CONTEXT,
        "comfort_speed": COMFORT_SPEED,
    }
    room_gb = round((total - other) / GB, 1)
    if info["file_gb"] * GB > total - other:
        # Loading it anyway would push the Mac into swap and freeze it for everyone.
        result.update(
            status="too_big",
            at_once=0,
            reason=f"The model is {info['file_gb']} GB and this Mac has {room_gb} GB left after macOS and other apps. It was not loaded.",
        )
        return result
    try:
        memory = _measure_memory(model, total, other)
        if memory["fits"] == 0:
            result.update(
                status="too_big",
                at_once=0,
                memory=memory,
                reason=f"Once loaded it needs {memory['levels'][0]['gb']} GB and this Mac has {room_gb} GB left, or part of it fell off the GPU.",
            )
            return result
        speed = _measure_speed(model)
    except requests.RequestException:
        result.update(status="failed", at_once=0, reason="The AI stopped answering while this model was tested.")
        return result
    except RuntimeError as exc:
        result.update(status="failed", at_once=0, reason=str(exc))
        return result
    speed_limit = max([lv["at_once"] for lv in speed if lv["comfortable"]], default=0)
    memory_known = memory["measured"]
    at_once = min(speed_limit, memory["fits"]) if memory_known else speed_limit
    result.update(
        status="ok" if speed_limit else "too_slow",
        at_once=at_once,
        speed_limit=speed_limit,
        memory_limit=memory["fits"] if memory_known else None,
        limited_by="memory" if memory_known and memory["fits"] < speed_limit else "speed",
        # True when the answer is the most the test tries, so the real limit may be higher.
        at_ceiling=at_once == LEVELS[-1],
        alone_speed=speed[0]["speed_each"],
        memory=memory,
        levels=speed,
    )
    if not speed_limit:
        result["reason"] = f"One person alone gets {speed[0]['speed_each']} tokens per second, under the {COMFORT_SPEED:g} that feels comfortable."
    return result


def _run_test(which: str) -> None:
    started = int(time.time())
    metrics.recording_paused = True
    try:
        _run_test_inner(which)
    finally:
        # The test drives the AI flat out. That is not people using it.
        store.delete_load_between(started, int(time.time()))
        metrics.recording_paused = False


def _run_test_inner(which: str) -> None:
    try:
        models = installed_models()
        if not models:
            raise RuntimeError("There is no AI model on this Mac, or the AI is switched off. Open the Ollama app, then try again.")
        default = _default_model()
        if which != "all":
            models = [m for m in models if m["name"] == default]
            if not models:
                raise RuntimeError("The default model is not on this Mac. Pick one under Models, then try again.")
        _step("Reading this Mac's memory with no model loaded")
        total = (metrics._memory()["total_gb"] or 0) * GB
        other = _memory_without_ai()
        results = saved()
        for info in models:
            results[info["name"]] = _test_one(info, total, other)
            store.set_setting(SETTING_KEY, json.dumps(results))
        if default:
            _step("Putting the default model back")
            try:
                _ask(default, CONTEXT, 1)
            except requests.RequestException:
                pass
        with _state_lock:
            _state.update(running=False, step="", error=None)
    except RuntimeError as exc:
        with _state_lock:
            _state.update(running=False, step="", error=str(exc))
    except Exception:
        with _state_lock:
            _state.update(running=False, step="", error="The test stopped unexpectedly. Try again.")


def start_test(which: str = "default") -> None:
    with _state_lock:
        if _state["running"]:
            return
        _state.update(running=True, step="Starting", error=None)
    threading.Thread(target=_run_test, args=(which,), name="starferret-capacity", daemon=True).start()


def real_load() -> dict[str, Any]:
    """What actually happened: how much of each hour the AI spent answering."""
    now = int(time.time())
    hours = store.load_by_hour(now - 7 * 86400)

    def window(seconds: int) -> Optional[dict[str, Any]]:
        rows = [h for h in hours if h["hour"] >= (now - seconds) // 3600 * 3600]
        samples = sum(h["samples"] for h in rows)
        if not samples:
            return None
        busiest = max(rows, key=lambda h: h["busy_percent"])
        return {
            "hours_recorded": len(rows),
            "average_busy_percent": round(sum(h["busy_percent"] * h["samples"] for h in rows) / samples, 1),
            "busiest_hour": busiest["hour"],
            "busiest_percent": busiest["busy_percent"],
            "most_people": max(h["people"] for h in rows),
        }

    return {
        "day": window(86400),
        "week": window(7 * 86400),
        "hours": [h for h in hours if h["hour"] >= now - 86400],
    }


def summary() -> dict[str, Any]:
    results = saved()
    default = _default_model()
    measured = results.get(default) if default else None
    who = people.summary()
    using = who["active_people"]
    now = metrics.snapshot()
    gpu = now["now"]["gpu"]
    metal = now["metal"]

    seats = at_once = None
    if measured:
        at_once = measured["at_once"]
        seats = at_once * PEOPLE_PER_ANSWER
    with _state_lock:
        test = dict(_state)

    if seats is None:
        level, headline = "unknown", "Not measured yet"
        advice = "Run the test to measure how many people this Mac can serve."
    elif seats == 0:
        level, headline = "over", "Does not fit" if measured["status"] == "too_big" else "Too slow"
        advice = f"{measured.get('reason') or ''} Pick a smaller model under Models.".strip()
    else:
        used = using / seats
        if used >= 1:
            level, headline = "over", "Over capacity"
            advice = "More people use this Mac than it serves comfortably. Answers will queue. Add a Mac."
        elif used >= 0.8:
            level, headline = "tight", "Nearly full"
            advice = "Plan a second Mac before more people join."
        else:
            level, headline = "ok", "Plenty of room"
            advice = f"Room for about {seats - using} more people."

    # Things a non technical owner should hear about, in their words.
    warnings: list[str] = []
    if not metal["runtime_reachable"]:
        warnings.append("The AI is switched off on this Mac. Open the Ollama app to turn it on.")
    for model in metal["models"]:
        if model.get("gpu_percent") is not None and model["gpu_percent"] < 100:
            warnings.append(f"{model['name']} is too big for this Mac and is answering slowly. Pick a smaller model under Models.")
    if now["now"]["memory"]["pressure"] == "critical":
        warnings.append("This Mac is out of memory. Close other apps on it or answers will slow down.")
    load = real_load()
    if load["week"] and load["week"]["busiest_percent"] >= 80:
        warnings.append(
            "In its busiest hour this week the AI was answering almost without a break, so people were waiting. Think about another Mac."
        )
    if default and results and not measured:
        warnings.append(f"The default model is now {default}, which has not been tested on this Mac. Run the test.")

    return {
        "level": level,
        "headline": headline,
        "advice": advice,
        "seats": seats,
        "at_once": at_once,
        "people_using": using,
        "active_days": who["active_days"],
        "online_now": len(who["online_now"]),
        "busy_percent": gpu["percent"] if gpu["available"] else None,
        "ai_on": metal["runtime_reachable"],
        "full_speed": metal["state"] in ("ok", "idle"),
        "model": default,
        "model_details": next((m for m in installed_models() if m["name"] == default), None),
        "models": [
            {**info, "test": results.get(info["name"]), "default": info["name"] == default}
            for info in installed_models()
        ],
        "measured": measured,
        "people_per_answer": PEOPLE_PER_ANSWER,
        "load": load,
        "test": test,
        "warnings": warnings,
        "busy_history": [p["gpu"] for p in now["history"]],
        "sample_seconds": now["sample_seconds"],
    }
