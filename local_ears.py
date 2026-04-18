"""Friday Ears — Continuous background listener with Silero VAD + Groq Whisper.

Enhancements:
- Dynamic VAD threshold (lower when Friday is talking)
- Frequency guard prevents self-interruption
- Memory-based transcription (no disk I/O)
- Faster silence timeout (0.7s)
"""

import pyaudio
import torch
import numpy as np
import time
import wave
import os
import threading
import requests
import io
from queue import Queue

import state
import local_voice

# .env Auto-loader
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# VAD Lazy Loader
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
            if any(hw in name for hw in ("Array", "Realtek", "Built-in", "Microphone")):
                return i
    return None


class ContinuousListener:
    """Always-on VAD listener with smart interruption handling."""

    CHUNK = 512
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000
    SILENCE_TIMEOUT = 0.7       # Faster response - was 1.2
    PRE_BUFFER = 0.3            # Pop filter - was 0.5
    MIN_SPEECH_DURATION = 0.5
    VAD_THRESHOLD_NORMAL = 0.85
    VAD_THRESHOLD_TALKING = 0.70  # Less sensitive when Friday is speaking
    TTS_FREQ_RANGE = (190, 230)   # Friday's voice frequency range

    def __init__(self, ui=None):
        self.ui = ui
        self.result_queue: Queue = Queue()
        self._thread: threading.Thread | None = None
        self._running = False
        self._boot_time = time.time()
        self._last_interrupt_time = 0
        self._interrupt_cooldown = 2.0  # Seconds between interrupts

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[Ear] Continuous listener started (enhanced).")

    def stop(self) -> None:
        self._running = False

    def _calibrate_microphone(self, pa, stream) -> None:
        """Calibrate VAD threshold based on actual room noise."""
        print("[Ear] Calibrating microphone... Please remain silent for 3 seconds.")

        noise_samples = []
        for _ in range(30):  # 3 seconds at 10 chunks per second
            try:
                data = stream.read(self.CHUNK, exception_on_overflow=False)
                pcm = np.frombuffer(data, dtype=np.int16)
                noise_samples.append(np.abs(pcm).mean())
            except Exception:
                pass

        if noise_samples:
            avg_noise = np.mean(noise_samples)
            self.VAD_THRESHOLD_NORMAL = max(
                0.75, min(0.90, 0.80 + avg_noise / 10000))
            self.VAD_THRESHOLD_TALKING = max(
                0.55, self.VAD_THRESHOLD_NORMAL - 0.15)
            print(
                f"[Ear] Calibrated - Noise floor: {avg_noise:.1f}, Threshold: {self.VAD_THRESHOLD_NORMAL:.2f}")

    def _loop(self) -> None:
        pa = pyaudio.PyAudio()
        mic_idx = _get_mic_index(pa)

        stream = pa.open(
            format=self.FORMAT, channels=self.CHANNELS,
            rate=self.RATE, input=True,
            input_device_index=mic_idx,
            frames_per_buffer=self.CHUNK,
        )

        self._calibrate_microphone(pa, stream)
        vad = _get_vad()
        print("[Ear] ALWAYS LISTENING - Circular buffer active...")

        CIRCULAR_BUFFER_SECONDS = 3.0
        circular_buffer_size = int(
            self.RATE / self.CHUNK * CIRCULAR_BUFFER_SECONDS)
        circular_buffer = []

        while self._running:
            frames = []
            has_started = False
            speech_duration = 0.0
            silence_duration = 0.0
            vocalizing_accum = 0.0
            consecutive_speech_frames = 0

            while self._running:
                try:
                    data = stream.read(self.CHUNK, exception_on_overflow=False)
                except Exception:
                    break

                circular_buffer.append(data)
                if len(circular_buffer) > circular_buffer_size:
                    circular_buffer.pop(0)

                pcm = np.frombuffer(data, dtype=np.int16)
                tensor = torch.from_numpy(pcm.astype(np.float32) / 32768.0)
                confidence = vad(tensor, self.RATE).item()

                is_friday_talking = getattr(state.is_talking, 'value', False)

                if is_friday_talking:
                    energy = np.sqrt(np.mean(pcm.astype(np.float32) ** 2))
                    if confidence > 0.70 and energy > 500:
                        fft = np.fft.rfft(pcm)
                        freqs = np.fft.rfftfreq(len(pcm), 1.0 / self.RATE)
                        if len(fft) > 0:
                            fft_magnitude = np.abs(fft)
                            dominant_freq = freqs[np.argmax(fft_magnitude)]
                            if 85 < dominant_freq < 400:
                                now = time.time()
                                if now - self._last_interrupt_time > self._interrupt_cooldown:
                                    local_voice.interrupt()
                                    self._last_interrupt_time = now
                                    print(
                                        f"[Ear] Interrupted — human voice at {dominant_freq:.1f}Hz, energy: {energy:.0f}")
                                    consecutive_speech_frames = 0
                    continue

                if confidence > self.VAD_THRESHOLD_NORMAL:
                    consecutive_speech_frames += 1
                    if consecutive_speech_frames >= 3:
                        vocalizing_accum += self.CHUNK / self.RATE
                        if vocalizing_accum >= 0.05:
                            if not has_started:
                                has_started = True
                                frames = list(circular_buffer) + frames
                                if self.ui:
                                    self.ui.set_state("LISTENING")

                            speech_duration += self.CHUNK / self.RATE
                            silence_duration = 0.0
                            frames.append(data)
                else:
                    consecutive_speech_frames = 0
                    if has_started:
                        frames.append(data)
                        silence_duration += self.CHUNK / self.RATE
                        if silence_duration > self.SILENCE_TIMEOUT:
                            break
                    else:
                        vocalizing_accum = 0.0

            if not frames or speech_duration < self.MIN_SPEECH_DURATION:
                continue

            total_energy = 0
            for frame in frames:
                pcm = np.frombuffer(frame, dtype=np.int16)
                total_energy += np.sqrt(np.mean(pcm.astype(np.float32) ** 2))
            avg_energy = total_energy / len(frames)

            if avg_energy < 100:
                print(
                    f"[Ear] Discarding low-energy audio (energy: {avg_energy:.0f})")
                continue

            text = self._transcribe_memory(frames, pa)

            if text and len(text) >= 3:
                wake_words = ["friday", "hey friday",
                              "okay friday", "hi friday", "hello friday"]
                text_lower = text.lower()
                for wake in wake_words:
                    if text_lower.startswith(wake):
                        text = text[len(wake):].strip()
                        print(f"[Ear] Removed wake word '{wake}'")
                        break

                if text_lower.startswith("friday"):
                    text = text[6:].strip().lstrip(",.!? ")

                HALLUCINATIONS = [
                    "thank you", "thanks", "thanks for watching", "bye", "you",
                    "the end", "subscribe", "silence", "...", "um", "hmm",
                    "ਸ੍ਰੇ", "োরে", "sequestação", "subtitle", "captions"
                ]

                text_stripped = text.lower().strip().rstrip(".!?,")
                if text_stripped in HALLUCINATIONS or len(text_stripped) < 3:
                    print(f"[Ear] Discarding hallucination: '{text}'")
                    continue

                ascii_count = sum(1 for c in text if ord(c) < 128)
                if ascii_count / len(text) < 0.5:
                    print(f"[Ear] Discarding non-ASCII gibberish: '{text}'")
                    continue

                STOP_COMMANDS = ["stop", "shut up", "quiet",
                                 "silence", "enough", "be quiet"]
                if text_stripped in STOP_COMMANDS:
                    local_voice.interrupt()
                    print("[Ear] Stop command detected")
                    continue

                print(f"\nYou: {text}")
                self.result_queue.put(text)
                for wake in wake_words:
                    if text_lower.startswith(wake):
                        text = text[len(wake):].strip()
                        print(
                            f"[Ear] Removed wake word '{wake}', remaining: '{text}'")
                        break

                if text_lower.startswith("friday") and not text_lower.startswith(tuple(wake_words)):
                    text = text[7:].strip().lstrip(",.!? ")
                    print(f"[Ear] Removed 'Friday', remaining: '{text}'")

            # NEW: Hard-coded stop commands
            STOP_COMMANDS = [
                "stop", "shut up", "quiet", "silence", "enough",
                "be quiet", "hush", "shhh", "stfu"
            ]
            if text and text.lower().strip().rstrip(".!?") in STOP_COMMANDS:
                local_voice.interrupt()
                print("[Ear] Stop command detected")
                continue

            if not text or len(text) < 3:
                continue

            # Hallucination filter
            HALLUCINATIONS = {
                "thank you", "thanks", "thanks for watching", "bye", "you",
                "the end", "subscribe", "silence", "...", "um", "hmm"
            }
            if text.lower().strip().rstrip(".!?,") in HALLUCINATIONS:
                continue

            stripped = text.strip()
            if stripped.isdigit() or len(set(stripped.replace(" ", ""))) <= 1:
                continue

            print(f"\nYou: {text}")
            self.result_queue.put(text)

        stream.stop_stream()
        stream.close()
        pa.terminate()

    def _transcribe_memory(self, frames: list, pa: pyaudio.PyAudio) -> str:
        """Transcribe directly from memory - no disk I/O."""
        if not GROQ_API_KEY:
            print("[Ear] GROQ_API_KEY missing")
            return ""

        try:
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, 'wb') as wf:
                wf.setnchannels(self.CHANNELS)
                wf.setsampwidth(pa.get_sample_size(self.FORMAT))
                wf.setframerate(self.RATE)
                wf.writeframes(b''.join(frames))
            wav_buffer.seek(0)

            resp = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                files={"file": ("audio.wav", wav_buffer, "audio/wav")},
                data={"model": "whisper-large-v3"},
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json().get("text", "").strip()
            else:
                print(
                    f"[Ear] Groq error {resp.status_code}: {resp.text[:100]}")
                return ""
        except Exception as e:
            print(f"[Ear] Transcription error: {e}")
            return ""


_TTS_DIR = os.path.dirname(os.path.abspath(__file__))
_singleton = None


def get_listener(ui=None) -> ContinuousListener:
    global _singleton
    if _singleton is None:
        _singleton = ContinuousListener(ui=ui)
    return _singleton
