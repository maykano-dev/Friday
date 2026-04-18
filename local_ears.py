"""Friday Ears — Continuous background listener with Silero VAD + Groq Whisper.

Architecture:
  ContinuousListener runs on a daemon thread. It never stops monitoring the mic.
  When VAD detects human speech:
    1. If Friday is currently talking → fires interrupt() kill-switch instantly.
    2. Records until 1.2s of silence, then checks the hallucination guard.
    3. If audio < 1.0s of actual speech → discards (hallucination/noise).
    4. Otherwise → ships the .wav to Groq Whisper API and pushes the
       transcribed text into a result_queue for main.py to consume.
"""

import pyaudio
import torch
import numpy as np
import time
import wave
import os
import threading
import requests
from queue import Queue

import state
import local_voice

# ── .env Auto-loader ────────────────────────────────────────────────────────
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# ── VAD Lazy Loader ─────────────────────────────────────────────────────────
_vad_model = None


def _get_vad():
    global _vad_model
    if _vad_model is None:
        _vad_model, _ = torch.hub.load(
            repo_or_dir='snakers4/silero-vad',
            model='silero_vad',
            trust_repo=True,
        )
    return _vad_model


def _get_mic_index(pa: pyaudio.PyAudio) -> int | None:
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        if info['maxInputChannels'] > 0:
            name = info.get('name', '')
            if any(skip in name for skip in ("Stereo Mix", "Virtual", "ManyCam")):
                continue
            if any(hw in name for hw in ("Array", "Realtek", "Built-in")):
                return i
    return None


def _transcribe_wav(wav_path: str) -> str:
    """Send a .wav to Groq Whisper API and return the transcribed text."""
    if not GROQ_API_KEY:
        print("[Ear] GROQ_API_KEY missing — cannot transcribe.")
        return ""
    try:
        with open(wav_path, "rb") as f:
            resp = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                files={"file": ("audio.wav", f, "audio/wav")},
                data={"model": "whisper-large-v3"},
                timeout=15,
            )
        if resp.status_code == 200:
            return resp.json().get("text", "").strip()
        else:
            print(
                f"[Ear] Groq API error {resp.status_code}: {resp.text[:200]}")
            return ""
    except Exception as e:
        print(f"[Ear] transcription error: {e}")
        return ""


class ContinuousListener:
    """Always-on VAD listener that runs on a background daemon thread.

    Transcribed utterances are pushed into `self.result_queue`.
    """

    CHUNK = 512
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000
    SILENCE_TIMEOUT = 1.2       # seconds of silence to end an utterance
    PRE_BUFFER = 0.1            # ignore first 0.1s (pop filter)
    MIN_SPEECH_DURATION = 0.5   # require clearer speech before we treat it as intentional
    VAD_THRESHOLD = 0.65        # LOWERED: Much more sensitive to your voice

    def __init__(self, ui=None):
        self.ui = ui
        self.result_queue: Queue = Queue()
        self._thread: threading.Thread | None = None
        self._running = False
        self._boot_time = time.time()  # Track startup

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[Ear] Continuous listener started.")

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        """Infinite listen → detect → record → transcribe cycle."""
        pa = pyaudio.PyAudio()
        mic_idx = _get_mic_index(pa)

        stream = pa.open(
            format=self.FORMAT, channels=self.CHANNELS,
            rate=self.RATE, input=True,
            input_device_index=mic_idx,
            frames_per_buffer=self.CHUNK,
        )

        vad = _get_vad()
        print("Friday is listening...")

        while self._running:
            frames = []
            has_started = False
            speech_duration = 0.0
            silence_duration = 0.0
            vocalizing_accum = 0.0

            # ── Inner loop: one utterance ──
            while self._running:
                try:
                    data = stream.read(self.CHUNK, exception_on_overflow=False)
                except Exception:
                    break

                pcm = np.frombuffer(data, dtype=np.int16)
                tensor = torch.from_numpy(pcm.astype(np.float32) / 32768.0)
                confidence = vad(tensor, self.RATE).item()

                if confidence > self.VAD_THRESHOLD:
                    vocalizing_accum += self.CHUNK / self.RATE

                    if vocalizing_accum >= self.PRE_BUFFER:
                        if not has_started:
                            has_started = True
                            # Signal UI to turn RED for listening
                            if self.ui:
                                self.ui.set_state("LISTENING")
                            if getattr(state.is_talking, 'value', False):
                                local_voice.interrupt()
                                print(
                                    "[Ear] Interrupted Friday — user is speaking.")

                        speech_duration += self.CHUNK / self.RATE
                        silence_duration = 0.0
                        frames.append(data)
                else:
                    if has_started:
                        frames.append(data)
                        silence_duration += self.CHUNK / self.RATE
                        if silence_duration > self.SILENCE_TIMEOUT:
                            break  # end of utterance
                    else:
                        vocalizing_accum = 0.0  # reset pop filter

            # ── Hallucination guard ──
            if not frames or speech_duration < self.MIN_SPEECH_DURATION:
                continue

            # ── Save WAV and transcribe ──
            wav_path = os.path.join(_TTS_DIR, "_ear_temp.wav")
            try:
                wf = wave.open(wav_path, 'wb')
                wf.setnchannels(self.CHANNELS)
                wf.setsampwidth(pa.get_sample_size(self.FORMAT))
                wf.setframerate(self.RATE)
                wf.writeframes(b''.join(frames))
                wf.close()
            except Exception as e:
                print(f"[Ear] WAV write error: {e}")
                continue

            text = _transcribe_wav(wav_path)

            try:
                os.remove(wav_path)
            except OSError:
                pass

            # ── Text-level hallucination filter ──
            if not text or len(text) < 3:
                continue

            # Common Whisper phantom outputs on near-silent audio
            HALLUCINATIONS = {
                "thank you", "thanks", "thank you.", "thanks.",
                "thanks for watching", "thanks for watching.",
                "thank you for watching", "thank you for watching.",
                "grazie", "grazie.", "bye", "bye.", "you",
                "the end", "the end.", "subtitle", "subtitles",
                "subscribe", "like and subscribe",
                "silence", "...", "…",
                "੧", "੧ ੧ ੧", "\u0a67", "\u0a67 \u0a67 \u0a67",
                "বোর্তে", "বোর্তে বোর্তে বোর্তে",
                "up friday", "saya membuat",
                "you.", "i", "um", "hmm", "uh",
            }
            if text.lower().strip().rstrip(".!?,") in HALLUCINATIONS:
                continue

            # Discard if it's just a number or single repeated character
            stripped = text.strip()
            if stripped.isdigit() or (len(set(stripped.replace(" ", ""))) <= 1):
                continue

            print(f"\nYou: {text}")
            self.result_queue.put(text)

        stream.stop_stream()
        stream.close()
        pa.terminate()


# Module-level convenience path
_TTS_DIR = os.path.dirname(os.path.abspath(__file__))

# Legacy compatibility — old code that calls local_ears.listen_and_transcribe()
# will still work, but the preferred interface is ContinuousListener.
_singleton = None


def get_listener(ui=None) -> ContinuousListener:
    global _singleton
    if _singleton is None:
        _singleton = ContinuousListener(ui=ui)
    return _singleton
