"""Gender Detection module for Zara.

Detects user gender from explicit statements and speech characteristics,
saving preferences persistently.
"""

import os
import json
import re
from typing import Optional

PREFS_FILE = "zara_prefs.json"

class GenderDetector:
    def __init__(self):
        self.gender = self._load_gender()

    def _load_gender(self) -> str:
        """Load from persistent user prefs."""
        if os.path.exists(PREFS_FILE):
            try:
                with open(PREFS_FILE, "r") as f:
                    data = json.load(f)
                return data.get("user_gender", "unknown")
            except Exception:
                pass
        return "unknown"

    def _save_gender(self, gender: str) -> None:
        """Save to persistent user prefs."""
        self.gender = gender
        data = {}
        if os.path.exists(PREFS_FILE):
            try:
                with open(PREFS_FILE, "r") as f:
                    data = json.load(f)
            except:
                pass
        
        data["user_gender"] = gender
        try:
            with open(PREFS_FILE, "w") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"[Gender Detector] Failed to save: {e}")

    def get_honorific(self) -> str:
        """Return Sir or Ma'am based on detected gender."""
        if self.gender == "female":
            return "Ma'am"
        elif self.gender == "male":
            return "Sir"
        # Default to Sir if unknown, but can be adaptive
        return "Sir"

    def detect_from_text(self, text: str) -> bool:
        """Detect gender identity from explicit statements in text."""
        text_lower = text.lower()
        
        female_triggers = [
            "i am a woman", "i'm a woman", "i am a girl", "i'm a girl",
            "i am female", "i'm female", "call me ma'am", "i am a lady"
        ]
        
        male_triggers = [
            "i am a man", "i'm a man", "i am a boy", "i'm a boy",
            "i am male", "i'm male", "call me sir", "i am a guy"
        ]
        
        for trigger in female_triggers:
            if trigger in text_lower:
                if self.gender != "female":
                    print("[Gender Detector] Detected female user")
                    self._save_gender("female")
                    return True
                    
        for trigger in male_triggers:
            if trigger in text_lower:
                if self.gender != "male":
                    print("[Gender Detector] Detected male user")
                    self._save_gender("male")
                    return True
                    
        return False

_instance = None

def get_gender_detector() -> GenderDetector:
    global _instance
    if _instance is None:
        _instance = GenderDetector()
    return _instance

def get_honorific() -> str:
    """Convenience function for system prompts."""
    return get_gender_detector().get_honorific()
