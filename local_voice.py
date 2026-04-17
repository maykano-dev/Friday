"""Friday TTS — Edge-TTS with chunked sentence streaming via pygame.mixer.

The speak() function accepts raw text of any length. It splits on sentence
boundaries (. ? ! , \n) and feeds each mini-phrase into a background queue.
The playback worker renders each chunk through Edge-TTS asynchronously and
plays it via pygame.mixer.music so phrases overlap seamlessly.
"""

import os
import re
import asyncio
import threading
from queue import Queue, Empty

import pygame
import state

# ── Edge-TTS Import ─────────────────────────────────────────────────────────
try:
    import edge_tts
except ImportError:
    edge_tts = None
    print("[Friday TTS] WARNING: edge-tts not installed. Run 'pip install edge-tts'.")

VOICE = "en-US-AriaNeural"

# ── Mixer Bootstrap ─────────────────────────────────────────────────────────
# pygame.mixer may already be initialised by the UI thread; guard against that.
try:
    if not pygame.mixer.get_init():
        pygame.mixer.init(frequency=24000)
except pygame.error:
    pass

# ── Internal State ──────────────────────────────────────────────────────────
_speech_queue: Queue = Queue()
_interrupted = False
_worker_thread: threading.Thread | None = None

# Sentence-boundary regex: splits on ". " / "? " / "! " / ", " / newline
# while keeping the delimiter attached to the preceding phrase.
_SPLIT_RE = re.compile(r'(?<=[.?!,])\s+|\n')


def _chunk_text(text: str) -> list[str]:
    """Split a block of text into speakable mini-phrases."""
    parts = _SPLIT_RE.split(text)
    return [p.strip() for p in parts if p.strip()]


def _render_and_play(text: str, index: int) -> None:
    """Use Edge-TTS to render `text` to an mp3, then play it blocking."""
    if edge_tts is None:
        return

    mp3_path = os.path.join(os.path.dirname(__file__), f"_tts_chunk_{index % 10}.mp3")

    # Edge-TTS is async — run in a throwaway event loop.
    communicate = edge_tts.Communicate(text, VOICE)
    asyncio.run(communicate.save(mp3_path))

    if _interrupted:
        return

    try:
        # Wait for any previous chunk to finish playing.
        while pygame.mixer.music.get_busy() and not _interrupted:
            pygame.time.wait(15)

        if _interrupted:
            return

        pygame.mixer.music.load(mp3_path)
        pygame.mixer.music.play()

        # Block until this chunk finishes (or we're interrupted).
        while pygame.mixer.music.get_busy() and not _interrupted:
            pygame.time.wait(15)
    except Exception as e:
        print(f"[Friday TTS] playback error: {e}")


def _playback_worker() -> None:
    """Daemon loop — pulls phrases from the queue and speaks them."""
    global _interrupted
    idx = 0
    while True:
        try:
            phrase = _speech_queue.get()
            if phrase is None:      # poison pill
                break
            if _interrupted:
                _speech_queue.task_done()
                continue

            _render_and_play(phrase, idx)
            idx += 1
            _speech_queue.task_done()

            # If queue is drained and nothing is playing, we're done talking.
            if _speech_queue.empty() and not pygame.mixer.music.get_busy():
                state.is_talking.value = False

        except Exception as e:
            print(f"[Friday TTS] worker error: {e}")
            state.is_talking.value = False


def _ensure_worker() -> None:
    global _worker_thread
    if _worker_thread is None or not _worker_thread.is_alive():
        _worker_thread = threading.Thread(target=_playback_worker, daemon=True)
        _worker_thread.start()


# Start the background worker immediately on import.
_ensure_worker()


# ── Public API ──────────────────────────────────────────────────────────────

def interrupt() -> None:
    """Immediately silence Friday and flush the queue."""
    global _interrupted
    _interrupted = True

    try:
        pygame.mixer.music.stop()
    except Exception:
        pass

    # Drain remaining phrases so they never play.
    while not _speech_queue.empty():
        try:
            _speech_queue.get_nowait()
            _speech_queue.task_done()
        except Empty:
            break

    state.is_talking.value = False


def speak(text: str) -> None:
    """Split `text` into sentence-level chunks and queue them for playback.

    Each chunk is rendered independently by Edge-TTS, which means the first
    phrase starts playing while later phrases are still being synthesised.
    """
    global _interrupted
    if not text or not str(text).strip():
        return

    _interrupted = False
    state.is_talking.value = True
    _ensure_worker()

    chunks = _chunk_text(str(text))
    for c in chunks:
        _speech_queue.put(c)
