"""Friday — Global application state.

Contains globally shared states, specifically for real-time multiprocessing
data like audio amplitudes that cross subsystem boundaries.
"""

from enum import Enum
from typing import Any
import multiprocessing


class FridayState(Enum):
    IDLE      = "IDLE"
    LISTENING = "LISTENING"
    THINKING  = "THINKING"
    SPEAKING  = "SPEAKING"


current_volume: Any = multiprocessing.Value('d', 0.0)
is_talking: Any = multiprocessing.Value('b', False)
media_playing: Any = multiprocessing.Value('b', False)


def set_talking(active: bool) -> None:
    """Centralize talking-state updates across audio subsystems."""
    is_talking.value = bool(active)


def set_media_playing(active: bool) -> None:
    """Track if media (music/video) is currently playing."""
    media_playing.value = bool(active)
