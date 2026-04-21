"""Zara TTS — Edge-TTS with dual-channel pre-loading and zero-gap playback.

Enhancements:
- Aggressive interrupt with full queue flushing
"""

import os
import asyncio
import threading
from queue import Queue, Empty

import pygame
import pyautogui
import time
import state
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

# ── Edge-TTS ────────────────────────────────────────────────────────────────
try:
    import edge_tts
except ImportError:
    edge_tts = None
    print("[Zara TTS] WARNING: edge-tts not installed. Run 'pip install edge-tts'.")

VOICE = "en-US-JennyNeural"
# +5% rate = alert, -2Hz pitch = body/resonance
RATE = "+5%"
PITCH = "-2Hz"

ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")

_TTS_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Mixer Bootstrap ─────────────────────────────────────────────────────────
try:
    if not pygame.mixer.get_init():
        pygame.mixer.init(frequency=24000, channels=2)
except pygame.error:
    pass

# ── Threading Primitives ────────────────────────────────────────────────────
_text_queue: Queue = Queue()   # text phrases waiting to be rendered
_audio_queue: Queue = Queue()   # rendered .mp3 paths waiting to be played
_interrupted = threading.Event()
_renderer_thread: threading.Thread | None = None
_player_thread:   threading.Thread | None = None

# Global ducking state
_ducking_active = False
_ducking_lock = threading.Lock()
_ducking_enabled = False  # DISABLED BY DEFAULT - too buggy
_startup_complete = False
_saved_volume: float = -1.0

def enable_ducking():
    global _ducking_enabled
    _ducking_enabled = True
    print("[Voice] Volume ducking enabled")

def disable_ducking():
    global _ducking_enabled
    _ducking_enabled = False
    print("[Voice] Volume ducking disabled")

def _lower_media_volume():
    """Lower system volume when Zara starts speaking using pycaw."""
    global _ducking_active, _saved_volume
    if not _ducking_enabled:
        return
    with _ducking_lock:
        if _ducking_active:
            return
        try:
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
            _saved_volume = volume.GetMasterVolumeLevelScalar()
            target = max(0.0, _saved_volume - 0.4)   # duck by 40%
            volume.SetMasterVolumeLevelScalar(target, None)
            _ducking_active = True
            print(f"[Voice] Volume ducked from {_saved_volume:.2f} to {target:.2f}")
        except Exception as e:
            print(f"[Voice] Ducking failed: {e}")

def _restore_media_volume():
    """Restore media volume after Zara finishes speaking using pycaw."""
    global _ducking_active, _saved_volume
    if not _ducking_enabled:
        return
    with _ducking_lock:
        if not _ducking_active:
            return
        try:
            if _saved_volume >= 0.0:
                devices = AudioUtilities.GetSpeakers()
                interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                volume = cast(interface, POINTER(IAudioEndpointVolume))
                volume.SetMasterVolumeLevelScalar(_saved_volume, None)
                print(f"[Voice] Volume restored to {_saved_volume:.2f}")
            _ducking_active = False
            _saved_volume = -1.0
        except Exception as e:
            print(f"[Voice] Restore failed: {e}")


def mark_startup_complete():
    """Flag that the initial greeting is done."""
    global _startup_complete, _ducking_enabled
    _startup_complete = True
    _ducking_enabled = True
    print("[Voice] Startup complete — ducking enabled")


def _sync_talking_state(channels=None) -> None:
    """Reflect whether any queued or currently playing speech still exists."""
    try:
        if channels is None:
            any_busy = pygame.mixer.get_busy() if pygame.mixer.get_init() else False
        else:
            any_busy = any(ch.get_busy() for ch in channels)
    except Exception:
        any_busy = False

    state.set_talking(not _text_queue.empty()
                      or not _audio_queue.empty() or any_busy)


# ── Pre-connect ─────────────────────────────────────────────────────────────
def _warmup() -> None:
    """Fire a silent request at boot so the Azure WebSocket is pre-cached."""
    if edge_tts is None:
        return
    try:
        c = edge_tts.Communicate(" ", VOICE, rate=RATE, pitch=PITCH)
        path = os.path.join(_TTS_DIR, "_tts_warmup.mp3")
        asyncio.run(c.save(path))
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


threading.Thread(target=_warmup, daemon=True).start()





def _renderer_worker() -> None:
    """Renders text to in-memory audio (BytesIO)."""
    from io import BytesIO

    while True:
        try:
            text = _text_queue.get()
            if text is None:
                _text_queue.task_done()
                _audio_queue.put(None)
                _sync_talking_state()
                break

            if _interrupted.is_set():
                _text_queue.task_done()
                _sync_talking_state()
                continue

            try:
                buf = BytesIO()
                # 1. Try ElevenLabs if API key is present
                if ELEVENLABS_API_KEY:
                    audio_data = asyncio.run(_render_elevenlabs(text))
                    if audio_data:
                        buf.write(audio_data)
                    else:
                        # Fallback to Edge-TTS if ElevenLabs failed
                        comm = edge_tts.Communicate(text, VOICE, rate=RATE, pitch=PITCH)
                        for chunk in asyncio.run(_collect_audio(comm)):
                            if _interrupted.is_set(): break
                            buf.write(chunk)
                # 2. Otherwise use Edge-TTS
                elif edge_tts:
                    comm = edge_tts.Communicate(text, VOICE, rate=RATE, pitch=PITCH)
                    for chunk in asyncio.run(_collect_audio(comm)):
                        if _interrupted.is_set(): break
                        buf.write(chunk)
                else:
                    print("[Zara TTS] No renderer available.")
                    _text_queue.task_done()
                    continue

                buf.seek(0)
            except Exception as e:
                print(f"[Zara TTS] render error: {e}")
                _text_queue.task_done()
                _sync_talking_state()
                continue

            if _interrupted.is_set():
                _text_queue.task_done()
                _sync_talking_state()
                continue

            _audio_queue.put(buf)
            _text_queue.task_done()
            _sync_talking_state()

        except Exception as e:
            print(f"[Zara TTS] renderer crash: {e}")
            _sync_talking_state()
            time.sleep(1)
            print(f"[Zara TTS] renderer crash: {e}")
            _sync_talking_state()


async def _collect_audio(comm) -> list[bytes]:
    """Collect raw audio bytes from the Edge-TTS stream."""
    chunks = []
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            chunks.append(chunk["data"])
    return chunks


async def _render_elevenlabs(text: str) -> bytes:
    """Render text using ElevenLabs streaming API."""
    import httpx
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}/stream"
    headers = {"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"}
    body = {
        "text": text,
        "model_id": "eleven_turbo_v2",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
    }
    try:
        async with httpx.AsyncClient() as client:
            async with client.stream("POST", url, json=body, headers=headers) as r:
                if r.status_code != 200:
                    print(f"[Zara TTS] ElevenLabs error: {r.status_code}")
                    return b""
                return await r.aread()
    except Exception as e:
        print(f"[Zara TTS] ElevenLabs connection error: {e}")
        return b""


# ── Player Thread (Dual-Channel Pre-loading) ────────────────────────────────
def _player_worker() -> None:
    """Plays segments back-to-back with zero gap."""
    channels = [pygame.mixer.Channel(0), pygame.mixer.Channel(1)]
    current_ch = 0

    while True:
        try:
            audio_buf = _audio_queue.get()
            if audio_buf is None:
                _audio_queue.task_done()
                _sync_talking_state(channels)
                break

            if _interrupted.is_set():
                _audio_queue.task_done()
                _sync_talking_state(channels)
                continue

            try:
                sound = pygame.mixer.Sound(audio_buf)
                ch = channels[current_ch % 2]

                # Wait for previous channel to finish
                while ch.get_busy():
                    if _interrupted.is_set():
                        ch.stop()
                        break
                    pygame.time.wait(10)

                if not _interrupted.is_set():
                    ch.play(sound)
                    current_ch += 1

                    # Wait for THIS sound to finish
                    while ch.get_busy():
                        if _interrupted.is_set():
                            ch.stop()
                            break
                        pygame.time.wait(10)

            except Exception as e:
                print(f"[Zara TTS] playback error: {e}")

            _audio_queue.task_done()
            _sync_talking_state(channels)

            # CHECK IF ALL AUDIO IS DONE - RESTORE VOLUME
            if _audio_queue.empty() and _text_queue.empty():
                pygame.mixer.stop()  # Ensure hardware is clear
                state.set_talking(False)  # Force mic to open
                _restore_media_volume()  # ← RESTORE VOLUME WHEN DONE

        except Exception as e:
            print(f"[Zara TTS] player crash: {e}")
            state.set_talking(False)
            # DO NOT restore here — queue-empty path handles it


# ── Thread Lifecycle ────────────────────────────────────────────────────────
def _ensure_workers() -> None:
    global _renderer_thread, _player_thread
    if _renderer_thread is None or not _renderer_thread.is_alive():
        while not _text_queue.empty():   # drain stale items first
            try:
                _text_queue.get_nowait()
                _text_queue.task_done()
            except:
                break
        _renderer_thread = threading.Thread(
            target=_renderer_worker, daemon=True)
        _renderer_thread.start()
    if _player_thread is None or not _player_thread.is_alive():
        while not _audio_queue.empty():
            try:
                _audio_queue.get_nowait()
                _audio_queue.task_done()
            except:
                break
        _player_thread = threading.Thread(target=_player_worker, daemon=True)
        _player_thread.start()


_ensure_workers()


# ── Public API ──────────────────────────────────────────────────────────────

def interrupt() -> None:
    """Immediately silence Zara, flush all queues aggressively."""
    _interrupted.set()

    # Stop all mixer channels — VIOLENT SILENCE
    try:
        pygame.mixer.stop()
    except Exception:
        pass

    try:
        pygame.mixer.music.stop()
    except Exception:
        pass

    # Aggressively drain both queues so she doesn't resume old sentences
    # Clear text queue (sentences waiting to be rendered)
    while True:
        try:
            _text_queue.get_nowait()
            _text_queue.task_done()
        except Empty:
            break

    # Clear audio queue (rendered audio waiting to be played)
    while True:
        try:
            _audio_queue.get_nowait()
            _audio_queue.task_done()
        except Empty:
            break

    state.set_talking(False)
    print("[Voice] Interrupted — audio killed, queues flushed.")


def speak(text: str) -> None:
    """Queue a sentence for rendering + playback."""
    if not text or not str(text).strip():
        return

    # ENSURE MIXER IS INITIALIZED
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=24000, channels=2)
            print("[Voice] Mixer re-initialized")
    except Exception as e:
        print(f"[Voice] Mixer init failed: {e}")
        pygame.mixer.init(frequency=24000, channels=2)

    _interrupted.clear()
    state.set_talking(True)

    # Only duck after startup is complete
    if _startup_complete:
        _lower_media_volume()

    _ensure_workers()
    _text_queue.put(str(text).strip())
    _sync_talking_state()
