"""
main.py PATCH — add these two lines right after ws_bridge.start_bridge() in run_Zara():

    # ── 1.2. Start Pygame Orb Bridge (streams orb frames to React UI) ───────
    try:
        from orb_bridge import start_orb_bridge, sync_with_zara_state
        start_orb_bridge()
        print("[System] Orb bridge started — React UI will receive live orb frames.")
    except Exception as e:
        print(f"[System] Orb bridge skipped: {e}")

Also patch ws_bridge.set_state() to keep the orb in sync.
Add to ws_bridge.py set_state() function body, after the _enqueue call:

    # Sync orb state
    try:
        from orb_bridge import sync_with_zara_state
        sync_with_zara_state(state)
    except Exception:
        pass

─────────────────────────────────────────────────────────────────────────────
If you want to apply these patches automatically, run this script:
python apply_main_patch.py
─────────────────────────────────────────────────────────────────────────────
"""

import re
import os

MAIN_PATH = os.path.join(os.path.dirname(__file__), "main.py")
WS_BRIDGE_PATH = os.path.join(os.path.dirname(__file__), "ws_bridge.py")

ORB_PATCH = '''
    # ── 1.2. Start Pygame Orb Bridge (streams orb frames to React UI) ───────
    try:
        from orb_bridge import start_orb_bridge
        start_orb_bridge()
        print("[System] Orb bridge started — React UI will receive live orb frames.")
    except Exception as e:
        print(f"[System] Orb bridge skipped: {e}")
'''

WS_STATE_PATCH = '''    # Sync orb state
    try:
        from orb_bridge import sync_with_zara_state
        sync_with_zara_state(_shared["zaraState"])
    except Exception:
        pass
'''


def patch_main():
    if not os.path.exists(MAIN_PATH):
        print(f"[Patch] main.py not found at {MAIN_PATH}")
        return

    with open(MAIN_PATH, "r", encoding="utf-8") as f:
        src = f.read()

    if "start_orb_bridge" in src:
        print("[Patch] main.py already has orb bridge — skipping.")
        return

    # Insert orb patch right after ws_bridge.start_bridge()
    target = "ws_bridge.start_bridge()"
    if target not in src:
        print("[Patch] Could not find insertion point in main.py")
        return

    src = src.replace(target, target + "\n" + ORB_PATCH, 1)

    with open(MAIN_PATH, "w", encoding="utf-8") as f:
        f.write(src)
    print("[Patch] main.py patched successfully ✓")


def patch_ws_bridge():
    if not os.path.exists(WS_BRIDGE_PATH):
        print(f"[Patch] ws_bridge.py not found at {WS_BRIDGE_PATH}")
        return

    with open(WS_BRIDGE_PATH, "r", encoding="utf-8") as f:
        src = f.read()

    if "sync_with_zara_state" in src:
        print("[Patch] ws_bridge.py already syncs orb state — skipping.")
        return

    # Insert after the _enqueue call in set_state()
    target = '_enqueue("state", {'
    if target not in src:
        print("[Patch] Could not find insertion point in ws_bridge.py")
        return

    # Find the end of the _enqueue call block in set_state
    idx = src.find(target)
    # Find the closing }) of this enqueue call
    end_idx = src.find("})", idx)
    if end_idx == -1:
        print("[Patch] Could not locate end of _enqueue call")
        return

    insert_pos = end_idx + 2   # right after })
    src = src[:insert_pos] + "\n" + WS_STATE_PATCH + src[insert_pos:]

    with open(WS_BRIDGE_PATH, "w", encoding="utf-8") as f:
        f.write(src)
    print("[Patch] ws_bridge.py patched successfully ✓")


if __name__ == "__main__":
    patch_main()
    patch_ws_bridge()
    print("\n[Patch] Done. Restart Zara (python main.py) to apply changes.")
