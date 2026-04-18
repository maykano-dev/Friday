"""Friday - local execution bridge.

Lets the LLM autonomously trigger file-system operations and sub-scripts
on background threads so the main conversational/UI loops never block.

Strictly stdlib: os, subprocess, json, threading. (shutil is allowed but
not currently needed.)
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from typing import Any, Dict, Optional

import pyautogui


SCRIPT_TIMEOUT_SECONDS = 120


class ActionExecutor:
    """Parses LLM-issued action payloads and dispatches them off the main thread."""

    last_run_code_bug: Optional[str] = None

    @staticmethod
    def _speak_confirmation(message: str) -> None:
        """Best-effort spoken confirmation after a successful action."""
        try:
            import local_voice
            local_voice.speak(message)
        except Exception as e:
            print(f"[Friday Action] confirmation speak failed: {e}")

    def execute_payload(self, json_string: str) -> Optional[threading.Thread]:
        """Parse `json_string` and run the requested action in a daemon thread.

        Returns the spawned (already-started) Thread, or None if the payload
        couldn't be parsed. The main loop never blocks on the result.
        """
        try:
            payload: Dict[str, Any] = json.loads(json_string)
        except (TypeError, ValueError) as e:
            print(f"[Friday Action] invalid JSON payload: {e}")
            return None

        if not isinstance(payload, dict):
            print("[Friday Action] payload must be a JSON object")
            return None

        action = payload.get("action")
        if not isinstance(action, str) or not action:
            print("[Friday Action] payload missing 'action' string")
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
            elif action == "media_control":
                self.media_control(payload)
            elif action == "ambient_mode":
                import presence_engine
                pe = presence_engine.PresenceEngine()
                sound = payload.get("sound", "rain")
                pe.enter_ambient_mode(sound)
            else:
                print(f"[Friday Action] unknown action: {action!r}")
        except Exception as e:
            print(f"[Friday Action] '{action}' failed: {e}")

    # ---- Action handlers ---------------------------------------------------

    @staticmethod
    def _create_dir(payload: Dict[str, Any]) -> None:
        raw_path = payload.get("path")
        print(f"[Friday Action] create_dir requested: raw_path={raw_path!r}")

        if not isinstance(raw_path, str) or not raw_path.strip():
            print(
                f"[Friday Action] create_dir FAILED: missing or empty 'path' (payload={payload!r})")
            ActionExecutor._speak_confirmation(
                "I encountered an error while creating that directory.")
            return

        # Normalize: expand ~, resolve to absolute, so relative paths
        # from the LLM don't silently land in Friday's working dir.
        try:
            expanded = os.path.expanduser(os.path.expandvars(raw_path))
            abs_path = os.path.abspath(expanded)
        except Exception as e:
            print(
                f"[Friday Action] create_dir FAILED during path normalization: {type(e).__name__}: {e}")
            ActionExecutor._speak_confirmation(
                "I encountered an error while creating that directory.")
            return

        dir_name = os.path.basename(abs_path.rstrip("\\/")) or abs_path

        parent = os.path.dirname(abs_path)
        print(f"[Friday Action]   normalized: {abs_path}")
        print(f"[Friday Action]   parent:     {parent}")
        print(
            f"[Friday Action]   parent_exists: {os.path.isdir(parent) if parent else '(no parent)'}")

        if os.path.exists(abs_path):
            if os.path.isdir(abs_path):
                print(
                    f"[Friday Action] create_dir no-op: directory already exists at {abs_path}")
                ActionExecutor._speak_confirmation(
                    f"The directory {dir_name} already exists.")
                return
            print(
                f"[Friday Action] create_dir FAILED: path exists but is NOT a directory: {abs_path}")
            ActionExecutor._speak_confirmation(
                "I encountered an error while creating that directory.")
            return

        try:
            os.makedirs(abs_path, exist_ok=True)
        except PermissionError as e:
            print(f"[Friday Action] create_dir PERMISSION DENIED: {e}")
            ActionExecutor._speak_confirmation(
                "I encountered an error while creating that directory.")
            return
        except FileExistsError as e:
            print(f"[Friday Action] create_dir race: {e}")
            ActionExecutor._speak_confirmation(
                "I encountered an error while creating that directory.")
            return
        except OSError as e:
            print(
                f"[Friday Action] create_dir OSError (errno={e.errno}): {e.strerror} -- on {e.filename!r}")
            ActionExecutor._speak_confirmation(
                "I encountered an error while creating that directory.")
            return
        except Exception as e:
            print(
                f"[Friday Action] create_dir UNEXPECTED {type(e).__name__}: {e}")
            ActionExecutor._speak_confirmation(
                "I encountered an error while creating that directory.")
            return

        if os.path.isdir(abs_path):
            print(f"[Friday Action] created directory: {abs_path}")
            ActionExecutor._speak_confirmation(
                f"The directory {dir_name} has been created successfully."
            )
        else:
            print(
                f"[Friday Action] create_dir completed without raising but target is missing: {abs_path}")
            ActionExecutor._speak_confirmation(
                "I encountered an error while creating that directory.")

    @staticmethod
    def _write_file(payload: Dict[str, Any]) -> None:
        path = payload.get("path")
        content = payload.get("content", "")
        if not isinstance(path, str) or not path:
            print("[Friday Action] write_file missing 'path'")
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
        print(f"[Friday Action] wrote file: {path} ({len(content)} chars)")
        ActionExecutor._speak_confirmation("File written.")

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
            print("[Friday Action] run_script missing 'command'")
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
                f"[Friday Action] script timed out after {SCRIPT_TIMEOUT_SECONDS}s")
            return

        print(f"[Friday Action] script exit={result.returncode}")
        if result.stdout:
            print(f"[Friday Action] stdout: {result.stdout.strip()}")
        if result.stderr:
            print(f"[Friday Action] stderr: {result.stderr.strip()}")

        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip()
            import friday_core
            friday_core.generate_response(
                f"The code failed with this error: {error_msg}. Analyze and provide a corrected <EXECUTE> block."
            )

    @classmethod
    def verified_execute(cls, payload: Dict[str, Any]) -> None:
        attempt = payload.get("attempt", 1)
        if attempt > 3:
            print(f"[Friday Action] verified_execute failed after 3 attempts.")
            import friday_core
            import main
            if main.ui:
                main.ui.set_bg_task("")
            friday_core.generate_response(
                "The code failed 3 times in the sandbox. Tell the user it failed.")
            return

        code = payload.get("code")
        if not isinstance(code, str) or not code:
            print("[Friday Action] verified_execute missing 'code'")
            return

        import memory_vault
        import friday_core
        import main

        if main.ui:
            main.ui.set_bg_task(f"Testing Code (Attempt {attempt}/3)...")

        sandbox_dir = os.path.abspath("friday_sandbox")
        os.makedirs(sandbox_dir, exist_ok=True)
        sandbox_path = os.path.join(sandbox_dir, "_sandbox.py")
        try:
            with open(sandbox_path, "w", encoding="utf-8") as f:
                f.write(code)
            print(
                f"[Friday Action] running code sequentially from {sandbox_path}")
        except Exception as e:
            print(
                f"[Friday Action] verified_execute failed to write sandbox: {e}")
            return

        try:
            result = subprocess.run(
                ["python", sandbox_path],
                capture_output=True,
                text=True,
                timeout=SCRIPT_TIMEOUT_SECONDS,
            )

            if result.returncode == 0:
                print("[Friday Action] verified_execute success!")
                if result.stdout:
                    print(f"[Friday Action] stdout: {result.stdout.strip()}")
                memory_vault.log_coding_task(code, "Success")
                if main.ui:
                    main.ui.set_bg_task("")
            else:
                print(
                    f"[Friday Action] verified_execute failed with exit={result.returncode}")
                error_msg = result.stderr.strip() if result.stderr else "Unknown Error"
                print(f"[Friday Action] output: {error_msg}")
                memory_vault.log_coding_task(code, "Failed")

                prompt = (
                    f"Code execution failed. Error: {error_msg}. Analyze the stack trace, identify the logic error, and provide a corrected <EXECUTE> block. "
                    f"IMPORTANT: You must include '\"attempt\": {attempt + 1}' inside your JSON payload."
                )
                if main.ui:
                    main.ui.set_bg_task("")
                friday_core.generate_response(prompt)

        except subprocess.TimeoutExpired as e:
            print("[Friday Action] sandbox execution timed out")
            error_msg = f"TimeoutExpired after {SCRIPT_TIMEOUT_SECONDS}s."
            memory_vault.log_coding_task(code, "Failed")
            prompt = (
                f"Code execution failed. Error: {error_msg}. Analyze the stack trace, identify the logic error, and provide a corrected <EXECUTE> block. "
                f"IMPORTANT: You must include '\"attempt\": {attempt + 1}' inside your JSON payload."
            )
            if main.ui:
                main.ui.set_bg_task("")
            friday_core.generate_response(prompt)

    @classmethod
    def _start_app(cls, payload: Dict[str, Any]) -> None:
        """Execute a local application or script using OS routing."""
        app_name = payload.get("app_name")
        if not app_name:
            return
        try:
            import platform
            import subprocess
            import os
            if platform.system() == "Windows":
                os.startfile(app_name)
            else:
                subprocess.Popen(["open" if platform.system()
                                 == "Darwin" else "xdg-open", app_name])
            print(f"[Friday Action] started app: {app_name}")
            cls._speak_confirmation("Application launched.")
        except Exception as e:
            print(f"[Friday Action] start_app failed: {e}")

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
                        f"[Friday Action] Successfully scraped and indexed {url}")
                    cls._speak_confirmation("Web scrape complete.")
            except Exception as e:
                print(f"[Friday Action] web_scrape failed: {e}")
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
                "[Friday: Initiating Stealth Web Bridge...]")
            web_card = WebResultCard(
                "https://stealth-bridge.local", status="running")
            main.ui.context_cards.append(web_card)
            main.ui.target_wing_open_ratio = 1.0

        def _research_thread():
            try:
                from playwright.sync_api import sync_playwright
                from playwright_stealth import stealth_sync
                import json
                import friday_core
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

                    llm_plan_str = friday_core.generate_response(prompt)
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
                    cls._speak_confirmation("Research complete.")

            except Exception as e:
                print(f"[Friday Action] web_research failed: {e}")
                if web_card:
                    web_card.content = f"Fatal Error: {e}"
                    web_card.status = "complete"

        import threading
        threading.Thread(target=_research_thread, daemon=True).start()

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
        import local_voice  # Local import to avoid circular issues

        if command == "play_pause":
            pyautogui.press("playpause")
            local_voice.speak("Toggled playback.")
        elif command == "next":
            pyautogui.press("nexttrack")
            local_voice.speak("Skipping to the next track.")
        elif command == "previous":
            pyautogui.press("prevtrack")
            local_voice.speak("Going back.")
        elif command == "volume_up":
            for _ in range(5):
                pyautogui.press("volumeup")
            local_voice.speak("Volume increased.")
        elif command == "volume_down":
            for _ in range(5):
                pyautogui.press("volumedown")
            local_voice.speak("Volume decreased.")
        elif command == "mute":
            pyautogui.press("volumemute")
            local_voice.speak("Audio muted.")
