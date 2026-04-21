"""Zara PC Controller — Full mouse, keyboard, screen navigation, and browser control.

This is the missing "hands" module. Zara uses this to actually DO things
on the computer: click buttons, type text, read screens, navigate browsers,
fill forms, take screenshots, and coordinate with the vision system.

Requirements:
    pip install pyperclip pytesseract pyautogui pywin32
    Also install Tesseract OCR: https://github.com/UB-Mannheim/tesseract/wiki
    Set TESSDATA_PREFIX or add Tesseract to PATH.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
import threading
from typing import Optional, Tuple, List, Dict, Any

import pyautogui

# Safety: move mouse to top-left corner to abort any running automation
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05  # 50ms between actions — fast but reliable

# Try to import optional OCR
try:
    import pytesseract
    # Common Windows install path — adjust if needed
    if os.path.exists(r"C:\Program Files\Tesseract-OCR\tesseract.exe"):
        pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    print("[PCController] pytesseract not installed — screen reading disabled. Run: pip install pytesseract")

# Try pyperclip for Unicode-safe clipboard typing
try:
    import pyperclip
    CLIPBOARD_AVAILABLE = True
except ImportError:
    CLIPBOARD_AVAILABLE = False
    print("[PCController] pyperclip not installed — clipboard paste disabled. Run: pip install pyperclip")


class PCController:
    """
    Full PC control for Zara.

    Zara can:
    - Move the mouse and click anywhere on screen
    - Type text (Unicode-safe via clipboard)
    - Press keys and hotkey combinations
    - Read text from any part of the screen (OCR)
    - Find specific text on screen and click it
    - Navigate browsers across multiple pages
    - Fill in forms (web and desktop)
    - Take and save screenshots
    - Open, switch, and close windows/apps
    """

    def __init__(self):
        self.screen_width, self.screen_height = pyautogui.size()
        self._browser_wait_default = 1.5  # seconds to wait after navigation

    # ════════════════════════════════════════════════════════
    #   MOUSE CONTROL
    # ════════════════════════════════════════════════════════

    def move_to(self, x: int, y: int, duration: float = 0.35) -> None:
        """Smoothly move mouse to screen coordinates."""
        pyautogui.moveTo(x, y, duration=duration)

    def click(self, x: int = None, y: int = None,
              button: str = "left", clicks: int = 1) -> None:
        """Click at (x, y) or at current position."""
        if x is not None and y is not None:
            pyautogui.click(x, y, button=button, clicks=clicks, interval=0.08)
        else:
            pyautogui.click(button=button, clicks=clicks)

    def double_click(self, x: int = None, y: int = None) -> None:
        """Double-click at position."""
        if x is not None and y is not None:
            pyautogui.doubleClick(x, y)
        else:
            pyautogui.doubleClick()

    def right_click(self, x: int = None, y: int = None) -> None:
        """Right-click at position."""
        if x is not None and y is not None:
            pyautogui.rightClick(x, y)
        else:
            pyautogui.rightClick()

    def drag_to(self, x1: int, y1: int, x2: int, y2: int,
                duration: float = 0.5) -> None:
        """Click and drag from one point to another."""
        pyautogui.moveTo(x1, y1, duration=0.3)
        pyautogui.dragTo(x2, y2, duration=duration, button="left")

    def scroll(self, amount: int, x: int = None, y: int = None) -> None:
        """
        Scroll at position.
        Positive = scroll up, Negative = scroll down.
        """
        if x is not None and y is not None:
            pyautogui.moveTo(x, y, duration=0.2)
        pyautogui.scroll(amount)

    def scroll_to_bottom(self) -> None:
        """Scroll to the very bottom of the page/document."""
        pyautogui.hotkey("ctrl", "end")

    def scroll_to_top(self) -> None:
        """Scroll to the very top of the page/document."""
        pyautogui.hotkey("ctrl", "home")

    def get_mouse_position(self) -> Tuple[int, int]:
        """Return current mouse coordinates."""
        pos = pyautogui.position()
        return (pos.x, pos.y)

    # ════════════════════════════════════════════════════════
    #   KEYBOARD CONTROL
    # ════════════════════════════════════════════════════════

    def type_text(self, text: str, interval: float = 0.03) -> None:
        """
        Type text. Uses clipboard for Unicode safety (handles special chars,
        accented names, emoji). Falls back to pyautogui.write for ASCII.
        """
        if CLIPBOARD_AVAILABLE:
            # Clipboard paste is instant and handles all Unicode
            pyperclip.copy(str(text))
            time.sleep(0.1)
            pyautogui.hotkey("ctrl", "v")
        else:
            # ASCII-only fallback
            safe_text = "".join(c for c in str(text) if ord(c) < 128)
            pyautogui.write(safe_text, interval=interval)

    def type_text_slow(self, text: str, interval: float = 0.06) -> None:
        """Type text slowly — use for apps that miss keystrokes at fast speeds."""
        for char in str(text):
            try:
                pyautogui.write(char, interval=interval)
            except Exception:
                # Skip unprintable characters
                pass

    def press_key(self, key: str) -> None:
        """Press a single key by name (e.g. 'enter', 'tab', 'escape', 'f5')."""
        pyautogui.press(key)

    def hotkey(self, *keys: str) -> None:
        """
        Press a key combination simultaneously.
        Example: hotkey("ctrl", "c")  hotkey("ctrl", "shift", "t")
        """
        pyautogui.hotkey(*keys)

    def hold_and_press(self, hold_key: str, press_key: str) -> None:
        """Hold one key while pressing another."""
        pyautogui.keyDown(hold_key)
        time.sleep(0.05)
        pyautogui.press(press_key)
        pyautogui.keyUp(hold_key)

    # ════════════════════════════════════════════════════════
    #   CLIPBOARD
    # ════════════════════════════════════════════════════════

    def copy(self) -> str:
        """Copy current selection and return clipboard text."""
        if CLIPBOARD_AVAILABLE:
            pyperclip.copy("")
        pyautogui.hotkey("ctrl", "c")
        time.sleep(0.25)
        if CLIPBOARD_AVAILABLE:
            return pyperclip.paste()
        return ""

    def paste(self, text: str = None) -> None:
        """Paste from clipboard, or paste given text."""
        if text is not None and CLIPBOARD_AVAILABLE:
            pyperclip.copy(str(text))
            time.sleep(0.1)
        pyautogui.hotkey("ctrl", "v")

    def select_all(self) -> None:
        pyautogui.hotkey("ctrl", "a")

    def clear_field(self) -> None:
        """Clear the current input field."""
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.05)
        pyautogui.press("delete")

    # ════════════════════════════════════════════════════════
    #   SCREEN READING (OCR)
    # ════════════════════════════════════════════════════════

    def read_screen_text(self, region: Tuple[int, int, int, int] = None) -> str:
        """
        Read all text currently visible on screen using OCR.
        region: (x, y, width, height) — if None, reads entire screen.
        """
        if not OCR_AVAILABLE:
            return ""
        try:
            screenshot = pyautogui.screenshot(region=region)
            text = pytesseract.image_to_string(screenshot, config="--psm 6")
            return text.strip()
        except Exception as e:
            print(f"[PCController] OCR failed: {e}")
            return ""

    def find_text_on_screen(self, text: str,
                             region: Tuple[int, int, int, int] = None,
                             confidence: float = 0.7) -> Optional[Tuple[int, int]]:
        """
        Find text on screen using OCR and return (x, y) center coordinates.
        Returns None if text not found.
        """
        if not OCR_AVAILABLE:
            print("[PCController] OCR not available — cannot find text on screen")
            return None
        try:
            screenshot = pyautogui.screenshot(region=region)
            data = pytesseract.image_to_data(
                screenshot, output_type=pytesseract.Output.DICT, config="--psm 6"
            )
            search = text.lower()
            # Scan word by word
            for i, word in enumerate(data["text"]):
                if not word.strip():
                    continue
                if search in word.lower() or word.lower() in search:
                    conf = int(data["conf"][i])
                    if conf > confidence * 100:
                        x = data["left"][i] + data["width"][i] // 2
                        y = data["top"][i] + data["height"][i] // 2
                        # If region offset, adjust coordinates
                        if region:
                            x += region[0]
                            y += region[1]
                        return (x, y)

            # Try multi-word phrase scan
            full_text = " ".join(data["text"]).lower()
            if search in full_text:
                # Approximate: find block containing the phrase
                idx = full_text.find(search)
                word_count = len(full_text[:idx].split())
                if word_count < len(data["text"]):
                    x = data["left"][word_count] + data["width"][word_count] // 2
                    y = data["top"][word_count] + data["height"][word_count] // 2
                    if region:
                        x += region[0]
                        y += region[1]
                    return (x, y)

        except Exception as e:
            print(f"[PCController] find_text_on_screen failed: {e}")
        return None

    def click_text_on_screen(self, text: str) -> bool:
        """Find text on screen and click it. Returns True if found and clicked."""
        coords = self.find_text_on_screen(text)
        if coords:
            self.click(coords[0], coords[1])
            print(f"[PCController] Clicked '{text}' at {coords}")
            return True
        print(f"[PCController] Text '{text}' not found on screen")
        return False

    def wait_for_text(self, text: str, timeout: float = 15.0,
                      interval: float = 0.5) -> bool:
        """Wait until text appears on screen. Returns True if found."""
        start = time.time()
        while time.time() - start < timeout:
            if self.find_text_on_screen(text):
                return True
            time.sleep(interval)
        return False

    def find_image_on_screen(self, image_path: str,
                              confidence: float = 0.8) -> Optional[Tuple[int, int]]:
        """Find a template image on screen and return its center coordinates."""
        try:
            location = pyautogui.locateOnScreen(image_path, confidence=confidence)
            if location:
                center = pyautogui.center(location)
                return (int(center.x), int(center.y))
        except Exception as e:
            print(f"[PCController] find_image failed: {e}")
        return None

    def click_image_on_screen(self, image_path: str,
                               confidence: float = 0.8) -> bool:
        """Find image on screen and click it."""
        coords = self.find_image_on_screen(image_path, confidence)
        if coords:
            self.click(coords[0], coords[1])
            return True
        return False

    # ════════════════════════════════════════════════════════
    #   SCREENSHOT
    # ════════════════════════════════════════════════════════

    def take_screenshot(self, save_path: str = None) -> str:
        """Take a screenshot and save it. Returns the saved file path."""
        import datetime
        screenshot = pyautogui.screenshot()
        if not save_path:
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            filename = f"zara_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            save_path = os.path.join(desktop, filename)
        screenshot.save(save_path)
        print(f"[PCController] Screenshot saved: {save_path}")
        return save_path

    # ════════════════════════════════════════════════════════
    #   WINDOW MANAGEMENT
    # ════════════════════════════════════════════════════════

    def get_active_window_title(self) -> str:
        """Return the title of the currently focused window."""
        try:
            import win32gui
            return win32gui.GetWindowText(win32gui.GetForegroundWindow())
        except Exception:
            return ""

    def focus_window(self, partial_title: str) -> bool:
        """Bring a window with a matching title to the foreground."""
        try:
            import win32gui, win32con
            result = {"hwnd": None}

            def callback(hwnd, _):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd).lower()
                    if partial_title.lower() in title:
                        result["hwnd"] = hwnd
                        return False
                return True

            win32gui.EnumWindows(callback, None)
            if result["hwnd"]:
                hwnd = result["hwnd"]
                if win32gui.IsIconic(hwnd):
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    time.sleep(0.2)
                try:
                    import ctypes
                    ctypes.windll.user32.AllowSetForegroundWindow(0xFFFFFFFF)
                    win32gui.SetForegroundWindow(hwnd)
                    time.sleep(0.3)
                    return True
                except Exception:
                    pass
        except Exception as e:
            print(f"[PCController] focus_window failed: {e}")
        return False

    def minimize_window(self) -> None:
        pyautogui.hotkey("win", "down")
        pyautogui.hotkey("win", "down")

    def maximize_window(self) -> None:
        pyautogui.hotkey("win", "up")

    def snap_left(self) -> None:
        pyautogui.hotkey("win", "left")

    def snap_right(self) -> None:
        pyautogui.hotkey("win", "right")

    def close_window(self) -> None:
        pyautogui.hotkey("alt", "f4")

    # ════════════════════════════════════════════════════════
    #   APPLICATION LAUNCHING
    # ════════════════════════════════════════════════════════

    def open_app(self, app_name: str) -> bool:
        """Launch an application by name."""
        app_map = {
            "chrome": "chrome",
            "google chrome": "chrome",
            "firefox": "firefox",
            "edge": "msedge",
            "microsoft edge": "msedge",
            "notepad": "notepad",
            "calculator": "calc",
            "explorer": "explorer",
            "file explorer": "explorer",
            "vs code": "code",
            "vscode": "code",
            "visual studio code": "code",
            "discord": "discord",
            "spotify": "spotify",
            "terminal": "cmd",
            "command prompt": "cmd",
            "cmd": "cmd",
            "powershell": "powershell",
            "task manager": "taskmgr",
            "settings": "ms-settings:",
            "paint": "mspaint",
            "word": "winword",
            "excel": "excel",
            "powerpoint": "powerpnt",
            "outlook": "outlook",
            "teams": "teams",
            "zoom": "zoom",
            "slack": "slack",
        }
        cmd = app_map.get(app_name.lower().strip(), app_name)
        try:
            os.startfile(cmd)
            return True
        except Exception:
            try:
                subprocess.Popen(cmd, shell=True)
                return True
            except Exception as e:
                print(f"[PCController] open_app '{app_name}' failed: {e}")
                return False

    def kill_app(self, process_name: str) -> bool:
        """Force-close a running process."""
        if not process_name.endswith(".exe"):
            process_name += ".exe"
        try:
            result = subprocess.run(
                ["taskkill", "/f", "/im", process_name],
                capture_output=True, text=True
            )
            return result.returncode == 0
        except Exception as e:
            print(f"[PCController] kill_app failed: {e}")
            return False

    # ════════════════════════════════════════════════════════
    #   BROWSER CONTROL
    # ════════════════════════════════════════════════════════

    def navigate_to_url(self, url: str, wait: float = 1.5) -> None:
        """Navigate the current browser tab to a URL."""
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        pyautogui.hotkey("ctrl", "l")      # Focus address bar
        time.sleep(0.25)
        pyautogui.hotkey("ctrl", "a")      # Select existing URL
        time.sleep(0.1)
        self.type_text(url)                # Paste new URL
        time.sleep(0.1)
        pyautogui.press("enter")
        time.sleep(wait)

    def open_new_tab(self, url: str = None) -> None:
        """Open a new browser tab, optionally navigating to a URL."""
        pyautogui.hotkey("ctrl", "t")
        time.sleep(0.4)
        if url:
            self.navigate_to_url(url)

    def close_tab(self) -> None:
        pyautogui.hotkey("ctrl", "w")

    def switch_tab_next(self) -> None:
        pyautogui.hotkey("ctrl", "tab")

    def switch_tab_prev(self) -> None:
        pyautogui.hotkey("ctrl", "shift", "tab")

    def go_back(self) -> None:
        pyautogui.hotkey("alt", "left")

    def go_forward(self) -> None:
        pyautogui.hotkey("alt", "right")

    def refresh(self) -> None:
        pyautogui.hotkey("ctrl", "r")

    def browser_search(self, query: str, new_tab: bool = True) -> None:
        """Open Google search in browser."""
        url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
        if new_tab:
            self.open_new_tab(url)
        else:
            self.navigate_to_url(url)

    def browser_find_on_page(self, text: str) -> None:
        """Use browser's built-in Ctrl+F to find text on page."""
        pyautogui.hotkey("ctrl", "f")
        time.sleep(0.3)
        self.type_text(text)
        time.sleep(0.3)
        pyautogui.press("escape")

    def get_current_url(self) -> str:
        """Get the URL currently in the browser address bar."""
        pyautogui.hotkey("ctrl", "l")
        time.sleep(0.2)
        url = self.copy()
        pyautogui.press("escape")
        return url.strip()

    def read_current_page(self, wait: float = 1.0) -> str:
        """Read the text content of the current browser page via OCR."""
        time.sleep(wait)
        return self.read_screen_text()

    # ════════════════════════════════════════════════════════
    #   MULTI-PAGE BROWSER RESEARCH
    # ════════════════════════════════════════════════════════

    def research_topic(self, query: str, num_results: int = 3) -> str:
        """
        Search Google, open top results, read each page, return combined summary.
        """
        results = []

        # Open Google search
        self.browser_search(query, new_tab=True)
        time.sleep(2.0)

        # Read search results page
        search_text = self.read_screen_text()
        results.append(f"=== SEARCH RESULTS ===\n{search_text[:1000]}")

        # Try to open and read first few result links
        for i in range(num_results):
            try:
                # Find result links (heuristic: look for blue link text)
                # In a real implementation, use vision model to find link coords
                # For now, use Tab navigation to reach links
                pyautogui.hotkey("ctrl", "l")
                time.sleep(0.2)
                pyautogui.press("escape")

                # Tab to i-th result link
                for _ in range(7 + i * 2):
                    pyautogui.press("tab")
                    time.sleep(0.05)
                pyautogui.press("enter")
                time.sleep(2.5)

                page_text = self.read_screen_text()
                results.append(f"=== RESULT {i+1} ===\n{page_text[:800]}")

                self.go_back()
                time.sleep(1.0)
            except Exception as e:
                print(f"[PCController] research result {i+1} failed: {e}")
                break

        return "\n\n".join(results)

    def browse_and_extract(self, url: str, wait: float = 2.0) -> str:
        """Navigate to a URL and return the page text."""
        self.navigate_to_url(url, wait=wait)
        return self.read_current_page()

    def multi_page_browse(self, urls: List[str]) -> List[str]:
        """Visit multiple URLs and return their text content."""
        page_texts = []
        for url in urls:
            try:
                self.open_new_tab(url)
                time.sleep(2.0)
                text = self.read_current_page()
                page_texts.append(text)
                self.close_tab()
                time.sleep(0.5)
            except Exception as e:
                print(f"[PCController] multi_page_browse error on {url}: {e}")
                page_texts.append("")
        return page_texts

    # ════════════════════════════════════════════════════════
    #   FORM FILLING
    # ════════════════════════════════════════════════════════

    def fill_form_by_label(self, field_label: str, value: str,
                            click_offset_x: int = 200) -> bool:
        """
        Find a form label on screen, click the input field next to it,
        and type the value.
        click_offset_x: pixels to the right of the label to click the input
        """
        coords = self.find_text_on_screen(field_label)
        if coords:
            # Click the input field (typically to the right of the label)
            self.click(coords[0] + click_offset_x, coords[1])
            time.sleep(0.2)
            self.clear_field()
            self.type_text(str(value))
            print(f"[PCController] Filled '{field_label}': {value}")
            return True
        print(f"[PCController] Form label '{field_label}' not found")
        return False

    def fill_form_fields(self, fields: Dict[str, str]) -> int:
        """
        Fill multiple form fields.
        fields = {"Label Text": "value to enter"}
        Returns count of successfully filled fields.
        """
        filled = 0
        for label, value in fields.items():
            if self.fill_form_by_label(label, value):
                filled += 1
            time.sleep(0.1)
        return filled

    def submit_form(self) -> None:
        """Submit the current form by pressing Enter."""
        pyautogui.press("enter")

    def login(self, username: str, password: str,
              username_label: str = "email",
              password_label: str = "password") -> bool:
        """
        Generic login: finds username and password fields by label text
        and fills them in.
        """
        u_success = self.fill_form_by_label(username_label, username)
        time.sleep(0.2)
        p_success = self.fill_form_by_label(password_label, password)
        time.sleep(0.2)
        if u_success or p_success:
            self.submit_form()
            time.sleep(1.5)
            return True
        # Fallback: try Tab-based navigation
        self.press_key("tab")
        time.sleep(0.1)
        self.type_text(username)
        self.press_key("tab")
        time.sleep(0.1)
        self.type_text(password)
        self.press_key("enter")
        return True

    # ════════════════════════════════════════════════════════
    #   HIGH-LEVEL VISION-GUIDED ACTIONS
    # ════════════════════════════════════════════════════════

    def smart_click(self, description: str) -> bool:
        """
        Try multiple strategies to click something described in natural language:
        1. OCR text search
        2. Image template matching (if image file provided)
        3. Vision model coordinate extraction (if zara_vision available)
        """
        # Strategy 1: OCR
        coords = self.find_text_on_screen(description)
        if coords:
            self.click(coords[0], coords[1])
            return True

        # Strategy 2: Vision model
        try:
            from zara_vision import get_vision
            vision = get_vision()
            
            coords = None
            def _find():
                nonlocal coords
                try:
                    coords = vision.find_element(description)
                except Exception:
                    pass
            
            import threading
            t = threading.Thread(target=_find)
            t.start()
            t.join(timeout=5.0)
            
            if t.is_alive():
                print("[PCController] Vision find_element timed out after 5s")
                return False
                
            if coords:
                if 0 < coords[0] < self.screen_width and 0 < coords[1] < self.screen_height:
                    self.click(coords[0], coords[1])
                    return True
        except Exception as e:
            print(f"[PCController] Vision fallback failed: {e}")

        return False

    def execute_natural_command(self, command: str) -> str:
        """
        Execute a natural language PC command.
        Examples:
          "click the submit button"
          "type hello world"
          "scroll down"
          "open Chrome"
          "take a screenshot"
          "go to google.com"
          "press enter"
        """
        cmd = command.lower().strip()

        # CLICK
        click_match = re.search(
            r'click (?:on |the )?["\']?(.+?)["\']?(?:\s+button|\s+link|\s+icon|\s+tab)?$',
            cmd
        )
        if click_match:
            target = click_match.group(1).strip()
            success = self.smart_click(target)
            return f"Clicked '{target}'." if success else f"Could not find '{target}' on screen, Sir."

        # TYPE
        type_match = re.search(r'(?:type|write|enter|input)\s+["\']?(.+?)["\']?$', cmd)
        if type_match:
            text = type_match.group(1).strip()
            self.type_text(text)
            return f"Typed '{text}', Sir."

        # SCROLL
        if "scroll down" in cmd:
            amount = -5
            scroll_match = re.search(r'scroll down\s+(\d+)', cmd)
            if scroll_match:
                amount = -int(scroll_match.group(1))
            self.scroll(amount)
            return "Scrolled down."

        if "scroll up" in cmd:
            amount = 5
            scroll_match = re.search(r'scroll up\s+(\d+)', cmd)
            if scroll_match:
                amount = int(scroll_match.group(1))
            self.scroll(amount)
            return "Scrolled up."

        # PRESS KEY
        key_match = re.search(r'press\s+(?:the\s+)?(.+?)(?:\s+key)?$', cmd)
        if key_match:
            key = key_match.group(1).strip().lower()
            key_map = {
                "enter": "enter", "return": "enter",
                "escape": "escape", "esc": "escape",
                "tab": "tab", "space": "space",
                "backspace": "backspace", "delete": "delete",
                "up": "up", "down": "down", "left": "left", "right": "right",
                "f5": "f5", "f12": "f12",
            }
            actual_key = key_map.get(key, key)
            self.press_key(actual_key)
            return f"Pressed {actual_key}."

        # NAVIGATE
        url_match = re.search(r'(?:go to|navigate to|open)\s+((?:https?://)?[\w.-]+\.[a-z]{2,}(?:/\S*)?)', cmd)
        if url_match:
            url = url_match.group(1)
            self.navigate_to_url(url)
            return f"Navigating to {url}, Sir."

        # OPEN APP
        open_match = re.search(r'open\s+(.+?)$', cmd)
        if open_match:
            app = open_match.group(1).strip()
            self.open_app(app)
            return f"Opening {app}, Sir."

        # SCREENSHOT
        if "screenshot" in cmd:
            path = self.take_screenshot()
            return f"Screenshot saved to desktop, Sir."

        # READ SCREEN
        if any(w in cmd for w in ["read screen", "what does it say", "read this"]):
            text = self.read_screen_text()
            return text[:500] if text else "I couldn't read any text on screen, Sir."

        # HOTKEYS
        hotkey_map = {
            "copy": ("ctrl", "c"),
            "paste": ("ctrl", "v"),
            "cut": ("ctrl", "x"),
            "undo": ("ctrl", "z"),
            "redo": ("ctrl", "y"),
            "save": ("ctrl", "s"),
            "select all": ("ctrl", "a"),
            "new tab": ("ctrl", "t"),
            "close tab": ("ctrl", "w"),
            "refresh": ("ctrl", "r"),
            "go back": ("alt", "left"),
            "go forward": ("alt", "right"),
            "find": ("ctrl", "f"),
            "zoom in": ("ctrl", "+"),
            "zoom out": ("ctrl", "-"),
        }
        for phrase, keys in hotkey_map.items():
            if phrase in cmd:
                self.hotkey(*keys)
                return f"Done, Sir."

        return f"I didn't understand that PC command: '{command}'"

    # ════════════════════════════════════════════════════════
    #   FILE SYSTEM
    # ════════════════════════════════════════════════════════

    def open_file(self, path: str) -> None:
        """Open a file with its default application."""
        os.startfile(os.path.expandvars(os.path.expanduser(path)))

    def open_folder(self, path: str) -> None:
        """Open a folder in File Explorer."""
        subprocess.Popen(f'explorer "{os.path.expandvars(os.path.expanduser(path))}"')


# ════════════════════════════════════════════════════════
#   GLOBAL SINGLETON
# ════════════════════════════════════════════════════════

_pc_controller: Optional[PCController] = None


def get_pc_controller() -> PCController:
    """Get the global PCController instance."""
    global _pc_controller
    if _pc_controller is None:
        _pc_controller = PCController()
    return _pc_controller
