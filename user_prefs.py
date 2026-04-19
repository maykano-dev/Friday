"""Zara User Preferences - Store user settings and defaults."""

import json
import os

PREF_FILE = os.path.join(os.path.dirname(__file__), "user_prefs.json")

DEFAULT_PREFS = {
    "music_app": "spotify",  # spotify, youtube, youtube music
    "browser": "chrome",
    "code_editor": "vscode",
    "volume_level": 60,
    "voice_style": "professional",
    "location_enabled": True,
    "wake_word": "zara",
}

def load_prefs() -> dict:
    """Load user preferences."""
    if os.path.exists(PREF_FILE):
        try:
            with open(PREF_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return DEFAULT_PREFS.copy()

def save_prefs(prefs: dict) -> None:
    """Save user preferences."""
    with open(PREF_FILE, "w") as f:
        json.dump(prefs, f, indent=2)

def get_pref(key: str, default=None):
    """Get a specific preference."""
    prefs = load_prefs()
    return prefs.get(key, default)

def set_pref(key: str, value) -> None:
    """Set a specific preference."""
    prefs = load_prefs()
    prefs[key] = value
    save_prefs(prefs)

def get_music_app() -> str:
    """Get user's preferred music app."""
    return get_pref("music_app", "spotify")
