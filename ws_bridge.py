"""Zara - WebSocket Bridge Server.

Streams real-time state from the Python backend to the React dashboard.

Protocol (all messages are JSON):
  Server → Client:
    { "type": "state",        "payload": { "zaraState": "STANDBY", "honorific": "Sir", "gender": "male" } }
    { "type": "metrics",      "payload": { "cpu": 25, "ram": 60, "gpu": 10, "disk": 45 } }
    { "type": "message",      "payload": { "role": "zara"|"user", "text": "..." } }
    { "type": "transcript",   "payload": { "text": "...", "live": true } }
    { "type": "subtitle",     "payload": { "zara": "...", "user": "..." } }
    { "type": "speaker",      "payload": { "context": "direct"|"background"|"ambient"|"none" } }
    { "type": "bg_task",      "payload": { "text": "Thinking..." } }
    { "type": "api_health",   "payload": { "groq": "online", ... } }
    { "type": "volume",       "payload": { "level": 60, "muted": false } }
    { "type": "windows",      "payload": { "open": [...], "minimized": [...] } }
    { "type": "orb_frame",    "payload": { "frame": "<base64 PNG>" } }
    { "type": "screen_frame", "payload": { "frame": "<base64 JPEG>", "title": "Chrome" } }
    { "type": "memory_stats", "payload": { "stored": 120, "semantic": 45, "recent": [...] } }

  Client → Server:
    { "type": "command",        "text": "..." }
    { "type": "volume",         "level": 75 }
    { "type": "gender",         "value": "male"|"female"|"reset" }
    { "type": "bg_detection",   "enabled": true }
    { "type": "capture_window", "title": "Spotify" }      ← capture specific app window
    { "type": "capture_screen"  }                          ← capture full desktop
    { "type": "stop_capture"    }                          ← stop live capture
    { "type": "get_windows"     }                          ← request window list refresh
    { "type": "window_action",  "hwnd": 123, "action": "focus"|"minimize"|"restore" }
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import threading
import time
from typing import Any, Dict, Optional, Set

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

try:
    from PIL import ImageGrab, Image
    _PIL = True
except ImportError:
    _PIL = False

try:
    import win32gui
    import win32con
    import win32process
    import win32api
    _WIN32 = True
except ImportError:
    _WIN32 = False

HOST = "localhost"
PORT = 8765

# ── Shared mutable state ──────────────────────────────────────────────────────
_shared: Dict[str, Any] = {
    "zaraState":    "STANDBY",
    "honorific":    "Sir",
    "gender":       "unknown",
    "volume":       60,
    "muted":        False,
    "conversation": [],
    "liveTranscript": "",
    "subtitleZara": "",
    "subtitleUser": "",
    "speakerContext": "none",
    "bgTask": "",
    "apiHealth": {
        "groq":       "checking",
        "deepgram":   "checking",
        "ollama":     "offline",
        "elevenlabs": "offline",
    },
    "activeMode":   "standard",
}
_lock = threading.Lock()
_clients: Set = set()
_loop: Optional[asyncio.AbstractEventLoop] = None
_queue: Optional[asyncio.Queue] = None

# ── Screen/window capture state ───────────────────────────────────────────────
_capture_active = False
_capture_target: Optional[str] = None   # None = full desktop, str = window title
_capture_task: Optional[asyncio.Task] = None

# ── Orb frame source (set by orb_bridge if pygame is running) ─────────────────
_orb_frame_callback = None   # callable() → base64 PNG str | None


def _load_persisted_prefs():
    """Load gender and honorific from zara_prefs.json on startup."""
    if os.path.exists("zara_prefs.json"):
        try:
            with open("zara_prefs.json", "r") as f:
                prefs = json.load(f)
                with _lock:
                    if "gender" in prefs:
                        _shared["gender"] = prefs["gender"]
                    if "honorific" in prefs:
                        _shared["honorific"] = prefs["honorific"]
            print(f"[WS Bridge] Loaded persisted prefs: {_shared['honorific']}")
        except Exception as e:
            print(f"[WS Bridge] Failed to load prefs: {e}")


# ── Public API (called from Zara core threads) ────────────────────────────────

def set_state(state: str):
    with _lock:
        _shared["zaraState"] = state.upper()
    _enqueue("state", {
        "zaraState": _shared["zaraState"],
        "honorific": _shared["honorific"],
        "gender":    _shared["gender"],
    })
    # Keep headless pygame orb color/animation in lockstep with Zara state.
    try:
        from orb_bridge import sync_with_zara_state
        sync_with_zara_state(_shared["zaraState"])
    except Exception:
        pass


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


def set_subtitles(zara_text: Optional[str] = None, user_text: Optional[str] = None):
    with _lock:
        if zara_text is not None:
            _shared["subtitleZara"] = str(zara_text or "")
        if user_text is not None:
            _shared["subtitleUser"] = str(user_text or "")
        payload = {
            "zara": _shared["subtitleZara"],
            "user": _shared["subtitleUser"],
        }
    _enqueue("subtitle", payload)


def set_speaker_context(context: str):
    with _lock:
        _shared["speakerContext"] = context
    _enqueue("speaker", {"context": context})


def set_bg_task(text: str):
    with _lock:
        _shared["bgTask"] = str(text or "")
    _enqueue("bg_task", {"text": _shared["bgTask"]})


def set_volume(level: int, muted: bool = False):
    with _lock:
        _shared["volume"] = level
        _shared["muted"] = muted
    _enqueue("volume", {"level": level, "muted": muted})


def set_api_health(updates: dict):
    with _lock:
        _shared["apiHealth"].update(updates)
    _enqueue("api_health", dict(_shared["apiHealth"]))


def set_gender(gender: str, honorific: str):
    with _lock:
        _shared["gender"] = gender
        _shared["honorific"] = honorific
    _enqueue("state", {
        "zaraState": _shared["zaraState"],
        "honorific": honorific,
        "gender":    gender,
        "activeMode": _shared.get("activeMode", "standard")
    })


def set_mode(mode: str):
    """Set the dashboard layout mode."""
    with _lock:
        _shared["activeMode"] = mode
    _enqueue("state", {
        "zaraState": _shared["zaraState"],
        "honorific": _shared["honorific"],
        "gender":    _shared["gender"],
        "activeMode": mode
    })


def set_metrics(cpu: float, ram: float, gpu: float = 0, disk: float = 0, voice_amp: float = 0):
    """Manually push metrics to the dashboard (used by hardware sensors)."""
    _enqueue("metrics", {
        "cpu": cpu,
        "ram": ram,
        "gpu": gpu,
        "disk": disk,
        "voice_amp": voice_amp
    })


def push_orb_frame(frame_b64: str):
    """Called from the pygame orb thread to stream frames to React."""
    _enqueue("orb_frame", {"frame": frame_b64})


def register_orb_callback(cb):
    """Register a callable that returns the latest orb frame as base64 PNG."""
    global _orb_frame_callback
    _orb_frame_callback = cb


def broadcast_context_card(card_type: str, content: str, label: str = ""):
    """Broadcasts a new context card to all connected dashboard clients."""
    _enqueue("context_card", {
        "card_type": card_type, 
        "content": content, 
        "label": label,
        "timestamp": time.time()
    })


def broadcast_agent_task(task_id: str, role: str, instruction: str, status: str, result: Optional[str] = None):
    """Broadcasts an agent task update to the dashboard."""
    _enqueue("agent_task", {
        "id": task_id,
        "role": role,
        "instruction": instruction,
        "status": status,
        "result": result,
        "timestamp": time.time()
    })


# ── Window enumeration ────────────────────────────────────────────────────────

def get_windows() -> dict:
    """Return {'open': [...], 'minimized': [...]} with window info dicts."""
    open_wins = []
    minimized_wins = []

    if _WIN32:
        def _enum_cb(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd)
            if not title or len(title) < 2:
                return
            try:
                rect = win32gui.GetWindowRect(hwnd)
            except Exception:
                return
            is_min = bool(win32gui.IsIconic(hwnd))
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                h = win32api.OpenProcess(0x0400 | 0x0010, False, pid)
                pname = win32process.GetModuleFileNameEx(h, 0).split("\\")[-1]
            except Exception:
                pname = "unknown.exe"
            info = {
                "title": title,
                "hwnd": hwnd,
                "process": pname,
                "x": rect[0], "y": rect[1],
                "width": rect[2] - rect[0],
                "height": rect[3] - rect[1],
            }
            if is_min:
                minimized_wins.append(info)
            else:
                open_wins.append(info)

        win32gui.EnumWindows(_enum_cb, None)

    elif _PSUTIL:
        # Cross-platform fallback: list running processes as proxy
        seen = set()
        for proc in psutil.process_iter(["pid", "name"]):
            name = proc.info["name"] or ""
            if name and name not in seen and not name.startswith("svchost"):
                seen.add(name)
                open_wins.append({
                    "title": name.replace(".exe", ""),
                    "hwnd": proc.info["pid"],
                    "process": name,
                    "x": 0, "y": 0, "width": 0, "height": 0,
                })

    return {"open": open_wins, "minimized": minimized_wins}


def broadcast_windows():
    """Push current window list to all clients."""
    data = get_windows()
    _enqueue("windows", data)


# ── Screen/window capture helpers ─────────────────────────────────────────────

def _capture_frame(target_title: Optional[str] = None, quality: int = 60) -> Optional[str]:
    """
    Capture a frame (full screen or specific window) and return as base64 JPEG.
    quality 1-95; lower = smaller payload.
    """
    if not _PIL:
        return None
    try:
        if target_title and _WIN32:
            hwnd = win32gui.FindWindow(None, target_title)
            if not hwnd:
                # Partial match
                def _find(h, _):
                    t = win32gui.GetWindowText(h)
                    if target_title.lower() in t.lower():
                        return h
                hwnd = None
                def _cb(h, extra):
                    nonlocal hwnd
                    t = win32gui.GetWindowText(h)
                    if target_title.lower() in t.lower() and win32gui.IsWindowVisible(h):
                        hwnd = h
                win32gui.EnumWindows(_cb, None)

            if hwnd:
                # Bring window to front and capture its rect
                win32gui.SetForegroundWindow(hwnd)
                time.sleep(0.05)
                rect = win32gui.GetWindowRect(hwnd)
                x1, y1, x2, y2 = rect
                img = ImageGrab.grab(bbox=(x1, y1, x2, y2))
            else:
                img = ImageGrab.grab()
        else:
            img = ImageGrab.grab()

        # Resize to max 1280px wide to keep payload small
        max_w = 1280
        if img.width > max_w:
            ratio = max_w / img.width
            img = img.resize((max_w, int(img.height * ratio)), Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        print(f"[WS Bridge] Capture error: {e}")
        return None


# ── Internal broadcast queue ──────────────────────────────────────────────────

def _enqueue(msg_type: str, payload: dict):
    if _loop and _queue:
        msg = json.dumps({"type": msg_type, "payload": payload})
        _loop.call_soon_threadsafe(_queue.put_nowait, msg)


# ── Background loops ──────────────────────────────────────────────────────────

async def _metrics_loop():
    """Push system metrics every 2.5 s."""
    while True:
        await asyncio.sleep(2.5)
        if not _PSUTIL or not _clients:
            continue
        try:
            cpu  = round(psutil.cpu_percent(interval=None))
            ram  = round(psutil.virtual_memory().percent)
            disk = round(psutil.disk_usage("/").percent)
            gpu  = 0
            voice_amp = 0.0
            try:
                import subprocess
                # Check for NVIDIA GPU utilization
                out = subprocess.check_output(
                    ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                    timeout=0.5, stderr=subprocess.DEVNULL
                )
                gpu = int(out.decode().strip().split('\n')[0])
            except (Exception, subprocess.CalledProcessError):
                # Fallback for non-NVIDIA or missing drivers
                gpu = 0
            try:
                import state as app_state
                amp_obj = getattr(app_state, "current_volume", 0.0)
                voice_amp = float(amp_obj.value if hasattr(amp_obj, "value") else amp_obj or 0.0)
            except Exception:
                voice_amp = 0.0
            _enqueue("metrics", {
                "cpu": cpu,
                "ram": ram,
                "gpu": gpu,
                "disk": disk,
                "voice_amp": voice_amp
            })

        except Exception:
            pass


async def _window_sync_loop():
    """Polls system windows and broadcasts to the dashboard every 2s."""
    try:
        from zara_window_manager import get_window_manager
        wm = get_window_manager()
    except Exception:
        return

    while True:
        try:
            if _clients:
                windows = wm.get_active_windows()
                _enqueue("window_sync", {
                    "open": [w['title'] for w in windows if not w['minimized']],
                    "minimized": [w['title'] for w in windows if w['minimized']]
                })
        except Exception as e:
            print(f"[WS Bridge] Window sync error: {e}")
        await asyncio.sleep(2.0)


async def _windows_loop():
    """Push window list every 5 s."""
    while True:
        await asyncio.sleep(5)
        if not _clients:
            continue
        try:
            data = await asyncio.get_event_loop().run_in_executor(None, get_windows)
            _enqueue("windows", data)
        except Exception:
            pass


async def _orb_loop():
    """Stream pygame orb frames at ~15 fps when clients are connected."""
    while True:
        await asyncio.sleep(1 / 15)
        if not _clients or not _orb_frame_callback:
            continue
        try:
            frame = _orb_frame_callback()
            if frame:
                _enqueue("orb_frame", {"frame": frame})
        except Exception:
            pass


async def _screen_capture_loop():
    """Stream screen/window frames when capture is active."""
    global _capture_active, _capture_target
    while True:
        await asyncio.sleep(1 / 10)   # 10 fps
        if not _capture_active or not _clients:
            continue
        try:
            frame = await asyncio.get_event_loop().run_in_executor(
                None, _capture_frame, _capture_target, 55
            )
            if frame:
                _enqueue("screen_frame", {
                    "frame": frame,
                    "title": _capture_target or "Desktop",
                })
        except Exception:
            pass


async def _memory_stats_loop():
    """Push memory vault stats every 30 s."""
    while True:
        await asyncio.sleep(30)
        if not _clients:
            continue
        try:
            import memory_vault
            recent = memory_vault.get_recent_memories(limit=10)
            stored = memory_vault.get_memory_count() if hasattr(memory_vault, "get_memory_count") else len(recent)
            semantic = memory_vault.get_semantic_count() if hasattr(memory_vault, "get_semantic_count") else 0
            _enqueue("memory_stats", {
                "stored": stored,
                "semantic": semantic,
                "recent": recent[:5],
            })
        except Exception:
            pass


# ── WebSocket connection handler ──────────────────────────────────────────────

async def _handler(websocket):
    _clients.add(websocket)
    # Full snapshot on connect
    with _lock:
        snap = dict(_shared)
    # Add live window list to snapshot
    try:
        snap["windows"] = await asyncio.get_event_loop().run_in_executor(None, get_windows)
    except Exception:
        snap["windows"] = {"open": [], "minimized": []}

    try:
        await websocket.send(json.dumps({"type": "snapshot", "payload": snap}))
    except Exception:
        pass

    try:
        async for raw in websocket:
            try:
                msg = json.loads(raw)
                await _handle_client_msg(msg)
            except Exception as e:
                print(f"[WS Bridge] msg parse error: {e}")
    except Exception:
        pass
    finally:
        _clients.discard(websocket)


async def _handle_client_msg(msg: dict):
    global _capture_active, _capture_target

    t = msg.get("type")

    if t == "command":
        text = msg.get("text", "").strip()
        if text:
            import main
            # FIX: Route through main utterance processor so Zara speaks and UI updates
            threading.Thread(
                target=main._process_utterance,
                args=(text, None), 
                daemon=True
            ).start()

    elif t == "volume":
        level = int(msg.get("level", 60))
        try:
            from volume_controller import get_volume_controller
            get_volume_controller().set_volume(level / 100.0)
        except Exception:
            pass
        set_volume(level, _shared.get("muted", False))

    elif t == "gender":
        import json
        value = msg.get("value") # 'male' or 'female'
        # Lock in the honorific based on selection
        prefs = {"gender": value, "honorific": "Sir" if value == "male" else "Ma'am"}
        with open("zara_prefs.json", "w", encoding="utf-8") as f:
            json.dump(prefs, f)
        print(f"[System] Identity lock: {prefs['honorific']}")
        set_gender(value, prefs["honorific"])

    elif t == "mode":
        value = msg.get("value", "standard")
        set_mode(value)
        print(f"[System] Dashboard mode switched to: {value}")

    elif t == "bg_detection":
        enabled = bool(msg.get("enabled", True))
        try:
            import local_ears
            local_ears._bg_detector_enabled = enabled
        except Exception:
            pass

    elif t == "capture_screen":
        _capture_active = True
        _capture_target = None
        _enqueue("state", {
            "zaraState": _shared["zaraState"],
            "honorific": _shared["honorific"],
            "gender": _shared["gender"],
            "capturing": True,
            "captureTarget": "Desktop",
        })

    elif t == "capture_window":
        title = msg.get("title", "")
        if title:
            _capture_active = True
            _capture_target = title
            _enqueue("state", {
                "zaraState": _shared["zaraState"],
                "honorific": _shared["honorific"],
                "gender": _shared["gender"],
                "capturing": True,
                "captureTarget": title,
            })
        # Also send one immediate frame
        frame = await asyncio.get_event_loop().run_in_executor(
            None, _capture_frame, title, 60
        )
        if frame:
            _enqueue("screen_frame", {"frame": frame, "title": title})

    elif t == "stop_capture":
        _capture_active = False
        _capture_target = None
        _enqueue("state", {
            "zaraState": _shared["zaraState"],
            "honorific": _shared["honorific"],
            "gender": _shared["gender"],
            "capturing": False,
            "captureTarget": None,
        })

    elif t == "get_windows":
        data = await asyncio.get_event_loop().run_in_executor(None, get_windows)
        _enqueue("windows", data)

    elif t == "window_action":
        hwnd = msg.get("hwnd")
        action = msg.get("action", "focus")
        if hwnd and _WIN32:
            try:
                if action == "focus":
                    win32gui.SetForegroundWindow(hwnd)
                elif action == "minimize":
                    win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
                elif action == "restore":
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    win32gui.SetForegroundWindow(hwnd)
                elif action == "close":
                    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            except Exception as e:
                print(f"[WS Bridge] Window action error: {e}")
        # Refresh window list
        await asyncio.sleep(0.3)
        data = await asyncio.get_event_loop().run_in_executor(None, get_windows)
        _enqueue("windows", data)


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
        if dead:
            _clients.difference_update(dead)


# ── Server entry point ────────────────────────────────────────────────────────

async def _serve():
    async with websockets.serve(_handler, HOST, PORT):
        print(f"[WS Bridge] Listening on ws://{HOST}:{PORT}")
        await asyncio.gather(
            _broadcast_loop(),
            _metrics_loop(),
            _window_sync_loop(),
            _windows_loop(),
            _orb_loop(),
            _screen_capture_loop(),
            _memory_stats_loop(),
        )


def start_bridge():
    """Launch WS bridge in a background daemon thread. Call from main.py."""
    if not _WS:
        print("[WS Bridge] websockets not installed — run: pip install websockets psutil")
        return

    global _loop

    def _run():
        global _loop, _queue
        _load_persisted_prefs()
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        _queue = asyncio.Queue()
        _loop.run_until_complete(_serve())

    t = threading.Thread(target=_run, daemon=True, name="ZaraWSBridge")
    t.start()
    print("[WS Bridge] Started.")
