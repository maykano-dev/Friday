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
import numpy as np
import os


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
        """Start lightweight proactive mode."""
        self._running = True
        self._thread = threading.Thread(target=self._lightweight_watch, daemon=True)
        self._thread.start()
        print("[Zara Eyes] Proactive error detection active")
    
    def stop(self):
        """Stop vision monitoring."""
        self._running = False
        print("[Zara Eyes] Vision paused.")
    
    def _lightweight_watch(self):
        """Fast loop: only checks for red-pixel errors, no LLM cost."""
        while self._running:
            try:
                screenshot = pyautogui.screenshot()
                if self._detect_error_fast(screenshot):
                    # Only call LLM when error is strongly suspected
                    try:
                        import win32gui
                        title = win32gui.GetWindowText(win32gui.GetForegroundWindow())
                    except:
                        title = "Unknown"
                    self._analyze_screen(screenshot, title, focus_on_error=True)
            except Exception as e:
                pass
            time.sleep(self.check_interval)

    def _vision_loop(self):
        """Main vision loop - legacy continuous mode."""
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
        """Quick error detection using numpy for vectorized analysis."""
        try:
            w, h = screenshot.size
            # Sample center region
            region = screenshot.crop((w//4, h//4, w*3//4, h*3//4))
            arr = np.array(region)
            
            # Red pixels: R > 200, G < 100, B < 100
            # arr shape is (H, W, 3)
            red_mask = (arr[:,:,0] > 200) & (arr[:,:,1] < 100) & (arr[:,:,2] < 100)
            
            # If more than 500 red pixels, suspect an error
            return int(red_mask.sum()) > 500
        except:
            return False
    
    def _analyze_screen(self, screenshot, window_title: str, focus_on_error: bool = False):
        """Use vision model to deeply analyze the screen."""
        try:
            import ollama
            
            DEBUG_VISION = os.environ.get("ZARA_DEBUG_VISION", "0") == "1"
            if DEBUG_VISION:
                debug_path = os.path.join(os.path.dirname(__file__), "last_screenshot.png")
                screenshot.save(debug_path)
                print(f"[Zara Eyes] Debug screenshot saved to {debug_path}")
            
            # Fallback OCR check
            ocr_text = self._read_text_ocr(screenshot)
            
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
                description = ocr_text[:200] or f"I see the {window_title} window open, Sir."
                self.current_context = ScreenContext(
                    timestamp=time.time(),
                    active_window=window_title,
                    text_on_screen=ocr_text,
                    has_error=False,
                    raw_description=description
                )
                return
            
            if error_msg:
                print(f"[Zara Eyes] Vision error: {error_msg}")
                description = ocr_text[:200] or f"I see the {window_title} window open, Sir."
                self.current_context = ScreenContext(
                    timestamp=time.time(),
                    active_window=window_title,
                    text_on_screen=ocr_text,
                    has_error=False,
                    raw_description=description
                )
                return
            
            description = response_text or ocr_text[:200] or f"I see the {window_title} window open, Sir."
            print(f"[Zara Eyes] Vision says: {description}")
            
            # Create context
            self.current_context = ScreenContext(
                timestamp=time.time(),
                active_window=window_title,
                text_on_screen=ocr_text,
                has_error="error" in description.lower() or "error" in ocr_text.lower(),
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

    def _read_text_ocr(self, screenshot) -> str:
        """Free offline fallback using pytesseract."""
        try:
            import pytesseract
            # Perform OCR on a slightly downscaled image for speed if needed
            return pytesseract.image_to_string(screenshot, config="--psm 11")[:500]
        except:
            return ""
    
    def look_at(self) -> Optional[ScreenContext]:
        """Take a single screenshot and analyze it."""
        try:
            import pyautogui
            try:
                import win32gui
                window_title = win32gui.GetWindowText(win32gui.GetForegroundWindow())
            except:
                window_title = "Unknown"
            
            # Try actual vision analysis with a short timeout
            screenshot = pyautogui.screenshot()
            self._analyze_screen(screenshot, window_title)
            return self.current_context
            
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
