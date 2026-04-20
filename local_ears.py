"""Zara Ears — Continuous background listener with Silero VAD + Groq Whisper.

Complete rewrite with:
- Proper circular buffer (never miss first words)
- Smart wake word removal
- Garbage character filtering
- No duplicate code
- Reliable VAD calibration
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
    return 0  # Default to first available


class ContinuousListener:
    """Always-on VAD listener with proper circular buffer."""

    CHUNK = 512
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000
    SILENCE_TIMEOUT = 0.7
    PRE_BUFFER = 0.1
    MIN_SPEECH_DURATION = 0.4
    CIRCULAR_BUFFER_SECONDS = 2.5

    def __init__(self, ui=None):
        self.ui = ui
        self.result_queue: Queue = Queue()
        self._thread: threading.Thread | None = None
        self._running = False
        self._last_interrupt_time = 0
        self._interrupt_cooldown = 1.5

        # Dynamic thresholds - will be calibrated
        self.VAD_THRESHOLD_NORMAL = 0.82
        self.VAD_THRESHOLD_TALKING = 0.65

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[Ear] Continuous listener started.")

    def stop(self) -> None:
        self._running = False

    def _calibrate_microphone(self, pa, stream) -> None:
        """Calibrate VAD threshold based on room noise."""
        print("[Ear] Calibrating microphone... (stay silent)")

        noise_levels = []
        for _ in range(40):  # 4 seconds
            try:
                data = stream.read(self.CHUNK, exception_on_overflow=False)
                pcm = np.frombuffer(data, dtype=np.int16)
                noise_levels.append(np.abs(pcm).mean())
            except Exception:
                pass
            time.sleep(0.1)

        if noise_levels:
            avg_noise = np.mean(noise_levels)
            # Set thresholds based on noise floor
            self.VAD_THRESHOLD_NORMAL = max(
                0.75, min(0.88, 0.78 + avg_noise / 8000))
            self.VAD_THRESHOLD_TALKING = max(
                0.55, self.VAD_THRESHOLD_NORMAL - 0.12)
            print(
                f"[Ear] Calibrated - Noise: {avg_noise:.1f}, Normal: {self.VAD_THRESHOLD_NORMAL:.2f}, Talking: {self.VAD_THRESHOLD_TALKING:.2f}")

    def _clean_transcription(self, text: str) -> str | None:
        """Clean and validate transcribed text."""
        if not text or len(text) < 2:
            return None

        # Remove wake words
        wake_words = ["zara", "hey zara", "okay zara", "hi zara", "hello zara"]
        text_lower = text.lower().strip()

        matched_wake = False
        for wake in wake_words:
            if text_lower.startswith(wake):
                # Remove the wake word but preserve the command
                text = text[len(wake):].strip()
                text = text.lstrip(",.!?;: ")
                if text:
                    print(f"[Ear] Command after wake word: '{text}'")
                else:
                    print(f"[Ear] Wake word only - no command")
                matched_wake = True
                break

        # Handle just "Zara" (catchall if it wasn't in the list or if list check skipped)
        if not matched_wake and text_lower.startswith("zara"):
            text = text[4:].strip()
            text = text.lstrip(",.!?;: ")
            if text:
                print(f"[Ear] Command after wake word: '{text}'")
            else:
                print(f"[Ear] Wake word only - no command")

        # Clean non-ASCII garbage
        ascii_chars = [c for c in text if ord(c) < 128]
        if len(ascii_chars) == 0:
            return None

        ascii_ratio = len(ascii_chars) / len(text) if text else 0
        if ascii_ratio < 0.6:
            cleaned = ''.join(ascii_chars).strip()
            if len(cleaned) < 3:
                return None
            print(f"[Ear] Cleaned non-ASCII: '{text[:30]}...' -> '{cleaned}'")
            text = cleaned

        # Stop commands
        stop_commands = ["stop", "shut up", "quiet",
                         "silence", "enough", "be quiet", "hush", "shhh"]
        if text.lower().strip().rstrip(".!?") in stop_commands:
            local_voice.interrupt()
            print("[Ear] Stop command detected")
            return None

        # Hallucination filter
        hallucinations = ["thank you", "thanks", "thanks for watching", "bye", "you",
                          "the end", "subscribe", "...", "um", "hmm", "captions", "subtitle"]
        if text.lower().strip().rstrip(".!?,") in hallucinations:
            print(f"[Ear] Hallucination filtered: '{text}'")
            return None

        return text.strip()

    def _should_interrupt(self, pcm: np.ndarray, confidence: float) -> bool:
        """Determine if we should interrupt Zara."""
        # Require HIGHER confidence when Zara is talking
        if confidence < 0.75:  # ← Increased from 0.65
            return False

        # Require MORE energy (voice is louder than background music)
        energy = np.sqrt(np.mean(pcm.astype(np.float32) ** 2))
        if energy < 800:  # ← Increased from 400
            return False

        fft = np.fft.rfft(pcm)
        if len(fft) == 0:
            return False

        freqs = np.fft.rfftfreq(len(pcm), 1.0 / self.RATE)
        fft_magnitude = np.abs(fft)
        dominant_freq = freqs[np.argmax(fft_magnitude)]

        # Check if the sound has harmonics (music has rich harmonics, voice is simpler)
        # Calculate spectral flatness - voice is less flat than music
        if len(fft_magnitude) > 10:
            spectral_flatness = np.exp(np.mean(np.log(fft_magnitude + 1e-10))) / (
                np.mean(fft_magnitude) + 1e-10)

            # Music tends to have higher spectral flatness (> 0.3)
            # Voice is more peaked (lower flatness)
            if spectral_flatness > 0.25:
                print(
                    f"[Ear] Detected music (flatness: {spectral_flatness:.2f}) - ignoring")
                return False

        # Human voice range: 85-400 Hz
        if 85 < dominant_freq < 400:
            now = time.time()
            if now - self._last_interrupt_time > self._interrupt_cooldown:
                self._last_interrupt_time = now
                print(f"[Ear] Human voice detected at {dominant_freq:.1f}Hz")
                return True

        return False

    def _loop(self) -> None:
        pa = pyaudio.PyAudio()
        mic_idx = _get_mic_index(pa)

        if mic_idx is None:
            print("[Ear] ERROR: No microphone found!")
            return

        stream = pa.open(
            format=self.FORMAT, channels=self.CHANNELS,
            rate=self.RATE, input=True,
            input_device_index=mic_idx,
            frames_per_buffer=self.CHUNK,
        )

        self._calibrate_microphone(pa, stream)
        vad = _get_vad()

        circular_size = int(self.RATE / self.CHUNK *
                            self.CIRCULAR_BUFFER_SECONDS)
        circular_buffer = []

        print("[Ear] Listening... (speak naturally)")
        print("[Ear] DEBUG: VAD loaded, circular buffer ready")

        # After Zara finishes speaking, add a cooldown
        was_talking = False

        while self._running:
            frames = []
            circular_buffer.clear()
            has_started = False
            speech_duration = 0.0
            silence_duration = 0.0
            vocalizing_accum = 0.0
            speech_frames = 0

            while self._running:
                try:
                    data = stream.read(self.CHUNK, exception_on_overflow=False)
                except Exception as e:
                    print(f"[Ear] Stream read error: {e}")
                    break

                # Maintain circular buffer
                circular_buffer.append(data)
                if len(circular_buffer) > circular_size:
                    circular_buffer.pop(0)

                pcm = np.frombuffer(data, dtype=np.int16)
                tensor = torch.from_numpy(pcm.astype(np.float32) / 32768.0)
                confidence = vad(tensor, self.RATE).item()

                is_zara_talking = getattr(state.is_talking, 'value', False)

                if is_zara_talking:
                    was_talking = True
                    # INTERRUPTION CHECK
                    if self._should_interrupt(pcm, confidence):
                        local_voice.interrupt()
                        print(f"[Ear] Interrupted Zara")
                    continue
                elif was_talking:
                    # Zara just finished talking - add a short cooldown
                    was_talking = False
                    time.sleep(0.3)  # 300ms cooldown for echo to dissipate
                    # Clear any audio buffers
                    circular_buffer.clear()
                    continue

                # NORMAL LISTENING
                media_is_playing = getattr(state.media_playing, 'value', False)

                # If media is playing, be MORE selective about what counts as speech
                if media_is_playing:
                    threshold = self.VAD_THRESHOLD_NORMAL + 0.05  # Stricter
                    min_speech_frames = 5  # Need more consecutive frames
                else:
                    threshold = self.VAD_THRESHOLD_NORMAL
                    min_speech_frames = 2

                # DEBUG: Print confidence occasionally
                if confidence > 0.5:
                    print(
                        f"[Ear] DEBUG: High confidence detected: {confidence:.2f}")

                if confidence > threshold:
                    speech_frames += 1

                    # Need consecutive frames to confirm speech
                    if speech_frames >= min_speech_frames:
                        vocalizing_accum += self.CHUNK / self.RATE

                        if vocalizing_accum >= self.PRE_BUFFER:
                            if not has_started:
                                has_started = True
                                # PREPEND circular buffer!
                                frames = list(circular_buffer)
                                if self.ui:
                                    self.ui.set_state("LISTENING")
                                print(
                                    f"[Ear] DEBUG: Speech started! Captured {len(circular_buffer)} pre-frames")

                            speech_duration += self.CHUNK / self.RATE
                            silence_duration = 0.0
                            frames.append(data)
                else:
                    speech_frames = 0
                    if has_started:
                        frames.append(data)
                        silence_duration += self.CHUNK / self.RATE
                        if silence_duration > self.SILENCE_TIMEOUT:
                            print(
                                f"[Ear] DEBUG: Silence timeout, processing {len(frames)} frames")
                            break
                    else:
                        vocalizing_accum = 0.0

            # Process captured speech
            if not frames or speech_duration < self.MIN_SPEECH_DURATION:
                print("[Ear] DEBUG: Not enough speech, skipping")
                continue

            # Check audio energy
            total_energy = sum(np.sqrt(np.mean(np.frombuffer(
                f, dtype=np.int16).astype(np.float32) ** 2)) for f in frames)
            avg_energy = total_energy / len(frames)
            if avg_energy < 80:
                print(f"[Ear] Low energy ({avg_energy:.0f}), discarding")
                continue

            # Transcribe
            print(f"[Ear] DEBUG: Transcribing {len(frames)} frames...")
            text = self._transcribe_memory(frames, pa)
            print(f"[Ear] DEBUG: Raw transcription: '{text}'")

            if not text:
                print("[Ear] DEBUG: No transcription returned")
                continue

            # Clean and validate
            cleaned = self._clean_transcription(text)
            print(f"[Ear] DEBUG: Cleaned: '{cleaned}'")

            if not cleaned:
                print("[Ear] DEBUG: Transcription filtered out")
                continue

            print(f"\n🗣️ You: {cleaned}")
            self.result_queue.put(cleaned)

        stream.stop_stream()
        stream.close()
        pa.terminate()

    def _transcribe_memory(self, frames: list, pa: pyaudio.PyAudio) -> str:
        """Transcribe directly from memory."""
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
                data={"model": "whisper-large-v3", "language": "en"},
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json().get("text", "").strip()
            else:
                print(f"[Ear] Groq error {resp.status_code}")
                return ""
        except Exception as e:
            print(f"[Ear] Transcription error: {e}")
            return ""


_singleton = None


def get_listener(ui=None) -> ContinuousListener:
    global _singleton
    if _singleton is None:
        _singleton = ContinuousListener(ui=ui)
    return _singleton
