"""Zara - WebSocket Bridge Server.

Streams real-time state from the Python backend to the React dashboard.
Runs as a lightweight thread alongside the main Zara process.

Protocol (all messages are JSON):
  Server → Client:
    { "type": "state",   "payload": { "zaraState": "STANDBY", "honorific": "Sir", "gender": "male" } }
    { "type": "metrics", "payload": { "cpu": 25, "ram": 60, "gpu": 10, "disk": 45 } }
    { "type": "message", "payload": { "role": "zara"|"user", "text": "..." } }
    { "type": "transcript", "payload": { "text": "...", "live": true } }
    { "type": "speaker", "payload": { "context": "direct"|"background"|"none" } }
    { "type": "api_health", "payload": { "groq": "online", ... } }
    { "type": "volume",  "payload": { "level": 60, "muted": false } }

  Client → Server:
    { "type": "command",  "text": "..." }
    { "type": "volume",   "level": 75 }
    { "type": "gender",   "value": "male"|"female"|"reset" }
    { "type": "bg_detection", "enabled": true }
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from typing import Any, Dict, Set

# ── Optional deps ─────────────────────────────────────────────────────────────
try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

try:
    import websockets
    _WS = True
except ImportError:
    _WS = False

HOST = "localhost"
PORT = 8765

# Shared mutable state — written by Zara core, read by WS broadcast loop
_shared: Dict[str, Any] = {
    "zaraState":   "STANDBY",
    "honorific":   "Sir",
    "gender":      "unknown",
    "volume":      60,
    "muted":       False,
    "conversation": [],          # last 100 messages
    "liveTranscript": "",
    "speakerContext": "none",
    "apiHealth": {
        "groq":       "checking",
        "deepgram":   "checking",
        "ollama":     "offline",
        "elevenlabs": "offline",
    },
}
_lock = threading.Lock()
_clients: Set = set()
_loop: asyncio.AbstractEventLoop | None = None


# ── Public API (called from Zara core threads) ────────────────────────────────

def set_state(state: str):
    with _lock:
        _shared["zaraState"] = state.upper()
    _enqueue("state", {"zaraState": _shared["zaraState"],
                        "honorific": _shared["honorific"],
                        "gender":    _shared["gender"]})

def add_message(role: str, text: str):
    msg = {"role": role, "text": text}
    with _lock:
        _shared["conversation"].append(msg)
        if len(_shared["conversation"]) > 100:
            _shared["conversation"].pop(0)
    _enqueue("message", msg)

def set_live_transcript(text: str, live: bool = True):
    with _lock:
        _shared["liveTranscript"] = text
    _enqueue("transcript", {"text": text, "live": live})

def set_speaker_context(context: str):
    with _lock:
        _shared["speakerContext"] = context
    _enqueue("speaker", {"context": context})

def set_volume(level: int, muted: bool = False):
    with _lock:
        _shared["volume"] = level
        _shared["muted"]  = muted
    _enqueue("volume", {"level": level, "muted": muted})

def set_api_health(updates: dict):
    with _lock:
        _shared["apiHealth"].update(updates)
    _enqueue("api_health", dict(_shared["apiHealth"]))

def set_gender(gender: str, honorific: str):
    with _lock:
        _shared["gender"]    = gender
        _shared["honorific"] = honorific
    _enqueue("state", {"zaraState": _shared["zaraState"],
                        "honorific": honorific,
                        "gender":    gender})


# ── Internal broadcast queue ──────────────────────────────────────────────────

_queue: asyncio.Queue | None = None

def _enqueue(msg_type: str, payload: dict):
    if _loop and _queue:
        msg = json.dumps({"type": msg_type, "payload": payload})
        _loop.call_soon_threadsafe(_queue.put_nowait, msg)


# ── Metrics sampler (every 2.5s) ──────────────────────────────────────────────

async def _metrics_loop():
    while True:
        await asyncio.sleep(2.5)
        if not _PSUTIL:
            continue
        try:
            cpu  = round(psutil.cpu_percent(interval=None))
            ram  = round(psutil.virtual_memory().percent)
            disk = round(psutil.disk_usage('/').percent)
            try:
                # GPU via nvidia-smi if available
                import subprocess
                out = subprocess.check_output(
                    ["nvidia-smi", "--query-gpu=utilization.gpu",
                     "--format=csv,noheader,nounits"],
                    timeout=1, stderr=subprocess.DEVNULL
                )
                gpu = int(out.decode().strip().split('\n')[0])
            except Exception:
                gpu = 0
            msg = json.dumps({"type": "metrics",
                               "payload": {"cpu": cpu, "ram": ram, "gpu": gpu, "disk": disk}})
            for ws in list(_clients):
                try:
                    await ws.send(msg)
                except Exception:
                    pass
        except Exception:
            pass


# ── WebSocket connection handler ──────────────────────────────────────────────

async def _handler(websocket):
    _clients.add(websocket)
    # Send full snapshot on connect
    with _lock:
        snap = dict(_shared)
    try:
        await websocket.send(json.dumps({"type": "snapshot", "payload": snap}))
    except Exception:
        pass

    try:
        async for raw in websocket:
            try:
                msg = json.loads(raw)
                await _handle_client_msg(msg)
            except Exception:
                pass
    except Exception:
        pass
    finally:
        _clients.discard(websocket)


async def _handle_client_msg(msg: dict):
    t = msg.get("type")
    if t == "command":
        text = msg.get("text", "").strip()
        if text:
            try:
                import zara_core
                threading.Thread(
                    target=zara_core.generate_response,
                    args=(text,),
                    daemon=True
                ).start()
            except Exception as e:
                print(f"[WS Bridge] Command error: {e}")

    elif t == "volume":
        level = int(msg.get("level", 60))
        try:
            from volume_controller import get_volume_controller
            vc = get_volume_controller()
            vc.set_volume(level / 100.0)
            set_volume(level, _shared.get("muted", False))
        except Exception as e:
            print(f"[WS Bridge] Volume error: {e}")

    elif t == "gender":
        val = msg.get("value", "reset")
        try:
            from gender_detector import get_gender_detector
            det = get_gender_detector()
            if val == "reset":
                det.reset()
                set_gender("unknown", "Sir")
            else:
                det._set_gender(type('G', (), {'value': val})(), 0.95)
                h = det.get_honorific()
                set_gender(val, h)
        except Exception as e:
            print(f"[WS Bridge] Gender error: {e}")

    elif t == "bg_detection":
        enabled = bool(msg.get("enabled", True))
        try:
            import local_ears
            if hasattr(local_ears, '_bg_detector') and local_ears._bg_detector:
                local_ears._bg_detector_enabled = enabled
        except Exception:
            pass


# ── Broadcast loop ────────────────────────────────────────────────────────────

async def _broadcast_loop():
    while True:
        msg = await _queue.get()
        dead = set()
        for ws in list(_clients):
            try:
                await ws.send(msg)
            except Exception:
                dead.add(ws)
        _clients -= dead


# ── Server entry point ────────────────────────────────────────────────────────

async def _serve():
    global _queue
    _queue = asyncio.Queue()
    async with websockets.serve(_handler, HOST, PORT):
        print(f"[WS Bridge] Listening on ws://{HOST}:{PORT}")
        await asyncio.gather(_broadcast_loop(), _metrics_loop())


def start_bridge():
    """Launch WS bridge in a background daemon thread. Call from main.py."""
    if not _WS:
        print("[WS Bridge] websockets not installed — dashboard bridge disabled.")
        print("            Run: pip install websockets psutil")
        return

    global _loop

    def _run():
        global _loop
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        _loop.run_until_complete(_serve())

    t = threading.Thread(target=_run, daemon=True, name="ZaraWSBridge")
    t.start()
    print("[WS Bridge] Started.")
