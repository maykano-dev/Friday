"""Zara Eyes - Continuous Screen Awareness System."""

import threading
import time
import base64
import io
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from collections import deque

import pyautogui
from PIL import ImageGrab


@dataclass
class ScreenContext:
    """What Zara currently sees."""
    timestamp: float
    active_window: str
    text_on_screen: str
    has_error: bool = False
    error_message: Optional[str] = None
    suggested_actions: list = field(default_factory=list)
    raw_description: str = ""


class ZaraEyes:
    """
    Always-on vision system.
    Zara continuously sees the screen like a human would.
    """
    
    def __init__(self, vision_model: str = "moondream:latest"):
        self.vision_model = vision_model
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
        # Context history (last 10 things she saw)
        self.context_history = deque(maxlen=10)
        self.current_context: Optional[ScreenContext] = None
        
        # How often to check the screen (seconds)
        self.check_interval = 2.0
        
        # Callbacks
        self.on_error_detected = None
        self.on_window_changed = None
        self.on_text_detected = None
        
    def start(self):
        """DISABLED - use look_at() on demand instead."""
        print("[Zara Eyes] On-demand mode - use 'what do you see' to activate")
        self._running = False  # Don't start continuous loop
    
    def stop(self):
        """Stop vision monitoring."""
        self._running = False
        print("[Zara Eyes] Vision paused.")
    
    def _vision_loop(self):
        """Main vision loop - runs continuously."""
        last_window = ""
        
        while self._running:
            try:
                # Capture screen
                screenshot = pyautogui.screenshot()
                
                # Get active window title
                try:
                    import win32gui
                    window_title = win32gui.GetWindowText(win32gui.GetForegroundWindow())
                except:
                    window_title = "Unknown"
                
                # Check if window changed
                if window_title != last_window:
                    last_window = window_title
                    print(f"[Zara Eyes] Window changed: {window_title}")
                    
                    # Analyze the new window with vision model
                    self._analyze_screen(screenshot, window_title)
                
                # Quick check for obvious errors (red text, dialog boxes)
                if self._detect_error_fast(screenshot):
                    print("[Zara Eyes] Possible error detected - analyzing...")
                    self._analyze_screen(screenshot, window_title, focus_on_error=True)
                
                time.sleep(self.check_interval)
                
            except Exception as e:
                print(f"[Zara Eyes] Vision loop error: {e}")
                time.sleep(5)
    
    def _detect_error_fast(self, screenshot) -> bool:
        """Quick error detection without LLM."""
        try:
            # Sample the center of the screen
            width, height = screenshot.size
            region = screenshot.crop((width//4, height//4, width*3//4, height*3//4))
            
            # Count red-ish pixels
            red_count = 0
            for pixel in region.getdata():
                r, g, b = pixel[0], pixel[1], pixel[2]
                if r > 200 and g < 100 and b < 100:
                    red_count += 1
                    if red_count > 500:  # Threshold
                        return True
        except:
            pass
        return False
    
    def _analyze_screen(self, screenshot, window_title: str, focus_on_error: bool = False):
        """Use vision model to deeply analyze the screen."""
        try:
            import ollama
            import os
            
            # Save screenshot for debugging
            debug_path = os.path.join(os.path.dirname(__file__), "last_screenshot.png")
            screenshot.save(debug_path)
            print(f"[Zara Eyes] Screenshot saved to {debug_path}")
            
            # Convert screenshot to base64
            import io
            import base64
            buffer = io.BytesIO()
            screenshot.save(buffer, format="PNG", optimize=True)
            img_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
            
            # Verify we have valid image data
            print(f"[Zara Eyes] Screenshot size: {len(img_b64)} bytes")
            
            # SIMPLE PROMPT - just describe what you see
            prompt = "Look at this screenshot. What application or window is open? Describe ONLY what you actually see in this image. Be specific."
            
            # Query vision model with timeout
            import threading
            import time
            
            response_text = ""
            error_msg = None
            
            def query_vision():
                nonlocal response_text, error_msg
                try:
                    response = ollama.chat(
                        model=self.vision_model,
                        messages=[{
                            'role': 'user',
                            'content': prompt,
                            'images': [img_b64]
                        }],
                        options={'temperature': 0.1, 'num_predict': 80}
                    )
                    response_text = response['message']['content']
                except Exception as e:
                    error_msg = str(e)
            
            thread = threading.Thread(target=query_vision)
            thread.start()
            thread.join(timeout=15)
            
            if thread.is_alive():
                print("[Zara Eyes] Vision query timed out")
                self.current_context = ScreenContext(
                    timestamp=time.time(),
                    active_window=window_title,
                    text_on_screen="",
                    has_error=False,
                    raw_description="I can see your screen but I'm still processing, Sir."
                )
                return
            
            if error_msg:
                print(f"[Zara Eyes] Vision error: {error_msg}")
                # Fallback to basic description
                self.current_context = ScreenContext(
                    timestamp=time.time(),
                    active_window=window_title,
                    text_on_screen="",
                    has_error=False,
                    raw_description=f"I see the {window_title} window open, Sir."
                )
                return
            
            description = response_text
            print(f"[Zara Eyes] Vision says: {description}")
            
            # Create context
            self.current_context = ScreenContext(
                timestamp=time.time(),
                active_window=window_title,
                text_on_screen="",
                has_error="error" in description.lower(),
                error_message=description if "error" in description.lower() else None,
                raw_description=description
            )
            
            self.context_history.append(self.current_context)
            
            # Trigger callbacks
            if self.current_context.has_error and self.on_error_detected:
                self.on_error_detected(self.current_context)
                
        except Exception as e:
            print(f"[Zara Eyes] Vision analysis failed: {e}")
            import traceback
            traceback.print_exc()
    
    def look_at(self) -> Optional[ScreenContext]:
        """Take a single screenshot and analyze it."""
        try:
            import pyautogui
            try:
                import win32gui
                window_title = win32gui.GetWindowText(win32gui.GetForegroundWindow())
            except:
                window_title = "Unknown"
            
            # Use a FASTER model or skip if too slow
            print("[Zara Eyes] Capturing screen...")
            
            # For now, return basic info without LLM (much faster)
            screen_w, screen_h = pyautogui.size()
            mouse_x, mouse_y = pyautogui.position()
            
            context = ScreenContext(
                timestamp=time.time(),
                active_window=window_title,
                text_on_screen="",
                has_error=False,
                raw_description=f"I see the {window_title} window on a {screen_w}x{screen_h} screen. Your mouse is at ({mouse_x}, {mouse_y})."
            )
            
            self.current_context = context
            return context
            
        except Exception as e:
            print(f"[Zara Eyes] Error: {e}")
            return ScreenContext(
                timestamp=time.time(),
                active_window="Unknown",
                text_on_screen="",
                raw_description="I can see your screen, Sir."
            )
    
    def what_do_you_see(self) -> str:
        """Return what Zara currently sees."""
        if self.current_context:
            return f"I see {self.current_context.active_window}. {self.current_context.raw_description}"
        
        # Force a look if no context
        self.look_at()
        if self.current_context:
            return f"I see {self.current_context.active_window}. {self.current_context.raw_description}"
        
        return "I'm still adjusting my eyes, Sir. One moment."
    
    def is_error_visible(self) -> bool:
        """Check if there's currently an error on screen."""
        if self.current_context:
            return self.current_context.has_error
        return False
    
    def get_error_message(self) -> Optional[str]:
        """Get the current error message if any."""
        if self.current_context and self.current_context.has_error:
            return self.current_context.error_message
        return None
    
    def get_active_window(self) -> str:
        """Get the current active window title."""
        if self.current_context:
            return self.current_context.active_window
        return "Unknown"


# Global singleton
_zara_eyes: Optional[ZaraEyes] = None

def get_eyes() -> ZaraEyes:
    global _zara_eyes
    if _zara_eyes is None:
        _zara_eyes = ZaraEyes()
    return _zara_eyes
