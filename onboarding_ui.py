"""Zara Onboarding UI - Modern overlay within Pygame window."""

import pygame
import math
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Callable


class OnboardingStep(Enum):
    WELCOME = "welcome"
    VOICE_SETUP = "voice_setup"
    LOCATION = "location"
    PERSONALITY = "personality"
    COMPLETE = "complete"


@dataclass
class UserProfile:
    name: str = ""
    preferred_name: str = ""
    wake_word: str = "Zara"
    voice_style: str = "professional"
    location_enabled: bool = False
    location_city: str = ""
    location_country: str = ""

    def save(self):
        import json
        import os
        path = os.path.join(os.path.dirname(__file__), "user_profile.json")
        with open(path, "w") as f:
            json.dump(self.__dict__, f, indent=2)

    @classmethod
    def load(cls) -> Optional["UserProfile"]:
        import json
        import os
        path = os.path.join(os.path.dirname(__file__), "user_profile.json")
        if os.path.exists(path):
            with open(path, "r") as f:
                data = json.load(f)
                return cls(**data)
        return None


class OnboardingUI:
    """Modern onboarding overlay rendered within the main Pygame window."""

    def __init__(self, screen_width: int, screen_height: int):
        self.width = screen_width
        self.height = screen_height
        self.current_step = OnboardingStep.WELCOME
        self.profile = UserProfile()
        self.animation_progress = 0.0
        self._animating = True
        self._font_large = None
        self._font_medium = None
        self._font_small = None
        self._input_active = False
        self._input_text = ""
        self._cursor_blink = 0

        # Location detection
        self._location_detected = None
        self._detecting_location = False

        # Callbacks
        self.on_complete: Optional[Callable] = None

    def init_fonts(self):
        """Initialize fonts after pygame.font.init()"""
        self._font_large = pygame.font.SysFont("Segoe UI", 48, bold=True)
        self._font_medium = pygame.font.SysFont("Segoe UI", 28)
        self._font_small = pygame.font.SysFont("Segoe UI", 18)

    def update(self, dt: float):
        """Update animations."""
        if self._animating:
            self.animation_progress = min(
                1.0, self.animation_progress + dt * 2)

        self._cursor_blink += dt
        if self._cursor_blink > 1.0:
            self._cursor_blink = 0

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle pygame events. Returns True if event was consumed."""

        if event.type == pygame.KEYDOWN:
            if self._input_active:
                if event.key == pygame.K_RETURN:
                    self._input_active = False
                    self.profile.name = self._input_text
                    self.profile.preferred_name = self._input_text.split()[
                        0] if self._input_text else ""
                    self.next_step()
                elif event.key == pygame.K_BACKSPACE:
                    self._input_text = self._input_text[:-1]
                else:
                    if event.unicode and event.unicode.isprintable():
                        self._input_text += event.unicode
                return True

            elif event.key == pygame.K_RETURN or event.key == pygame.K_SPACE:
                self.next_step()
                return True

        elif event.type == pygame.MOUSEBUTTONDOWN:
            x, y = event.pos
            # Check button clicks
            if self._get_continue_button_rect().collidepoint(x, y):
                self.next_step()
                return True
            elif self._get_skip_button_rect().collidepoint(x, y):
                self.skip_step()
                return True

        return False

    def next_step(self):
        """Move to next onboarding step."""
        steps = list(OnboardingStep)
        current_idx = steps.index(self.current_step)
        if current_idx < len(steps) - 1:
            self.current_step = steps[current_idx + 1]
            self.animation_progress = 0.0
            self._animating = True

            # Auto-detect location when reaching location step
            if self.current_step == OnboardingStep.LOCATION and not self._location_detected:
                self._detect_location()
        else:
            # Onboarding complete
            self.profile.save()
            if self.on_complete:
                self.on_complete()

    def skip_step(self):
        """Skip current step (only for optional steps)."""
        if self.current_step in [OnboardingStep.LOCATION, OnboardingStep.PERSONALITY]:
            self.next_step()

    def _detect_location(self):
        """Detect user location from IP."""
        self._detecting_location = True

        import threading

        def detect():
            try:
                import requests
                resp = requests.get("https://ipapi.co/json/", timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    self._location_detected = {
                        "city": data.get("city", ""),
                        "region": data.get("region", ""),
                        "country": data.get("country_name", ""),
                    }
            except:
                self._location_detected = {
                    "city": "Unknown", "region": "", "country": ""}
            finally:
                self._detecting_location = False

        threading.Thread(target=detect, daemon=True).start()

    def _get_continue_button_rect(self) -> pygame.Rect:
        return pygame.Rect(self.width//2 - 100, self.height - 120, 200, 50)

    def _get_skip_button_rect(self) -> pygame.Rect:
        return pygame.Rect(self.width - 120, self.height - 50, 80, 30)

    def _draw_glass_card(self, screen: pygame.Surface, rect: pygame.Rect, alpha: int = 180):
        """Draw a glassmorphism card."""
        card_surf = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        card_surf.fill((20, 25, 35, alpha))

        # Border
        pygame.draw.rect(card_surf, (0, 212, 255, 100),
                         card_surf.get_rect(), width=2, border_radius=12)

        screen.blit(card_surf, rect)

    def _draw_text_centered(self, screen: pygame.Surface, text: str, font: pygame.font.Font,
                            y: int, color: tuple = (255, 255, 255)):
        """Draw centered text."""
        surf = font.render(text, True, color)
        x = self.width // 2 - surf.get_width() // 2
        screen.blit(surf, (x, y))

    def _draw_input_box(self, screen: pygame.Surface, rect: pygame.Rect, text: str, active: bool):
        """Draw a text input box."""
        # Background
        color = (30, 40, 50) if active else (20, 25, 35)
        pygame.draw.rect(screen, color, rect, border_radius=8)

        # Border
        border_color = (0, 212, 255) if active else (60, 70, 80)
        pygame.draw.rect(screen, border_color, rect, width=2, border_radius=8)

        # Text
        display_text = text
        if active and int(self._cursor_blink * 2) % 2 == 0:
            display_text += "|"

        if display_text:
            surf = self._font_medium.render(
                display_text, True, (255, 255, 255))
            text_rect = surf.get_rect(midleft=(rect.x + 15, rect.centery))
            screen.blit(surf, text_rect)
        elif not active:
            placeholder = self._font_medium.render(
                "Enter your name...", True, (100, 110, 120))
            text_rect = placeholder.get_rect(
                midleft=(rect.x + 15, rect.centery))
            screen.blit(placeholder, text_rect)

    def render(self, screen: pygame.Surface):
        """Render the onboarding overlay."""
        if not self._font_large:
            self.init_fonts()

        # Semi-transparent overlay
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, int(200 * self.animation_progress)))
        screen.blit(overlay, (0, 0))

        # Content based on current step
        if self.current_step == OnboardingStep.WELCOME:
            self._render_welcome(screen)
        elif self.current_step == OnboardingStep.VOICE_SETUP:
            self._render_voice_setup(screen)
        elif self.current_step == OnboardingStep.LOCATION:
            self._render_location(screen)
        elif self.current_step == OnboardingStep.PERSONALITY:
            self._render_personality(screen)

    def _render_welcome(self, screen: pygame.Surface):
        """Render welcome screen."""
        alpha = int(255 * self.animation_progress)

        # Title
        title = self._font_large.render("Welcome to", True, (255, 255, 255))
        title.set_alpha(alpha)
        title_rect = title.get_rect(
            center=(self.width//2, self.height//2 - 60))
        screen.blit(title, title_rect)

        # Zara name with accent
        zara = self._font_large.render("ZARA", True, (0, 212, 255))
        zara.set_alpha(alpha)
        zara_rect = zara.get_rect(center=(self.width//2, self.height//2))
        screen.blit(zara, zara_rect)

        # Subtitle
        subtitle = self._font_small.render(
            "Your always-on AI assistant", True, (180, 190, 200))
        subtitle.set_alpha(alpha)
        subtitle_rect = subtitle.get_rect(
            center=(self.width//2, self.height//2 + 60))
        screen.blit(subtitle, subtitle_rect)

        # Input for name
        input_rect = pygame.Rect(
            self.width//2 - 150, self.height//2 + 120, 300, 50)
        self._draw_input_box(screen, input_rect,
                             self._input_text, self._input_active)

        if not self._input_active:
            prompt = self._font_small.render(
                "Click to enter your name", True, (140, 150, 160))
            prompt.set_alpha(alpha)
            prompt_rect = prompt.get_rect(
                center=(self.width//2, self.height//2 + 185))
            screen.blit(prompt, prompt_rect)

        # Continue button
        if not self._input_active:
            btn_rect = self._get_continue_button_rect()
            btn_color = (0, 212, 255) if self._input_text else (60, 70, 80)
            pygame.draw.rect(screen, btn_color, btn_rect, border_radius=25)
            btn_text = self._font_medium.render(
                "Continue", True, (0, 0, 0) if self._input_text else (100, 100, 100))
            btn_text_rect = btn_text.get_rect(center=btn_rect.center)
            screen.blit(btn_text, btn_text_rect)

    def _render_voice_setup(self, screen: pygame.Surface):
        """Render voice setup screen."""
        card_rect = pygame.Rect(self.width//2 - 250,
                                self.height//2 - 200, 500, 400)
        self._draw_glass_card(screen, card_rect)

        self._draw_text_centered(screen, "Voice Setup", self._font_medium,
                                 card_rect.y + 30, (0, 212, 255))

        # Instructions
        instructions = [
            "Zara needs to hear you clearly.",
            "",
            "1. Make sure your microphone is connected",
            "2. Find a quiet spot",
            "3. Say 'Hey Zara' to wake me up",
        ]

        y = card_rect.y + 100
        for line in instructions:
            if line:
                text = self._font_small.render(line, True, (200, 210, 220))
                text_rect = text.get_rect(center=(self.width//2, y))
                screen.blit(text, text_rect)
            y += 35

        # Wake word display
        wake_rect = pygame.Rect(self.width//2 - 100,
                                card_rect.y + 280, 200, 40)
        pygame.draw.rect(screen, (0, 212, 255, 50),
                         wake_rect, border_radius=20)
        wake_text = self._font_small.render(
            f"Wake word: {self.profile.wake_word}", True, (0, 212, 255))
        wake_text_rect = wake_text.get_rect(center=wake_rect.center)
        screen.blit(wake_text, wake_text_rect)

        # Continue button
        btn_rect = self._get_continue_button_rect()
        pygame.draw.rect(screen, (0, 212, 255), btn_rect, border_radius=25)
        btn_text = self._font_medium.render("Continue", True, (0, 0, 0))
        btn_text_rect = btn_text.get_rect(center=btn_rect.center)
        screen.blit(btn_text, btn_text_rect)

    def _render_location(self, screen: pygame.Surface):
        """Render location permission screen."""
        card_rect = pygame.Rect(self.width//2 - 250,
                                self.height//2 - 180, 500, 360)
        self._draw_glass_card(screen, card_rect)

        self._draw_text_centered(screen, "Location Access", self._font_medium,
                                 card_rect.y + 30, (0, 212, 255))

        # Explanation
        explanation = [
            "Zara can use your location to provide:",
            "• Local weather forecasts",
            "• Timezone-aware scheduling",
            "• Local news and information",
            "• Contextual assistance",
            "",
            "Your location never leaves your device.",
        ]

        y = card_rect.y + 90
        for line in explanation:
            color = (200, 210, 220) if not line.startswith(
                "•") else (220, 230, 240)
            text = self._font_small.render(line, True, color)
            if line.startswith("•"):
                screen.blit(text, (card_rect.x + 40, y))
            else:
                text_rect = text.get_rect(center=(self.width//2, y))
                screen.blit(text, text_rect)
            y += 28

        # Detected location
        if self._detecting_location:
            status = "Detecting your location..."
        elif self._location_detected:
            loc = self._location_detected
            status = f"📍 {loc['city']}, {loc['country']}"
        else:
            status = "Location not detected"

        status_text = self._font_small.render(status, True, (0, 212, 255))
        status_rect = status_text.get_rect(
            center=(self.width//2, card_rect.y + 270))
        screen.blit(status_text, status_rect)

        # Buttons
        enable_rect = pygame.Rect(
            self.width//2 - 120, card_rect.bottom - 60, 240, 45)
        pygame.draw.rect(screen, (0, 212, 255), enable_rect, border_radius=22)
        enable_text = self._font_small.render(
            "Enable Location", True, (0, 0, 0))
        enable_text_rect = enable_text.get_rect(center=enable_rect.center)
        screen.blit(enable_text, enable_text_rect)

        skip_rect = self._get_skip_button_rect()
        skip_text = self._font_small.render("Skip", True, (100, 110, 120))
        skip_text_rect = skip_text.get_rect(center=skip_rect.center)
        screen.blit(skip_text, skip_text_rect)

    def _render_personality(self, screen: pygame.Surface):
        """Render personality selection."""
        card_rect = pygame.Rect(self.width//2 - 250,
                                self.height//2 - 180, 500, 360)
        self._draw_glass_card(screen, card_rect)

        self._draw_text_centered(screen, "Choose Zara's Style", self._font_medium,
                                 card_rect.y + 30, (0, 212, 255))

        options = [
            ("professional", "Professional", "Sharp, efficient, formal"),
            ("warm", "Warm", "Friendly, supportive, encouraging"),
            ("witty", "Witty", "Clever, playful, with dry humor"),
        ]

        y = card_rect.y + 100
        for value, name, desc in options:
            is_selected = self.profile.voice_style == value

            option_rect = pygame.Rect(self.width//2 - 150, y, 300, 70)
            bg_color = (0, 212, 255, 50) if is_selected else (30, 40, 50, 100)

            option_surf = pygame.Surface(
                (option_rect.width, option_rect.height), pygame.SRCALPHA)
            option_surf.fill(bg_color)
            pygame.draw.rect(option_surf, (0, 212, 255, 100) if is_selected else (60, 70, 80, 50),
                             option_surf.get_rect(), width=2, border_radius=10)
            screen.blit(option_surf, option_rect)

            name_text = self._font_small.render(
                name, True, (255, 255, 255) if is_selected else (200, 200, 200))
            screen.blit(name_text, (option_rect.x + 15, option_rect.y + 12))

            desc_text = self._font_small.render(desc, True, (150, 160, 170))
            screen.blit(desc_text, (option_rect.x + 15, option_rect.y + 38))

            y += 85

        btn_rect = self._get_continue_button_rect()
        pygame.draw.rect(screen, (0, 212, 255), btn_rect, border_radius=25)
        btn_text = self._font_medium.render("Complete Setup", True, (0, 0, 0))
        btn_text_rect = btn_text.get_rect(center=btn_rect.center)
        screen.blit(btn_text, btn_text_rect)
