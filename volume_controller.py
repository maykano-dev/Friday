"""Zara - Silent Volume Controller.

Controls system volume without any UI popup or visual feedback.
Uses Windows Core Audio API (pycaw) as primary method.
Falls back to pyautogui key simulation if pycaw fails.

All operations are silent and background - no toast notifications,
no volume OSD overlay.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Optional


class SilentVolumeController:
    """Controls PC volume silently with no UI popups."""

    def __init__(self):
        self._lock = threading.Lock()
        self._current_volume: float = -1.0  # -1 = unknown
        self._is_muted: bool = False
        self._vol_interface = None
        self._init_pycaw()

    def _init_pycaw(self):
        """Initialize Windows Core Audio API interface."""
        try:
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL

            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            self._vol_interface = cast(interface, POINTER(IAudioEndpointVolume))
            self._current_volume = self._vol_interface.GetMasterVolumeLevelScalar()
            self._is_muted = bool(self._vol_interface.GetMute())
            print(f"[Volume] pycaw initialized. Current: {self._current_volume:.0%}, Muted: {self._is_muted}")
        except Exception as e:
            print(f"[Volume] pycaw init failed ({e}), will use keypress fallback")
            self._vol_interface = None

    def get_volume(self) -> float:
        """Get current volume (0.0 to 1.0)."""
        with self._lock:
            if self._vol_interface:
                try:
                    self._current_volume = self._vol_interface.GetMasterVolumeLevelScalar()
                    return self._current_volume
                except Exception:
                    pass
            return self._current_volume if self._current_volume >= 0 else 0.5

    def set_volume(self, level: float) -> bool:
        """
        Set volume to exact level (0.0 to 1.0).
        Silent - no OS popup.
        """
        level = max(0.0, min(1.0, level))

        with self._lock:
            if self._vol_interface:
                try:
                    self._vol_interface.SetMasterVolumeLevelScalar(level, None)
                    self._current_volume = level
                    print(f"[Volume] Set to {level:.0%} via pycaw (silent)")
                    return True
                except Exception as e:
                    print(f"[Volume] pycaw set failed: {e}")

            # Fallback: use keypress (this may show OS popup briefly)
            return self._set_volume_keypress(level)

    def _set_volume_keypress(self, target: float) -> bool:
        """Adjust volume via keypresses - less precise but works as fallback."""
        try:
            import pyautogui
            current = self.get_volume()
            diff = target - current

            # Each keypress changes volume by ~2% on most Windows systems
            steps = int(abs(diff) / 0.02)
            if steps == 0:
                return True

            key = "volumeup" if diff > 0 else "volumedown"
            for _ in range(min(steps, 50)):  # Cap at 50 presses
                pyautogui.press(key)
                time.sleep(0.02)

            self._current_volume = target
            return True
        except Exception as e:
            print(f"[Volume] Keypress fallback failed: {e}")
            return False

    def volume_up(self, amount: float = 0.10) -> tuple[bool, float]:
        """Increase volume by amount (default 10%)."""
        current = self.get_volume()
        new_level = min(1.0, current + amount)
        success = self.set_volume(new_level)
        return success, new_level

    def volume_down(self, amount: float = 0.10) -> tuple[bool, float]:
        """Decrease volume by amount (default 10%)."""
        current = self.get_volume()
        new_level = max(0.0, current - amount)
        success = self.set_volume(new_level)
        return success, new_level

    def mute(self) -> bool:
        """Mute system volume silently."""
        with self._lock:
            if self._vol_interface:
                try:
                    self._vol_interface.SetMute(1, None)
                    self._is_muted = True
                    print("[Volume] Muted via pycaw (silent)")
                    return True
                except Exception as e:
                    print(f"[Volume] pycaw mute failed: {e}")

            # Fallback
            try:
                import pyautogui
                pyautogui.press("volumemute")
                self._is_muted = True
                return True
            except Exception:
                return False

    def unmute(self) -> bool:
        """Unmute system volume silently."""
        with self._lock:
            if self._vol_interface:
                try:
                    self._vol_interface.SetMute(0, None)
                    self._is_muted = False
                    print("[Volume] Unmuted via pycaw (silent)")
                    return True
                except Exception as e:
                    print(f"[Volume] pycaw unmute failed: {e}")

            try:
                import pyautogui
                pyautogui.press("volumemute")
                self._is_muted = False
                return True
            except Exception:
                return False

    def toggle_mute(self) -> tuple[bool, bool]:
        """Toggle mute. Returns (success, is_now_muted)."""
        if self._is_muted:
            return self.unmute(), False
        else:
            return self.mute(), True

    def set_volume_from_text(self, text: str) -> Optional[tuple[bool, float]]:
        """
        Parse natural language volume command and execute.
        Examples:
        - "volume up" → +10%
        - "turn it up" → +10%
        - "set volume to 50" → 50%
        - "volume to 70 percent" → 70%
        - "louder" → +15%
        - "quieter" / "softer" → -15%
        - "mute" → mute
        - "unmute" → unmute
        - "max volume" → 100%
        - "half volume" → 50%
        
        Returns (success, new_level) or None if not a volume command.
        """
        import re
        text_lower = text.lower().strip()

        # Mute commands
        if re.search(r"\b(mute|silence|quiet)\b", text_lower) and "unmute" not in text_lower:
            success = self.mute()
            return success, 0.0

        if re.search(r"\bunmute\b", text_lower):
            success = self.unmute()
            return success, self.get_volume()

        # Specific percentage
        pct_match = re.search(r"\b(\d+)\s*(?:%|percent)\b", text_lower)
        if pct_match:
            pct = int(pct_match.group(1))
            level = pct / 100.0
            success = self.set_volume(level)
            return success, level

        # "set to N"
        set_match = re.search(r"(?:set|put|change).+?(?:to|at)\s+(\d+)", text_lower)
        if set_match:
            val = int(set_match.group(1))
            level = val / 100.0 if val > 1 else val
            success = self.set_volume(level)
            return success, level

        # Max / min
        if re.search(r"\b(max|maximum|full|100)\b", text_lower) and "volume" in text_lower:
            success = self.set_volume(1.0)
            return success, 1.0

        if re.search(r"\b(half|50)\b", text_lower) and "volume" in text_lower:
            success = self.set_volume(0.5)
            return success, 0.5

        if re.search(r"\bminimum\b", text_lower) and "volume" in text_lower:
            success = self.set_volume(0.05)
            return success, 0.05

        # Up/down
        up_words = ["up", "louder", "higher", "increase", "raise", "boost", "more"]
        down_words = ["down", "quieter", "lower", "decrease", "reduce", "softer", "less"]

        if any(w in text_lower for w in up_words):
            # Check for amount modifier
            if any(w in text_lower for w in ["little", "bit", "slightly"]):
                return self.volume_up(0.05)
            elif any(w in text_lower for w in ["lot", "much", "way"]):
                return self.volume_up(0.20)
            return self.volume_up(0.10)

        if any(w in text_lower for w in down_words):
            if any(w in text_lower for w in ["little", "bit", "slightly"]):
                return self.volume_down(0.05)
            elif any(w in text_lower for w in ["lot", "much", "way"]):
                return self.volume_down(0.20)
            return self.volume_down(0.10)

        return None

    def duck_for_speech(self, duck_amount: float = 0.4) -> float:
        """Lower volume during Zara speech. Returns saved level."""
        current = self.get_volume()
        target = max(0.0, current - duck_amount)
        self.set_volume(target)
        return current  # Return original so caller can restore

    def restore_after_speech(self, original_level: float) -> bool:
        """Restore volume after Zara finishes speaking."""
        return self.set_volume(original_level)


# Global singleton
_controller: Optional[SilentVolumeController] = None


def get_volume_controller() -> SilentVolumeController:
    global _controller
    if _controller is None:
        _controller = SilentVolumeController()
    return _controller


def handle_volume_command(text: str) -> Optional[str]:
    """
    Process a volume command and return a spoken response.
    Returns None if not a volume command.
    """
    controller = get_volume_controller()
    result = controller.set_volume_from_text(text)

    if result is None:
        return None

    success, new_level = result
    honorific = "Sir"
    try:
        from gender_detector import get_honorific
        honorific = get_honorific()
    except Exception:
        pass

    if not success:
        return f"I had trouble adjusting the volume, {honorific}."

    if new_level == 0.0:
        return f"Muted, {honorific}."

    pct = int(new_level * 100)
    return f"Volume set to {pct}%, {honorific}."
