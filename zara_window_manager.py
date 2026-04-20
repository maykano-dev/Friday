"""Zara Window Manager - Complete Window Control System."""

import pyautogui
import time
from typing import Optional, List, Tuple, Dict
from dataclasses import dataclass
import subprocess


@dataclass
class WindowInfo:
    """Information about a window."""
    title: str
    hwnd: int
    x: int
    y: int
    width: int
    height: int
    is_minimized: bool
    is_maximized: bool
    process_name: str


class ZaraWindowManager:
    """Complete window control for Zara."""
    
    def __init__(self):
        self._windows_cache = {}
        self._last_update = 0
        self._using_win32 = False
        
        # Try to import Windows-specific libraries
        try:
            import win32gui
            import win32con
            import win32api
            import win32process
            self.win32gui = win32gui
            self.win32con = win32con
            self.win32api = win32api
            self.win32process = win32process
            self._using_win32 = True
            print("[Window Manager] Windows API available - full control enabled")
        except ImportError:
            print("[Window Manager] win32gui not installed - using fallback methods")
            print("  Install with: pip install pywin32")
    
    # ─────────────────────────────────────────────────────────
    # WINDOW DISCOVERY
    # ─────────────────────────────────────────────────────────
    
    def get_all_windows(self) -> List[WindowInfo]:
        """Get all visible windows."""
        windows = []
        
        if self._using_win32:
            def callback(hwnd, windows):
                if self.win32gui.IsWindowVisible(hwnd):
                    title = self.win32gui.GetWindowText(hwnd)
                    if title and len(title) > 1:
                        rect = self.win32gui.GetWindowRect(hwnd)
                        # FIXED: Use IsIconic for minimized, no direct IsZoomed
                        is_minimized = self.win32gui.IsIconic(hwnd)
                        
                        # Check if maximized by comparing to screen size
                        import pyautogui
                        screen_w, screen_h = pyautogui.size()
                        is_maximized = (rect[2] - rect[0] >= screen_w - 50 and 
                                       rect[3] - rect[1] >= screen_h - 50)
                        
                        # Get process name
                        try:
                            _, pid = self.win32process.GetWindowThreadProcessId(hwnd)
                            handle = self.win32api.OpenProcess(0x0400 | 0x0010, False, pid)
                            process_name = self.win32process.GetModuleFileNameEx(handle, 0)
                            process_name = process_name.split("\\")[-1]
                        except:
                            process_name = "unknown"
                        
                        windows.append(WindowInfo(
                            title=title,
                            hwnd=hwnd,
                            x=rect[0],
                            y=rect[1],
                            width=rect[2] - rect[0],
                            height=rect[3] - rect[1],
                            is_minimized=is_minimized,
                            is_maximized=is_maximized,
                            process_name=process_name
                        ))
                return True
            
            self.win32gui.EnumWindows(callback, windows)
        
        return windows
    
    def find_window(self, title_contains: str = None, process_contains: str = None) -> Optional[WindowInfo]:
        """Find a window by title or process name."""
        windows = self.get_all_windows()
        
        for w in windows:
            if title_contains and title_contains.lower() in w.title.lower():
                return w
            if process_contains and process_contains.lower() in w.process_name.lower():
                return w
        
        return None
    
    def get_active_window(self) -> Optional[WindowInfo]:
        """Get the currently active window."""
        if self._using_win32:
            hwnd = self.win32gui.GetForegroundWindow()
            title = self.win32gui.GetWindowText(hwnd)
            if title:
                rect = self.win32gui.GetWindowRect(hwnd)
                # Manual maximize check for active window
                import pyautogui
                screen_w, screen_h = pyautogui.size()
                is_maximized = (rect[2] - rect[0] >= screen_w - 50 and 
                               rect[3] - rect[1] >= screen_h - 50)
                
                return WindowInfo(
                    title=title,
                    hwnd=hwnd,
                    x=rect[0],
                    y=rect[1],
                    width=rect[2] - rect[0],
                    height=rect[3] - rect[1],
                    is_minimized=self.win32gui.IsIconic(hwnd),
                    is_maximized=is_maximized,
                    process_name=""
                )
        return None
    
    # ─────────────────────────────────────────────────────────
    # WINDOW ACTIONS
    # ─────────────────────────────────────────────────────────
    
    def focus_window(self, title_contains: str = None, process_contains: str = None) -> bool:
        """Bring a window to the foreground."""
        window = self.find_window(title_contains, process_contains)
        if window and self._using_win32:
            # Restore if minimized
            if window.is_minimized:
                self.win32gui.ShowWindow(window.hwnd, self.win32con.SW_RESTORE)
                time.sleep(0.2)
            
            # Bring to front
            try:
                self.win32gui.SetForegroundWindow(window.hwnd)
                print(f"[Window Manager] Focused: {window.title}")
                return True
            except:
                pass
        
        # Fallback: Alt+Tab
        if title_contains:
            pyautogui.keyDown("alt")
            pyautogui.press("tab")
            pyautogui.keyUp("alt")
            time.sleep(0.3)
            return True
        
        return False
    
    def minimize_window(self, title_contains: str = None) -> bool:
        """Minimize a window."""
        window = self.find_window(title_contains)
        if window and self._using_win32:
            self.win32gui.ShowWindow(window.hwnd, self.win32con.SW_MINIMIZE)
            print(f"[Window Manager] Minimized: {window.title}")
            return True
        
        # Fallback
        pyautogui.hotkey("win", "down")
        return True
    
    def maximize_window(self, title_contains: str = None) -> bool:
        """Maximize a window."""
        window = self.find_window(title_contains)
        if window and self._using_win32:
            self.win32gui.ShowWindow(window.hwnd, self.win32con.SW_MAXIMIZE)
            print(f"[Window Manager] Maximized: {window.title}")
            return True
        
        # Fallback
        pyautogui.hotkey("win", "up")
        return True
    
    def restore_window(self, title_contains: str = None) -> bool:
        """Restore a maximized window."""
        window = self.find_window(title_contains)
        if window and self._using_win32:
            self.win32gui.ShowWindow(window.hwnd, self.win32con.SW_RESTORE)
            print(f"[Window Manager] Restored: {window.title}")
            return True
        
        return False
    
    def close_window(self, title_contains: str = None) -> bool:
        """Close a window."""
        window = self.find_window(title_contains)
        if window and self._using_win32:
            self.win32gui.PostMessage(window.hwnd, self.win32con.WM_CLOSE, 0, 0)
            print(f"[Window Manager] Closed: {window.title}")
            return True
        
        # Fallback: Alt+F4
        pyautogui.hotkey("alt", "f4")
        return True
    
    def move_window(self, title_contains: str, x: int, y: int) -> bool:
        """Move a window to specific coordinates."""
        window = self.find_window(title_contains)
        if window and self._using_win32:
            self.win32gui.SetWindowPos(
                window.hwnd, 0, x, y, window.width, window.height, 0
            )
            print(f"[Window Manager] Moved '{title_contains}' to ({x}, {y})")
            return True
        return False
    
    def resize_window(self, title_contains: str, width: int, height: int) -> bool:
        """Resize a window."""
        window = self.find_window(title_contains)
        if window and self._using_win32:
            self.win32gui.SetWindowPos(
                window.hwnd, 0, window.x, window.y, width, height, 0
            )
            print(f"[Window Manager] Resized '{title_contains}' to {width}x{height}")
            return True
        return False
    
    # ─────────────────────────────────────────────────────────
    # SMART LAYOUTS
    # ─────────────────────────────────────────────────────────
    
    def snap_left(self, title_contains: str = None) -> bool:
        """Snap window to left half of screen."""
        if self._using_win32:
            window = self.find_window(title_contains) if title_contains else self.get_active_window()
            if window:
                screen_width = pyautogui.size()[0]
                screen_height = pyautogui.size()[1]
                self.win32gui.SetWindowPos(
                    window.hwnd, 0, 0, 0, screen_width // 2, screen_height, 0
                )
                return True
        
        # Fallback
        pyautogui.hotkey("win", "left")
        return True
    
    def snap_right(self, title_contains: str = None) -> bool:
        """Snap window to right half of screen."""
        if self._using_win32:
            window = self.find_window(title_contains) if title_contains else self.get_active_window()
            if window:
                screen_width = pyautogui.size()[0]
                screen_height = pyautogui.size()[1]
                self.win32gui.SetWindowPos(
                    window.hwnd, 0, screen_width // 2, 0, screen_width // 2, screen_height, 0
                )
                return True
        
        # Fallback
        pyautogui.hotkey("win", "right")
        return True
    
    def snap_top(self, title_contains: str = None) -> bool:
        """Maximize window (snap to top)."""
        return self.maximize_window(title_contains)
    
    def arrange_side_by_side(self, window1_title: str, window2_title: str) -> bool:
        """Arrange two windows side by side."""
        w1 = self.find_window(window1_title)
        w2 = self.find_window(window2_title)
        
        if w1 and w2 and self._using_win32:
            screen_width = pyautogui.size()[0]
            screen_height = pyautogui.size()[1]
            
            # Left window
            self.win32gui.SetWindowPos(w1.hwnd, 0, 0, 0, screen_width // 2, screen_height, 0)
            # Right window
            self.win32gui.SetWindowPos(w2.hwnd, 0, screen_width // 2, 0, screen_width // 2, screen_height, 0)
            
            print(f"[Window Manager] Arranged '{window1_title}' and '{window2_title}' side by side")
            return True
        
        return False
    
    def arrange_grid(self, windows: List[str]) -> bool:
        """Arrange multiple windows in a grid."""
        if len(windows) == 2:
            return self.arrange_side_by_side(windows[0], windows[1])
        
        # For 3-4 windows, arrange in quarters
        window_objs = [self.find_window(w) for w in windows[:4]]
        window_objs = [w for w in window_objs if w is not None]
        
        if len(window_objs) >= 2 and self._using_win32:
            screen_width = pyautogui.size()[0]
            screen_height = pyautogui.size()[1]
            half_w = screen_width // 2
            half_h = screen_height // 2
            
            positions = [
                (0, 0, half_w, half_h),           # Top-left
                (half_w, 0, half_w, half_h),      # Top-right
                (0, half_h, half_w, half_h),      # Bottom-left
                (half_w, half_h, half_w, half_h)  # Bottom-right
            ]
            
            for i, w in enumerate(window_objs):
                if i < 4:
                    x, y, wd, ht = positions[i]
                    self.win32gui.SetWindowPos(w.hwnd, 0, x, y, wd, ht, 0)
            
            print(f"[Window Manager] Arranged {len(window_objs)} windows in grid")
            return True
        
        return False
    
    def minimize_all(self) -> bool:
        """Minimize all windows (show desktop)."""
        pyautogui.hotkey("win", "d")
        return True
    
    def restore_all(self) -> bool:
        """Restore all minimized windows."""
        pyautogui.hotkey("win", "shift", "m")
        return True
    
    # ─────────────────────────────────────────────────────────
    # WINDOW INFORMATION
    # ─────────────────────────────────────────────────────────
    
    def list_windows(self) -> str:
        """Get a list of all open windows."""
        windows = self.get_all_windows()
        if not windows:
            return "No windows detected, Sir."
        
        result = "Open windows:\n"
        for w in windows[:10]:
            result += f"• {w.title} ({w.process_name})\n"
        
        if len(windows) > 10:
            result += f"... and {len(windows) - 10} more."
        
        return result
    
    def get_window_info(self, title_contains: str) -> Optional[str]:
        """Get detailed info about a specific window."""
        window = self.find_window(title_contains)
        if window:
            return (
                f"Window: {window.title}\n"
                f"Process: {window.process_name}\n"
                f"Position: ({window.x}, {window.y})\n"
                f"Size: {window.width}x{window.height}\n"
                f"Minimized: {window.is_minimized}\n"
                f"Maximized: {window.is_maximized}"
            )
        return f"Could not find window containing '{title_contains}'."


# Global singleton
_window_manager: Optional[ZaraWindowManager] = None

def get_window_manager() -> ZaraWindowManager:
    global _window_manager
    if _window_manager is None:
        _window_manager = ZaraWindowManager()
    return _window_manager
