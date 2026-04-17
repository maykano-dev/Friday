"""Friday - Global application state.

Contains globally shared states, specifically for real-time multiprocessing
data like audio amplitudes that cross subsystem boundaries.
"""

from typing import Any
import multiprocessing

current_volume: Any = multiprocessing.Value('d', 0.0)
is_talking: Any = multiprocessing.Value('b', False)
