"""Zara User Preferences - Learning System."""

import json
import os
from typing import Optional, List, Dict

PREF_FILE = os.path.join(os.path.dirname(__file__), "zara_prefs.json")

DEFAULT_PREFS = {
    "music_app": None,  # Will be learned
    "browser": "chrome",
    "code_editor": "vscode",
    "volume_level": 60,
    "preferred_genres": [],
    "favorite_artists": [],
    "recently_played": [],  # Last 10 songs
    "last_used_app": None,
}

class ZaraPreferences:
    def __init__(self):
        self.prefs = self._load()
    
    def _load(self) -> dict:
        if os.path.exists(PREF_FILE):
            try:
                with open(PREF_FILE, "r") as f:
                    return json.load(f)
            except:
                pass
        return DEFAULT_PREFS.copy()
    
    def _save(self):
        with open(PREF_FILE, "w") as f:
            json.dump(self.prefs, f, indent=2)
    
    def get_music_app(self) -> Optional[str]:
        """Get user's preferred music app."""
        return self.prefs.get("music_app")
    
    def set_music_app(self, app: str):
        """Learn user's preferred music app."""
        self.prefs["music_app"] = app.lower()
        self._save()
        print(f"[Prefs] Learned music app: {app}")
    
    def detect_installed_music_apps(self) -> List[str]:
        """Detect which music apps are installed."""
        installed = []
        
        # Check Spotify
        import shutil
        if shutil.which("spotify") or os.path.exists(os.path.expanduser("~/AppData/Roaming/Spotify/Spotify.exe")):
            installed.append("spotify")
        
        # Check Apple Music
        if shutil.which("apple music") or os.path.exists("C:/Program Files/WindowsApps/AppleInc.AppleMusicWin_*"):
            installed.append("apple_music")
        
        # YouTube Music is always available via web
        installed.append("youtube_music")
        
        return installed
    
    def add_recent_song(self, song: str, artist: str):
        """Remember recently played songs."""
        entry = {"song": song, "artist": artist}
        self.prefs["recently_played"].insert(0, entry)
        self.prefs["recently_played"] = self.prefs["recently_played"][:10]
        
        # Track favorite artists
        if artist.lower() and artist.lower() not in [a.lower() for a in self.prefs["favorite_artists"]]:
            self.prefs["favorite_artists"].append(artist)
            self.prefs["favorite_artists"] = self.prefs["favorite_artists"][:20]
        
        self._save()
    
    def get_favorite_artists(self) -> List[str]:
        return self.prefs.get("favorite_artists", [])
    
    def get_recently_played(self) -> List[dict]:
        return self.prefs.get("recently_played", [])


# Global singleton
_prefs: Optional[ZaraPreferences] = None

def get_prefs() -> ZaraPreferences:
    global _prefs
    if _prefs is None:
        _prefs = ZaraPreferences()
    return _prefs
