"""Friday TTS — Edge-TTS with lookahead downloading and instant interruption.

Architecture:
  1. Two background threads: a RENDERER and a PLAYER.
  2. The renderer pulls text from _text_queue, calls Edge-TTS, and pushes
     the resulting .mp3 path into _audio_queue.
  3. The player pulls .mp3 paths from _audio_queue and plays them via
     pygame.mixer.music.
  4. This means audio for Phrase N+1 is being downloaded while Phrase N
     is still playing — zero gap between phrases.
  5. A threading.Event (_interrupted) provides an instant kill-switch that
     both threads respect.
"""

import os
import asyncio
import threading
from queue import Queue, Empty

import pygame
import state

# ── Edge-TTS ────────────────────────────────────────────────────────────────
try:
    import edge_tts
except ImportError:
    edge_tts = None
    print("[Friday TTS] WARNING: edge-tts not installed. Run 'pip install edge-tts'.")

VOICE = "en-US-AriaNeural"
_TTS_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Mixer Bootstrap ─────────────────────────────────────────────────────────
try:
    if not pygame.mixer.get_init():
        pygame.mixer.init(frequency=24000)
except pygame.error:
    pass

# ── Threading Primitives ────────────────────────────────────────────────────
_text_queue: Queue  = Queue()   # text phrases waiting to be rendered
_audio_queue: Queue = Queue()   # rendered .mp3 paths waiting to be played
_interrupted = threading.Event()
_renderer_thread: threading.Thread | None = None
_player_thread:   threading.Thread | None = None


# ── Pre-connect Hack ────────────────────────────────────────────────────────
# Edge-TTS uses a WebSocket to the Azure endpoint. The first call has a
# ~300ms handshake penalty. We fire a silent warmup at import time so the
# connection is already cached when the user first speaks.
def _warmup() -> None:
    if edge_tts is None:
        return
    try:
        c = edge_tts.Communicate(" ", VOICE)
        warmup_path = os.path.join(_TTS_DIR, "_tts_warmup.mp3")
        asyncio.run(c.save(warmup_path))
        if os.path.exists(warmup_path):
            os.remove(warmup_path)
    except Exception:
        pass

threading.Thread(target=_warmup, daemon=True).start()


# ── Renderer Thread ─────────────────────────────────────────────────────────
def _renderer_worker() -> None:
    """Pulls text from _text_queue, renders to .mp3, pushes path to _audio_queue."""
    idx = 0
    while True:
        try:
            text = _text_queue.get()
            if text is None:  # poison pill
                _audio_queue.put(None)
                break

            if _interrupted.is_set():
                _text_queue.task_done()
                continue

            if edge_tts is None:
                _text_queue.task_done()
                continue

            mp3_path = os.path.join(_TTS_DIR, f"_tts_chunk_{idx % 10}.mp3")
            idx += 1

            try:
                communicate = edge_tts.Communicate(text, VOICE)
                asyncio.run(communicate.save(mp3_path))
            except Exception as e:
                print(f"[Friday TTS] render error: {e}")
                _text_queue.task_done()
                continue

            if _interrupted.is_set():
                _text_queue.task_done()
                continue

            _audio_queue.put(mp3_path)
            _text_queue.task_done()

        except Exception as e:
            print(f"[Friday TTS] renderer crash: {e}")


# ── Player Thread ───────────────────────────────────────────────────────────
def _player_worker() -> None:
    """Pulls .mp3 paths from _audio_queue and plays them sequentially."""
    while True:
        try:
            mp3_path = _audio_queue.get()
            if mp3_path is None:  # poison pill
                break

            if _interrupted.is_set():
                _audio_queue.task_done()
                continue

            try:
                pygame.mixer.music.load(mp3_path)
                pygame.mixer.music.play()

                while pygame.mixer.music.get_busy():
                    if _interrupted.is_set():
                        pygame.mixer.music.stop()
                        break
                    pygame.time.wait(15)
            except Exception as e:
                print(f"[Friday TTS] playback error: {e}")

            _audio_queue.task_done()

            # If both queues are empty and nothing is playing, we're done.
            if (_text_queue.empty() and _audio_queue.empty()
                    and not pygame.mixer.music.get_busy()):
                state.is_talking.value = False

        except Exception as e:
            print(f"[Friday TTS] player crash: {e}")
            state.is_talking.value = False


# ── Thread Lifecycle ────────────────────────────────────────────────────────
def _ensure_workers() -> None:
    global _renderer_thread, _player_thread
    if _renderer_thread is None or not _renderer_thread.is_alive():
        _renderer_thread = threading.Thread(target=_renderer_worker, daemon=True)
        _renderer_thread.start()
    if _player_thread is None or not _player_thread.is_alive():
        _player_thread = threading.Thread(target=_player_worker, daemon=True)
        _player_thread.start()

_ensure_workers()


# ── Public API ──────────────────────────────────────────────────────────────

def interrupt() -> None:
    """Immediately silence Friday, flush all queues."""
    _interrupted.set()

    try:
        pygame.mixer.music.stop()
    except Exception:
        pass

    # Drain both queues.
    for q in (_text_queue, _audio_queue):
        while not q.empty():
            try:
                q.get_nowait()
                q.task_done()
            except Empty:
                break

    state.is_talking.value = False


def speak(text: str) -> None:
    """Queue a phrase for rendering + playback.

    Because the renderer and player are separate threads, audio for phrase N+1
    is downloaded while phrase N is still playing.
    """
    if not text or not str(text).strip():
        return

    _interrupted.clear()
    state.is_talking.value = True
    _ensure_workers()
    _text_queue.put(str(text).strip())
