"""Zara - local execution bridge.

Lets the LLM autonomously trigger file-system operations and sub-scripts
on background threads so the main conversational/UI loops never block.

Strictly stdlib: os, subprocess, json, threading. (shutil is allowed but
not currently needed.)
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import threading
import time
from typing import Any, Dict, Optional

import pyautogui
import state


SCRIPT_TIMEOUT_SECONDS = 120


def is_app_running(app_name: str) -> bool:
    """Check if an application is running using tasklist."""
    import subprocess
    try:
        # Standardize name for Windows tasklist
        if not app_name.endswith(".exe"):
            proc_name = f"{app_name}.exe"
        else:
            proc_name = app_name
            
        output = subprocess.check_output(
            f'tasklist /FI "IMAGENAME eq {proc_name}"', 
            shell=True, 
            text=True
        )
        return proc_name.lower() in output.lower()
    except:
        # Fallback to psutil if available
        try:
            import psutil
            for proc in psutil.process_iter(['name']):
                if app_name.lower() in proc.info['name'].lower():
                    return True
        except:
            pass
        return False


def focus_app(app_name: str) -> bool:
    """Bring an app to the foreground using win32gui for precision."""
    try:
        import win32gui, win32con, ctypes
        
        def find_and_focus(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd).lower()
                if app_name.lower() in title:
                    # Found the window
                    if win32gui.IsIconic(hwnd):
                        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    
                    # Win10/11 focus workaround
                    ctypes.windll.user32.AllowSetForegroundWindow(0xFFFFFFFF)
                    win32gui.SetForegroundWindow(hwnd)
                    return False   # stop enumeration
            return True

        win32gui.EnumWindows(find_and_focus, None)
        return True
    except Exception as e:
        print(f"[Zara Action] focus_app failed for {app_name}: {e}")
        return False


def is_app_installed(app_name: str) -> bool:
    """Check if an application is installed (basic Windows check)."""
    if "spotify" in app_name.lower():
        import os
        app_data = os.getenv("APPDATA")
        local_app_data = os.getenv("LOCALAPPDATA")
        # Common Spotify paths
        paths = [
            f"{app_data}\\Spotify\\Spotify.exe",
            f"{local_app_data}\\Microsoft\\WindowsApps\\Spotify.exe"
        ]
        return any(os.path.exists(p) for p in paths) or os.path.exists("spotify:")
    return True  # Default to True for other apps


class ActionExecutor:
    """Parses LLM-issued action payloads and dispatches them off the main thread."""

    last_run_code_bug: Optional[str] = None
    _recent_actions: Dict[str, float] = {}
    _action_cooldown: float = 1.5  # 1.5 second cooldown between duplicate actions

    @staticmethod
    def _speak_confirmation(message: str) -> None:
        """Best-effort spoken confirmation after a successful action."""
        try:
            import local_voice
            local_voice.speak(message)
        except Exception as e:
            print(f"[Zara Action] confirmation speak failed: {e}")

    def execute_payload(self, json_string: str) -> Optional[threading.Thread]:
        """Parse `json_string` and run the requested action in a daemon thread.

        Returns the spawned (already-started) Thread, or None if the payload
        couldn't be parsed. The main loop never blocks on the result.
        """
        try:
            payload: Dict[str, Any] = json.loads(json_string)
        except (TypeError, ValueError) as e:
            print(f"[Zara Action] invalid JSON payload: {e}")
            return None

        if not isinstance(payload, dict):
            print("[Zara Action] payload must be a JSON object")
            return None

        action = payload.get("action")
        if not isinstance(action, str) or not action:
            print("[Zara Action] payload missing 'action' string")
            return None

        worker = threading.Thread(
            target=self._dispatch,
            args=(action, payload),
            daemon=True,
        )
        worker.start()
        return worker

    # ---- Dispatch ----------------------------------------------------------

    def _dispatch(self, action: str, payload: Dict[str, Any]) -> None:
        import time

        # DEDUPLICATION GUARD: Prevent duplicate actions within cooldown window
        action_key = f"{action}_{json.dumps(payload, sort_keys=True)}"
        now = time.time()

        if action_key in self._recent_actions:
            if now - self._recent_actions[action_key] < self._action_cooldown:
                print(
                    f"[Zara Action] SKIPPING duplicate: {action} (within {self._action_cooldown}s)")
                return

        self._recent_actions[action_key] = now

        # Clean old entries (keep last 10 seconds to prevent memory leak)
        self._recent_actions = {k: v for k, v in self._recent_actions.items()
                                if now - v < 10.0}

        try:
            if action == "create_dir":
                self._create_dir(payload)
            elif action == "write_file":
                self._write_file(payload)
            elif action == "run_script":
                self._run_script(payload)
            elif action == "verified_execute":
                self.verified_execute(payload)
            elif action == "start_app":
                self._start_app(payload)
            elif action == "web_scrape":
                self._web_scrape(payload)
            elif action == "web_research":
                self._web_research(payload)
            elif action == "open_url":
                self._open_url(payload)
            elif action == "web_search":
                self._web_search(payload)
            elif action == "browse_web":
                self._browse_web(payload)
            elif action == "fill_form":
                self._fill_form(payload)
            elif action == "click_element":
                self._click_element(payload)
            elif action == "media_control":
                self.media_control(payload)
            elif action == "volume_control":
                self._volume_control(payload)
            elif action == "ambient_mode":
                import presence_engine
                pe = presence_engine.PresenceEngine()
                sound = payload.get("sound", "rain")
                pe.enter_ambient_mode(sound)
            else:
                print(f"[Zara Action] unknown action: {action!r}")
        except Exception as e:
            print(f"[Zara Action] '{action}' failed: {e}")

    # ---- Action handlers ---------------------------------------------------

    @staticmethod
    def _create_dir(payload: Dict[str, Any]) -> None:
        raw_path = payload.get("path")
        print(f"[Zara Action] create_dir requested: raw_path={raw_path!r}")

        if not isinstance(raw_path, str) or not raw_path.strip():
            print(
                f"[Zara Action] create_dir FAILED: missing or empty 'path' (payload={payload!r})")
            return

        # Normalize: expand ~, resolve to absolute, so relative paths
        # from the LLM don't silently land in Zara's working dir.
        try:
            expanded = os.path.expanduser(os.path.expandvars(raw_path))
            abs_path = os.path.abspath(expanded)
        except Exception as e:
            print(
                f"[Zara Action] create_dir FAILED during path normalization: {type(e).__name__}: {e}")
            return

        dir_name = os.path.basename(abs_path.rstrip("\\/")) or abs_path

        parent = os.path.dirname(abs_path)
        print(f"[Zara Action]   normalized: {abs_path}")
        print(f"[Zara Action]   parent:     {parent}")
        print(
            f"[Zara Action]   parent_exists: {os.path.isdir(parent) if parent else '(no parent)'}")

        if os.path.exists(abs_path):
            if os.path.isdir(abs_path):
                print(
                    f"[Zara Action] create_dir no-op: directory already exists at {abs_path}")
                return
            print(
                f"[Zara Action] create_dir FAILED: path exists but is NOT a directory: {abs_path}")
            return

        try:
            os.makedirs(abs_path, exist_ok=True)
        except PermissionError as e:
            print(f"[Zara Action] create_dir PERMISSION DENIED: {e}")
            return
        except FileExistsError as e:
            print(f"[Zara Action] create_dir race: {e}")
            return
        except OSError as e:
            print(
                f"[Zara Action] create_dir OSError (errno={e.errno}): {e.strerror} -- on {e.filename!r}")
            return
        except Exception as e:
            print(
                f"[Zara Action] create_dir UNEXPECTED {type(e).__name__}: {e}")
            return

        if os.path.isdir(abs_path):
            print(f"[Zara Action] created directory: {abs_path}")
            # Zara's brain handles the confirmation naturally
        else:
            print(
                f"[Zara Action] create_dir completed without raising but target is missing: {abs_path}")

    @staticmethod
    def _write_file(payload: Dict[str, Any]) -> None:
        path = payload.get("path")
        content = payload.get("content", "")
        if not isinstance(path, str) or not path:
            print("[Zara Action] write_file missing 'path'")
            return
        if not isinstance(content, str):
            content = str(content)

        # Ensure the destination directory exists so writes don't fail with
        # FileNotFoundError when the model targets a brand-new folder.
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[Zara Action] wrote file: {path} ({len(content)} chars)")

    @classmethod
    def _run_script(cls, payload: Dict[str, Any]) -> None:
        command = payload.get("command")
        if isinstance(command, list) and command:
            cmd_args: Any = command
            shell = False
        elif isinstance(command, str) and command.strip():
            cmd_args = command
            shell = True
        else:
            print("[Zara Action] run_script missing 'command'")
            return

        try:
            result = subprocess.run(
                cmd_args,
                shell=shell,
                capture_output=True,
                text=True,
                timeout=SCRIPT_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            print(
                f"[Zara Action] script timed out after {SCRIPT_TIMEOUT_SECONDS}s")
            return

        print(f"[Zara Action] script exit={result.returncode}")
        if result.stdout:
            print(f"[Zara Action] stdout: {result.stdout.strip()}")
        if result.stderr:
            print(f"[Zara Action] stderr: {result.stderr.strip()}")

        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip()
            import zara_core
            zara_core.generate_response(
                f"The code failed with this error: {error_msg}. Analyze and provide a corrected <EXECUTE> block."
            )

    @classmethod
    def verified_execute(cls, payload: Dict[str, Any]) -> None:
        attempt = payload.get("attempt", 1)
        if attempt > 3:
            print(f"[Zara Action] verified_execute failed after 3 attempts.")
            import zara_core
            import main
            if main.ui:
                main.ui.set_bg_task("")
            zara_core.generate_response(
                "The code failed 3 times in the sandbox. Tell the user it failed.")
            return

        code = payload.get("code")
        if not isinstance(code, str) or not code:
            print("[Zara Action] verified_execute missing 'code'")
            return

        import memory_vault
        import zara_core
        import main

        if main.ui:
            main.ui.set_bg_task(f"Testing Code (Attempt {attempt}/3)...")

        sandbox_dir = os.path.abspath("zara_sandbox")
        os.makedirs(sandbox_dir, exist_ok=True)
        sandbox_path = os.path.join(sandbox_dir, "_sandbox.py")
        try:
            with open(sandbox_path, "w", encoding="utf-8") as f:
                f.write(code)
            print(
                f"[Zara Action] running code sequentially from {sandbox_path}")
        except Exception as e:
            print(
                f"[Zara Action] verified_execute failed to write sandbox: {e}")
            return

        try:
            result = subprocess.run(
                ["python", sandbox_path],
                capture_output=True,
                text=True,
                timeout=SCRIPT_TIMEOUT_SECONDS,
            )

            if result.returncode == 0:
                print("[Zara Action] verified_execute success!")
                if result.stdout:
                    print(f"[Zara Action] stdout: {result.stdout.strip()}")
                memory_vault.log_coding_task(code, "Success")
                if main.ui:
                    main.ui.set_bg_task("")
            else:
                print(
                    f"[Zara Action] verified_execute failed with exit={result.returncode}")
                error_msg = result.stderr.strip() if result.stderr else "Unknown Error"
                print(f"[Zara Action] output: {error_msg}")
                memory_vault.log_coding_task(code, "Failed")

                prompt = (
                    f"Code execution failed. Error: {error_msg}. Analyze the stack trace, identify the logic error, and provide a corrected <EXECUTE> block. "
                    f"IMPORTANT: You must include '\"attempt\": {attempt + 1}' inside your JSON payload."
                )
                if main.ui:
                    main.ui.set_bg_task("")
                zara_core.generate_response(prompt)

        except subprocess.TimeoutExpired as e:
            print("[Zara Action] sandbox execution timed out")
            error_msg = f"TimeoutExpired after {SCRIPT_TIMEOUT_SECONDS}s."
            memory_vault.log_coding_task(code, "Failed")
            prompt = (
                f"Code execution failed. Error: {error_msg}. Analyze the stack trace, identify the logic error, and provide a corrected <EXECUTE> block. "
                f"IMPORTANT: You must include '\"attempt\": {attempt + 1}' inside your JSON payload."
            )
            if main.ui:
                main.ui.set_bg_task("")
            zara_core.generate_response(prompt)

    @classmethod
    def _start_app(cls, payload: Dict[str, Any]) -> None:
        """Execute a local application with smart music handling."""
        app_name = payload.get("app_name", "").lower()
        search_query = payload.get("query", "")
        action = payload.get("music_action", "")

        print(f"[Zara Action] start_app: app={app_name}, query='{search_query}', action={action}")

        # ── SPOTIFY ─────────────────────────────────────────────
        if "spotify" in app_name:
            if search_query:
                # Use vision-guided search and play
                cls.spotify_search_and_play_with_vision(search_query)
            elif action == "play_recommended":
                cls.spotify_play_recommended()
            else:
                os.startfile("spotify:")
                state.set_media_playing(True)
                print("[Zara Action] Opened Spotify")

        # ── YOUTUBE MUSIC ───────────────────────────────────────
        elif "youtube" in app_name:
            import webbrowser
            if search_query:
                url = f"https://music.youtube.com/search?q={search_query.replace(' ', '+')}"
            else:
                url = "https://music.youtube.com"
            webbrowser.open(url)
            state.set_media_playing(True)
            print(f"[Zara Action] Opened YouTube Music")
        
        # ── APPLE MUSIC ─────────────────────────────────────────
        elif "apple" in app_name:
            if platform.system() == "Windows":
                os.startfile("itms-apps://")
            else:
                subprocess.Popen(["open", "-a", "Music"])
            state.set_media_playing(True)

        # ── OTHER APPS ──────────────────────────────────────────
        elif platform.system() == "Windows":
            try:
                os.startfile(app_name)
            except OSError:
                # Robust fallback for common app names
                app_map = {
                    "chrome": "chrome.exe",
                    "firefox": "firefox.exe",
                    "notepad": "notepad.exe",
                    "calculator": "calc.exe",
                    "edge": "msedge.exe"
                }
                cmd = app_map.get(app_name, app_name)
                try:
                    subprocess.Popen(["cmd", "/c", "start", "", cmd], shell=True)
                except:
                    print(f"[Zara Action] Failed to start {app_name}")
            print(f"[Zara Action] started app: {app_name}")
        else:
            subprocess.Popen(["open" if platform.system() == "Darwin" else "xdg-open", app_name])
            print(f"[Zara Action] started app: {app_name}")

    @classmethod
    def _web_scrape(cls, payload: Dict[str, Any]) -> None:
        """Utilize Playwright to extract DOM context for a given URL."""
        url = payload.get("url")
        if not url:
            return
        import main
        if main.ui:
            main.ui.set_bg_task(f"Initializing Playwright for {url[:20]}...")

        def _scrape_thread():
            try:
                from playwright.sync_api import sync_playwright
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()
                    page.goto(url, wait_until="domcontentloaded",
                              timeout=15000)
                    text = page.locator("body").inner_text()
                    browser.close()
                    import memory_vault
                    memory_vault.index_data(text[:10000], "web_scrape")
                    print(
                        f"[Zara Action] Successfully scraped and indexed {url}")
                    # Zara's brain handles confirmation naturally
            except Exception as e:
                print(f"[Zara Action] web_scrape failed: {e}")
            finally:
                if main.ui:
                    main.ui.set_bg_task("")

        import threading
        threading.Thread(target=_scrape_thread, daemon=True).start()

    @classmethod
    def _web_research(cls, payload: Dict[str, Any]) -> None:
        task_description = payload.get("task_description")
        if not task_description:
            return
        import main
        from ui_engine import WebResultCard

        web_card = None
        if main.ui:
            main.ui.set_subtitle_text(
                "[Zara: Initiating Stealth Web Bridge...]")
            web_card = WebResultCard(
                "https://stealth-bridge.local", status="running")
            main.ui.context_cards.append(web_card)
            main.ui.target_wing_open_ratio = 1.0

        def _research_thread():
            try:
                from playwright.sync_api import sync_playwright
                from playwright_stealth import stealth_sync
                import json
                import zara_core
                import re

                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()
                    stealth_sync(page)

                    if web_card:
                        web_card.content = f"Interrogating core for playwright mapping...\nTask: {task_description}"

                    prompt = f"""You are a playwright-python JSON automation generator.
Task: {task_description}
Generate an array of commands to execute. Only use: "goto", "fill", "click", "wait", "content".
Example format:
[
  {{"cmd": "goto", "url": "https://www.google.com"}},
  {{"cmd": "fill", "selector": "[name=q]", "value": "test"}},
  {{"cmd": "click", "selector": "input[type=submit]"}},
  {{"cmd": "wait", "time": 2000}},
  {{"cmd": "content"}}
]
Return purely valid JSON without markdown tags."""

                    llm_plan_str = zara_core.generate_response(prompt)
                    # aggressive json strip
                    import re
                    json_str = re.sub(r'```json\n|```', '',
                                      llm_plan_str).strip()

                    try:
                        commands = json.loads(json_str)
                    except json.JSONDecodeError:
                        if web_card:
                            web_card.content = f"LLM returned invalid plan:\n{llm_plan_str}"
                            web_card.status = "complete"
                        browser.close()
                        return

                    output_text = "Executed LLM Sequence:\n"

                    for step in commands:
                        cmd = step.get("cmd")
                        if web_card:
                            web_card.content = output_text + f"Running: {cmd}"

                        try:
                            if cmd == "goto":
                                url = step.get("url")
                                if web_card:
                                    web_card.url = url
                                    web_card._fetch_favicon()
                                page.goto(url, timeout=15000)
                            elif cmd == "fill":
                                page.fill(step.get("selector"),
                                          step.get("value"), timeout=5000)
                            elif cmd == "click":
                                page.click(step.get("selector"), timeout=5000)
                            elif cmd == "wait":
                                page.wait_for_timeout(step.get("time", 1000))
                            elif cmd == "content":
                                raw_text = page.locator("body").inner_text()
                                cleaned = re.sub(
                                    r'[\r\n]{3,}', '\n\n', raw_text.strip())
                                output_text += f"\n[Extracted Data Length: {len(cleaned)}]"
                                if web_card:
                                    web_card.content = cleaned
                        except Exception as e:
                            output_text += f"\nError on {cmd}: {e}"

                    browser.close()
                    if web_card:
                        web_card.status = "complete"
                    # Zara's brain handles confirmation naturally

            except Exception as e:
                print(f"[Zara Action] web_research failed: {e}")
                if web_card:
                    web_card.content = f"Fatal Error: {e}"
                    web_card.status = "complete"

        import threading
        threading.Thread(target=_research_thread, daemon=True).start()

    @staticmethod
    def _open_url(payload: Dict[str, Any]) -> None:
        url = payload.get("url")
        if not isinstance(url, str) or not url.strip():
            print(
                f"[Zara Action] open_url FAILED: missing or empty 'url' (payload={payload!r})")
            return

        import webbrowser
        try:
            webbrowser.open(url)
            # Zara's brain handles confirmation naturally
        except Exception as e:
            print(f"[Zara Action] open_url failed: {e}")

    @staticmethod
    def _web_search(payload: Dict[str, Any]) -> None:
        query = payload.get("query")
        if not isinstance(query, str) or not query.strip():
            print(
                f"[Zara Action] web_search FAILED: missing or empty 'query' (payload={payload!r})")
            return

        from urllib.parse import quote_plus
        import webbrowser

        search_url = f"https://www.google.com/search?q={quote_plus(query)}"
        try:
            webbrowser.open(search_url)
            # Zara's brain handles confirmation naturally
        except Exception as e:
            print(f"[Zara Action] web_search failed: {e}")

    @classmethod
    def _browse_web(cls, payload: Dict[str, Any]) -> None:
        """Advanced web browsing with full interaction."""
        url = payload.get("url")
        task = payload.get("task", "")
        session_id = payload.get("session_id", "default")

        if not url and not task:
            print("[Zara Action] browse_web missing url/task")
            return

        def browse_thread():
            try:
                from web_agent import get_web_agent
                agent = get_web_agent()

                if session_id not in agent.sessions:
                    agent.create_session(session_id)

                if url:
                    snapshot = agent.navigate(session_id, url)
                    # Zara's brain handles feedback naturally

                    if task:
                        text = snapshot.text_content[:1000]
                        # Zara's brain filters and speaks results

                elif task:
                    snapshot = agent.search(session_id, task)
                    # Zara's brain handles search feedback naturally
            except Exception as e:
                print(f"[WebAgent] Error: {e}")
                # Zara's brain handles error naturally

        threading.Thread(target=browse_thread, daemon=True).start()

    @classmethod
    def _fill_form(cls, payload: Dict[str, Any]) -> None:
        """Fill a form on the current page."""
        session_id = payload.get("session_id", "default")
        fields = payload.get("fields", {})
        submit = payload.get("submit", False)

        def fill_thread():
            try:
                from web_agent import get_web_agent
                agent = get_web_agent()

                agent.fill_form(session_id, fields, submit=submit)
                # Zara's brain handles confirmation naturally
            except Exception as e:
                print(f"[WebAgent] Fill error: {e}")
                # Zara's brain handles error naturally

        threading.Thread(target=fill_thread, daemon=True).start()

    @classmethod
    def _click_element(cls, payload: Dict[str, Any]) -> None:
        """Click an element on the page."""
        session_id = payload.get("session_id", "default")
        text = payload.get("text")
        selector = payload.get("selector")

        def click_thread():
            try:
                from web_agent import get_web_agent
                agent = get_web_agent()

                agent.click(session_id, text=text, selector=selector)
                # Zara's brain handles confirmation naturally
            except Exception as e:
                print(f"[WebAgent] Click error: {e}")

        threading.Thread(target=click_thread, daemon=True).start()

    @classmethod
    def process_multimodal_input(cls, file_path: str) -> None:
        import os
        import base64
        import main
        from ui_engine import ContextCard
        if not hasattr(main, "ui") or not main.ui:
            return
        ext = os.path.splitext(file_path)[1].lower()
        if ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']:
            main.ui.context_cards.append(ContextCard(
                "TEXT", "[Vision: Processing Visual Input...]"))

            def load_vision():
                try:
                    import pygame
                    surf = pygame.image.load(file_path).convert_alpha()
                    with open(file_path, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode("utf-8")
                    for c in main.ui.context_cards:
                        if c.content == "[Vision: Processing Visual Input...]":
                            c.card_type = "IMAGE"
                            c.content = b64
                            c.surface = surf
                except Exception as e:
                    print(f"Vision error {e}")
            import threading
            threading.Thread(target=load_vision, daemon=True).start()
        else:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                main.ui.context_cards.append(ContextCard("CODE" if ext in [
                                             '.py', '.js', '.ts', '.html', '.css', '.json', '.md'] else "TEXT", content))
                import memory_vault
                memory_vault.index_data(content, "dropped_file")
            except Exception:
                main.ui.context_cards.append(ContextCard(
                    "TEXT", f"Binary File: {os.path.basename(file_path)}"))

    @staticmethod
    def media_control(payload: Dict[str, Any]) -> None:
        command = payload.get("command", "").lower()
        announcements = {
            "volume_up": "Volume increased, Sir.",
            "volume_down": "Volume lowered, Sir.",
            "mute": "System volume toggled, Sir.",
            "play_pause": "Toggled playback, Sir.",
            "next": "Next track, Sir.",
            "previous": "Previous track, Sir.",
            "pause": "Music paused, Sir.",
            "stop": "Music stopped, Sir.",
        }

        try:
            import pyautogui
            import time

            if command == "volume_up" or command == "up":
                from volume_controller import get_volume_controller
                get_volume_controller().volume_up(0.10)
                print("[Zara Action] Volume up (Silent)")

            elif command == "volume_down" or command == "down":
                from volume_controller import get_volume_controller
                get_volume_controller().volume_down(0.10)
                print("[Zara Action] Volume down (Silent)")

            elif command == "mute":
                from volume_controller import get_volume_controller
                get_volume_controller().toggle_mute()
                print("[Zara Action] Mute (Silent)")

            elif command == "play_pause":
                pyautogui.press("playpause")
                # Toggle media playing state
                current = getattr(state.media_playing, 'value', False)
                state.set_media_playing(not current)
                print(f"[Zara Action] Play/Pause (State: {not current})")

            elif command == "pause" or command == "stop":
                pyautogui.press("pause") # or stop, depending on app support
                state.set_media_playing(False)
                print(f"[Zara Action] Media {command}")

            elif command == "next":
                pyautogui.press("nexttrack")
                print("[Zara Action] Next")

            elif command == "previous":
                pyautogui.press("prevtrack")
                print("[Zara Action] Previous")

            # Speak the announcement regardless of how it was called
            msg = announcements.get(command)
            if msg:
                payload["announcement"] = msg
                try:
                    import local_voice
                    local_voice.speak(msg)
                except:
                    pass

        except Exception as e:
            print(f"[Zara Action] Media control failed: {e}")

    @staticmethod
    def _volume_control(payload: Dict[str, Any]) -> None:
        """Control system volume."""
        # Redirect to main media_control for consistency
        ActionExecutor.media_control(payload)

    @classmethod
    def spotify_search_and_play_with_vision(cls, query: str):
        """Use vision to verify and click play."""
        from zara_eyes import get_eyes
        from urllib.parse import quote_plus
        import webbrowser
        import pyautogui
        import time

        # Open Spotify search
        encoded = quote_plus(query)
        spotify_uri = f"spotify:search:{encoded}"
        webbrowser.open(spotify_uri)

        time.sleep(3)

        # Ask vision: "Where is the first song?"
        eyes = get_eyes()
        context = eyes.look_at()

        if context:
            print(f"[Zara] Vision sees: {context.raw_description}")

            # If vision sees search results, try to click
            if "spotify" in context.active_window.lower():
                # Use coordinates based on screen size
                screen_width, screen_height = pyautogui.size()
                click_x = int(screen_width * 0.15)
                click_y = int(screen_height * 0.35)

                pyautogui.doubleClick(click_x, click_y)
                print("[Zara Action] Vision-guided click on first result")
            else:
                # Fallback to standard automation if vision is confused
                cls.spotify_search_and_play(query)
        else:
            cls.spotify_search_and_play(query)

    @classmethod
    def spotify_search_and_play(cls, query: str):
        """Search and play using simple, reliable keystrokes."""
        import pyautogui
        import time
        import os
        
        print(f"[Zara Action] Spotify: searching '{query}'")
        
        # Ensure Spotify is focused
        if not is_app_running("spotify"):
            os.startfile("spotify:")
            time.sleep(4)  # Wait for Spotify to fully load
        else:
            focus_app("spotify")
            time.sleep(1)
        
        # METHOD 1: Use Spotify's built-in keyboard shortcut to open search
        pyautogui.hotkey("ctrl", "k")
        time.sleep(0.8)
        
        # Clear existing text
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.2)
        
        # Type the query using clipboard for Unicode safety
        try:
            import pyperclip
            pyperclip.copy(query)
            time.sleep(0.1)
            pyautogui.hotkey("ctrl", "v")
        except ImportError:
            # Fallback: type char by char slowly
            for char in query:
                try:
                    pyautogui.write(char, interval=0.05)
                except:
                    pass
        time.sleep(0.6)
        
        # Press Enter to search
        pyautogui.press("enter")
        time.sleep(2.0)  # Wait for results
        
        # Tab to first track result and play it
        # Spotify search results: Tabx3 reaches first song in most layouts
        for _ in range(3):
            pyautogui.press("tab")
            time.sleep(0.15)
        pyautogui.press("enter")
        time.sleep(0.5)
        
        state.set_media_playing(True)
        print(f"[Zara Action] Spotify: playback command sent for '{query}'")

    @classmethod
    def spotify_play_recommended(cls):
        """Play user's Discover Weekly or Liked Songs."""
        import pyautogui
        import time
        import os

        if not is_app_running("spotify"):
            os.startfile("spotify:")
            time.sleep(3)
        else:
            focus_app("spotify")
            time.sleep(0.5)

        # Click on "Liked Songs" or press Ctrl+L and type "liked"
        pyautogui.hotkey("ctrl", "l")
        time.sleep(0.3)
        pyautogui.write("liked songs")
        time.sleep(0.5)
        pyautogui.press("enter")
        time.sleep(1)
        pyautogui.press("enter")  # Play

        state.set_media_playing(True)
        print("[Zara Action] Playing Liked Songs")
