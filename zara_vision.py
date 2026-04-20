"""Zara Vision - Complete Screen and Camera Understanding System."""

import base64
import io
import time
import threading
from typing import Optional, Tuple, List
from dataclasses import dataclass
from enum import Enum

import pyautogui
from PIL import Image, ImageGrab
import numpy as np

try:
    import cv2
    CAMERA_AVAILABLE = True
except ImportError:
    CAMERA_AVAILABLE = False
    print("[Vision] OpenCV not installed - camera disabled")


class VisionMode(Enum):
    SCREEN = "screen"
    CAMERA = "camera"
    REGION = "region"
    WINDOW = "window"


@dataclass
class VisionResult:
    """Result from vision analysis."""
    description: str
    text_found: List[str]
    objects_detected: List[str]
    colors: List[str]
    error_detected: bool
    error_message: Optional[str]
    ui_elements: List[dict]
    suggested_actions: List[str]


class ZaraVision:
    """Complete vision system for Zara."""
    
    def __init__(self, model: str = "moondream:latest"):
        self.model = model
        self.screen_width, self.screen_height = pyautogui.size()
        self._camera = None
        self._last_frame = None
        
    # ─────────────────────────────────────────────────────────
    # SCREEN CAPTURE
    # ─────────────────────────────────────────────────────────
    
    def capture_screen(self, region: Tuple[int, int, int, int] = None) -> str:
        """Capture screen or region and return base64."""
        if region:
            screenshot = pyautogui.screenshot(region=region)
        else:
            screenshot = pyautogui.screenshot()
        
        buffer = io.BytesIO()
        screenshot.save(buffer, format="PNG", optimize=True)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")
    
    def capture_active_window(self) -> str:
        """Capture only the active window."""
        try:
            import win32gui
            hwnd = win32gui.GetForegroundWindow()
            rect = win32gui.GetWindowRect(hwnd)
            # rect is (left, top, right, bottom)
            # pyautogui needs (left, top, width, height)
            w = rect[2] - rect[0]
            h = rect[3] - rect[1]
            return self.capture_screen(region=(rect[0], rect[1], w, h))
        except:
            return self.capture_screen()
    
    def capture_camera(self) -> Optional[str]:
        """Capture webcam image."""
        if not CAMERA_AVAILABLE:
            return None
        
        try:
            if self._camera is None:
                self._camera = cv2.VideoCapture(0)
            
            ret, frame = self._camera.read()
            if ret:
                self._last_frame = frame
                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                return base64.b64encode(buffer).decode("utf-8")
        except Exception as e:
            print(f"[Vision] Camera error: {e}")
        
        return None
    
    def release_camera(self):
        """Release camera resources."""
        if self._camera:
            self._camera.release()
            self._camera = None
    
    # ─────────────────────────────────────────────────────────
    # VISION QUERIES
    # ─────────────────────────────────────────────────────────
    
    def _query_vision(self, image_b64: str, prompt: str) -> str:
        """Send image to vision model."""
        import ollama
        
        try:
            response = ollama.chat(
                model=self.model,
                messages=[{
                    'role': 'user',
                    'content': prompt,
                    'images': [image_b64]
                }],
                options={'temperature': 0.2}  # Low temp for accuracy
            )
            return response['message']['content']
        except Exception as e:
            error_str = str(e)
            if "memory" in error_str.lower() or "500" in error_str:
                print(f"[Vision] CRITICAL: System memory insufficient for {self.model}. Try a smaller model or clear RAM.")
                return f"I'm sorry Sir, my visual cortex requires more system memory to process this image. Current available: {error_str}"
            print(f"[Vision] Query error: {e}")
            return f"I encountered an error while analyzing the image: {e}"
    
    # ─────────────────────────────────────────────────────────
    # HIGH-LEVEL VISION COMMANDS
    # ─────────────────────────────────────────────────────────
    
    def see(self, mode: VisionMode = VisionMode.SCREEN) -> str:
        """General purpose: 'Zara, what do you see?'"""
        if mode == VisionMode.SCREEN:
            img = self.capture_screen()
            prompt = "Describe what you see on this screen in detail. Include any open applications, text, images, and notable elements."
        elif mode == VisionMode.CAMERA:
            img = self.capture_camera()
            if not img:
                return "I cannot access the camera, Sir."
            prompt = "Describe what you see through the camera. Include people, objects, setting, and lighting."
        elif mode == VisionMode.WINDOW:
            img = self.capture_active_window()
            prompt = "Describe what you see in this active window."
        else:
            return "I don't understand that vision mode, Sir."
        
        return self._query_vision(img, prompt)
    
    def read_text(self, mode: VisionMode = VisionMode.SCREEN) -> str:
        """Read all text visible on screen."""
        img = self.capture_screen() if mode == VisionMode.SCREEN else self.capture_active_window()
        prompt = "Read all text visible in this image. Return the text exactly as it appears, organized by location (e.g., 'Top left:', 'Center:')."
        return self._query_vision(img, prompt)
    
    def find_element(self, description: str) -> Optional[Tuple[int, int]]:
        """Find a UI element by description and return coordinates."""
        img = self.capture_screen()
        prompt = f"Find the '{description}' in this screenshot. Return ONLY the approximate center coordinates in format 'x,y'. If not found, return 'None'."
        
        response = self._query_vision(img, prompt)
        
        import re
        match = re.search(r'(\d+)\s*[,]\s*(\d+)', response)
        if match:
            return (int(match.group(1)), int(match.group(2)))
        return None
    
    def click_on(self, description: str) -> bool:
        """Find and click on a described element."""
        coords = self.find_element(description)
        if coords:
            pyautogui.moveTo(coords[0], coords[1], duration=0.5)
            pyautogui.click()
            print(f"[Vision] Clicked '{description}' at {coords}")
            return True
        return False
    
    def detect_error(self) -> Optional[str]:
        """Check if there's an error on screen and return it."""
        img = self.capture_screen()
        prompt = "Is there an error message, warning, or dialog box visible on this screen? If yes, describe it and quote the exact error text. If no error, just say 'No error detected.'"
        response = self._query_vision(img, prompt)
        
        if "no error" in response.lower():
            return None
        return response
    
    def analyze_ui(self) -> VisionResult:
        """Complete UI analysis - buttons, fields, navigation."""
        img = self.capture_screen()
        prompt = """Analyze this UI screenshot and return a JSON object with:
        {
            "description": "overall description",
            "text_found": ["list of visible text"],
            "ui_elements": [
                {"type": "button/link/input", "text": "element text", "location": "approximate"}
            ],
            "suggested_actions": ["what user might want to do next"]
        }
        Return ONLY valid JSON, no other text."""
        
        response = self._query_vision(img, prompt)
        
        import json
        import re
        try:
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return VisionResult(
                    description=data.get('description', ''),
                    text_found=data.get('text_found', []),
                    objects_detected=[],
                    colors=[],
                    error_detected='error' in response.lower(),
                    error_message=None,
                    ui_elements=data.get('ui_elements', []),
                    suggested_actions=data.get('suggested_actions', [])
                )
        except:
            pass
        
        return VisionResult(description=response, text_found=[], objects_detected=[], 
                          colors=[], error_detected=False, error_message=None, 
                          ui_elements=[], suggested_actions=[])
    
    def answer_question(self, question: str, mode: VisionMode = VisionMode.SCREEN) -> str:
        """Answer a specific question about what's visible."""
        img = self.capture_screen() if mode == VisionMode.SCREEN else self.capture_camera()
        if not img:
            return "I cannot see anything right now, Sir."

        return self._query_vision(img, question)

    def ask_about_screen(self, question: str) -> str:
        """Ask a question about what's on the screen."""
        img = self.capture_screen()
        return self._query_vision(img, question)

    def ask_about_camera(self, question: str) -> str:
        """Ask a question about what the camera sees."""
        img = self.capture_camera()
        if not img:
            return "I cannot access the camera, Sir."
        return self._query_vision(img, question)
    
    def summarize_document(self) -> str:
        """Summarize a document visible on screen."""
        img = self.capture_active_window()
        prompt = "This appears to be a document. Summarize its key points in 3-5 bullet points."
        return self._query_vision(img, prompt)
    
    def read_code(self) -> str:
        """Read and understand code on screen."""
        img = self.capture_active_window()
        prompt = "This is code. Explain what this code does, identify the language, and note any potential issues."
        return self._query_vision(img, prompt)
    
    def identify_person(self) -> str:
        """Identify a person through the camera."""
        img = self.capture_camera()
        if not img:
            return "Camera not available."
        prompt = "Describe the person visible in this image. Include estimated age, gender, clothing, expression, and any distinguishing features. Do not make up names - only describe what you see."
        return self._query_vision(img, prompt)
    
    def scan_environment(self) -> str:
        """Full environment scan through camera."""
        img = self.capture_camera()
        if not img:
            return "Camera not available."
        prompt = "Describe this environment in detail. Include setting (office/home/outdoor), lighting, objects present, and general atmosphere."
        return self._query_vision(img, prompt)
    
    def navigate_to(self, destination: str) -> bool:
        """Navigate through UI to reach a destination."""
        steps_taken = 0
        max_steps = 5
        
        while steps_taken < max_steps:
            img = self.capture_screen()
            prompt = f"I need to navigate to '{destination}'. What should I click next? Options: a specific element description, 'scroll down', 'go back', or 'done' if already there. Return ONLY one of these."
            
            action = self._query_vision(img, prompt).strip().lower()
            
            if 'done' in action or destination.lower() in action:
                return True
            elif 'scroll' in action:
                pyautogui.scroll(-300)
            elif 'back' in action:
                pyautogui.hotkey('alt', 'left')
            elif action:
                self.click_on(action)
            else:
                break
            
            steps_taken += 1
            time.sleep(1)
        
        return False
    
    # ─────────────────────────────────────────────────────────
    # REAL-TIME MONITORING
    # ─────────────────────────────────────────────────────────
    
    def monitor_for_change(self, check_interval: float = 1.0, timeout: float = 30.0) -> Optional[str]:
        """Monitor screen for changes and return what changed."""
        import hashlib
        
        initial = self.capture_screen()
        initial_hash = hashlib.md5(initial.encode()).hexdigest()
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            time.sleep(check_interval)
            current = self.capture_screen()
            current_hash = hashlib.md5(current.encode()).hexdigest()
            
            if current_hash != initial_hash:
                prompt = "Compare this new screenshot with the previous state. What changed? Describe only the differences."
                return self._query_vision(current, prompt)
        
        return None
    
    def wait_for_element(self, description: str, timeout: float = 30.0) -> bool:
        """Wait for a specific element to appear on screen."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.find_element(description):
                return True
            time.sleep(0.5)
        return False


# ─────────────────────────────────────────────────────────
# GLOBAL SINGLETON
# ─────────────────────────────────────────────────────────

_vision_instance: Optional[ZaraVision] = None

def get_vision() -> ZaraVision:
    global _vision_instance
    if _vision_instance is None:
        _vision_instance = ZaraVision()
    return _vision_instance
