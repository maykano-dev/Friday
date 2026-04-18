import pygame
import os


class PresenceEngine:
    def __init__(self):
        self.channel = pygame.mixer.Channel(
            7)  # Reserve Channel 7 for ambience
        self.is_ambient = False

    def enter_ambient_mode(self, sound_type="rain"):
        """Play background loops from the assets/ambient directory."""
        path = f"assets/ambient/{sound_type}.wav"
        if not os.path.exists(path):
            print(f"[Presence] Error: Missing audio file {path}")
            return

        sound = pygame.mixer.Sound(path)
        self.channel.play(sound, loops=-1, fade_ms=2000)
        self.channel.set_volume(0.2)  # Keep it low in the background
        self.is_ambient = True
        print(f"[Presence] Ambient mode active: {sound_type}")

    def stop_ambient(self):
        self.channel.fadeout(2000)
        self.is_ambient = False
