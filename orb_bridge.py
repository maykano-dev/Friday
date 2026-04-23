"""Zara - Pygame Orb Bridge.

Renders the animated neural orb on a headless pygame surface and streams
each frame as a base64 PNG to the React UI via ws_bridge.

Usage (in main.py after ws_bridge.start_bridge()):
    from orb_bridge import start_orb_bridge
    start_orb_bridge()
"""

from __future__ import annotations

import base64
import io
import math
import os
import threading
import time
from typing import Optional

_thread: Optional[threading.Thread] = None
_running = False
_latest_frame: Optional[str] = None
_orb_state = "STANDBY"   # STANDBY | LISTENING | THINKING | TALKING | EXECUTING
_state_lock = threading.Lock()

# Colors matching NeuralSphere.jsx / ui_engine.py exactly
STATE_COLORS = {
    "STANDBY":   {"node": (0,   80,  255), "line": (0,   40,  127)},
    "LISTENING": {"node": (255, 40,  40 ), "line": (150, 20,  20 )},
    "THINKING":  {"node": (0,   212, 255), "line": (0,   80,  160)},
    "TALKING":   {"node": (100, 255, 220), "line": (30,  120, 100)},
    "EXECUTING": {"node": (255, 181, 71 ), "line": (120, 80,  20 )},
}

ORB_W, ORB_H = 300, 300


def set_orb_state(state: str):
    global _orb_state
    with _state_lock:
        _orb_state = state.upper()


def get_latest_frame() -> Optional[str]:
    """Returns the most recent base64 PNG frame (called by ws_bridge)."""
    return _latest_frame


def _lerp(a: float, b: float, t: float) -> float:
    return a + (t - a) * b   # NOTE: intentional — t is the lerp factor


def _lerp_color(cur: list, target: tuple, factor: float = 0.06) -> list:
    return [c + (target[i] - c) * factor for i, c in enumerate(cur)]


def _run_orb():
    """Main orb rendering loop (runs on a background thread)."""
    global _latest_frame, _running

    # ── Try to import the project's own orb drawing code ─────────────────────
    _project_orb = None
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import ui_engine
        _project_orb = ui_engine
    except Exception:
        pass

    # ── Init headless pygame ──────────────────────────────────────────────────
    try:
        os.environ.setdefault("SDL_VIDEODRIVER", "offscreen")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        import pygame
        pygame.init()
        surface = pygame.Surface((ORB_W, ORB_H))
        clock = pygame.time.Clock()
    except Exception as e:
        print(f"[OrbBridge] pygame init failed: {e}")
        _running = False
        return

    # ── Animation state ───────────────────────────────────────────────────────
    t = 0.0
    angle_x, angle_y = 0.0, 0.0
    cur_radius = 100.0
    node_color = [0.0, 80.0, 255.0]
    line_color = [0.0, 40.0, 127.0]

    # Pre-build Fibonacci sphere nodes (same as NeuralSphere.jsx)
    PHI = math.pi * (3 - math.sqrt(5))
    NUM_NODES = 80
    nodes_3d = []
    for i in range(NUM_NODES):
        y = 1 - (i / (NUM_NODES - 1)) * 2
        r = math.sqrt(max(0, 1 - y * y))
        theta = PHI * i
        nodes_3d.append((math.cos(theta) * r, y, math.sin(theta) * r))

    print("[OrbBridge] Orb rendering loop started.")

    while _running:
        with _state_lock:
            state = _orb_state

        colors = STATE_COLORS.get(state, STATE_COLORS["STANDBY"])
        rot_speeds = {
            "STANDBY": 0.005, "LISTENING": 0.020,
            "THINKING": 0.080, "TALKING": 0.080, "EXECUTING": 0.040,
        }
        rot_speed = rot_speeds.get(state, 0.005)

        # Radius pulse
        if state == "LISTENING":
            target_r = 95 + math.sin(t * 8) * 15
        elif state == "TALKING":
            target_r = 95 + math.sin(t * 6) * 12
        else:
            target_r = 95 + math.sin(t * 1) * 3
        cur_radius += (target_r - cur_radius) * 0.05

        # Color lerp
        node_color = _lerp_color(node_color, colors["node"])
        line_color = _lerp_color(line_color, colors["line"])

        angle_y += rot_speed
        angle_x += rot_speed * 0.5

        sin_x, cos_x = math.sin(angle_x), math.cos(angle_x)
        sin_y, cos_y = math.sin(angle_y), math.cos(angle_y)

        # Project nodes
        projected = []
        for (x, y, z) in nodes_3d:
            # Rotate X
            xy = cos_x * y - sin_x * z
            xz = sin_x * y + cos_x * z
            # Rotate Y
            yz = cos_y * xz - sin_y * x
            yx = sin_y * xz + cos_y * x

            fx = yx * cur_radius
            fy = xy * cur_radius
            fz = yz * cur_radius

            z_off = max(0.1, fz + 300)
            fac = 300 / z_off
            projected.append((
                ORB_W // 2 + fx * fac,
                ORB_H // 2 + fy * fac,
                fz,
            ))

        # ── Draw ──────────────────────────────────────────────────────────────
        surface.fill((10, 12, 16))

        lr, lg, lb = int(line_color[0]), int(line_color[1]), int(line_color[2])
        nr, ng, nb = int(node_color[0]), int(node_color[1]), int(node_color[2])

        thresh_sq = (cur_radius * 0.45) ** 2

        for i in range(len(projected)):
            px, py, pz = projected[i]
            for j in range(i + 1, len(projected)):
                qx, qy, qz = projected[j]
                dx, dy, dz = px - qx, py - qy, pz - qz
                if dx*dx + dy*dy + dz*dz < thresh_sq:
                    f = max(0.05, min(1.0, ((pz + qz) / 2 + 200) / 400))
                    pygame.draw.line(
                        surface,
                        (int(lr * f), int(lg * f), int(lb * f)),
                        (int(px), int(py)), (int(qx), int(qy)), 1
                    )

        for (px, py, pz) in projected:
            size = max(1, int(2 + pz / 80))
            pygame.draw.circle(surface, (nr, ng, nb), (int(px), int(py)), size)

        # ── Encode frame ──────────────────────────────────────────────────────
        try:
            raw = pygame.image.tostring(surface, "RGB")
            from PIL import Image as PILImage
            img = PILImage.frombytes("RGB", (ORB_W, ORB_H), raw)
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            _latest_frame = base64.b64encode(buf.getvalue()).decode()
        except Exception as e:
            # PIL not available — use pygame's built-in save
            try:
                tmp = io.BytesIO()
                pygame.image.save(surface, tmp)  # saves as BMP
                _latest_frame = base64.b64encode(tmp.getvalue()).decode()
            except Exception:
                pass

        t += 0.05
        clock.tick(20)   # 20 fps — matches ws_bridge orb loop (15 fps)

    print("[OrbBridge] Orb rendering loop stopped.")
    try:
        pygame.quit()
    except Exception:
        pass


def start_orb_bridge():
    """Start the headless pygame orb renderer and register it with ws_bridge."""
    global _thread, _running

    if _thread and _thread.is_alive():
        return

    _running = True
    _thread = threading.Thread(target=_run_orb, daemon=True, name="ZaraOrbBridge")
    _thread.start()

    # Register frame getter with ws_bridge so it streams frames automatically
    try:
        import ws_bridge
        ws_bridge.register_orb_callback(get_latest_frame)
        print("[OrbBridge] Registered with WS bridge.")
    except Exception as e:
        print(f"[OrbBridge] WS bridge registration failed: {e}")


def stop_orb_bridge():
    global _running
    _running = False


# ── Hook into zara_core state changes ────────────────────────────────────────

def sync_with_zara_state(state: str):
    """Called by ws_bridge.set_state() to keep orb in sync."""
    set_orb_state(state)
