"""Zara Wake Word Engine.

A dual-mode wake word detection system:
1. Primary: Picovoice Porcupine (Fast, Low-CPU, Offline).
2. Fallback: Silero VAD + SpeechRecognition + Whisper (if Porcupine key is missing).
"""

import os
import struct
import threading
from typing import Optional, Callable

try:
    import pvporcupine
    from pvrecorder import PvRecorder
    PICOVOICE_AVAILABLE = True
except ImportError:
    PICOVOICE_AVAILABLE = False

# Config
PORCUPINE_KEY = os.environ.get("PORCUPINE_API_KEY", "")

class WakeWordEngine:
    def __init__(self, callback: Callable[[], None]):
        self.callback = callback
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._mode = "porcupine" if PORCUPINE_KEY and PICOVOICE_AVAILABLE else "vad_whisper"
        self._recorder = None
        self._porcupine = None

    def start(self):
        if self._running:
            return
        self._running = True
        
        if self._mode == "porcupine":
            self._thread = threading.Thread(target=self._run_porcupine, daemon=True)
            print("[Wake Word] Starting in Porcupine mode")
        else:
            self._thread = threading.Thread(target=self._run_vad_whisper, daemon=True)
            print("[Wake Word] Starting in VAD+Whisper fallback mode")
            
        self._thread.start()

    def stop(self):
        self._running = False
        if self._recorder:
            try:
                self._recorder.delete()
            except:
                pass
        if self._porcupine:
            try:
                self._porcupine.delete()
            except:
                pass

    def _run_porcupine(self):
        try:
            # You can train a custom 'Zara' wake word at console.picovoice.ai
            # For now, we use a built-in one if a custom path isn't provided.
            zara_ppn = os.path.join(os.path.dirname(__file__), "zara_windows.ppn")
            
            if os.path.exists(zara_ppn):
                self._porcupine = pvporcupine.create(
                    access_key=PORCUPINE_KEY,
                    keyword_paths=[zara_ppn]
                )
            else:
                print(f"[Wake Word] Custom model not found at {zara_ppn}. Using default 'computer'.")
                self._porcupine = pvporcupine.create(
                    access_key=PORCUPINE_KEY,
                    keywords=["computer"]
                )

            self._recorder = PvRecorder(device_index=-1, frame_length=self._porcupine.frame_length)
            self._recorder.start()
            
            while self._running:
                pcm = self._recorder.read()
                result = self._porcupine.process(pcm)
                
                if result >= 0:
                    print("[Wake Word] Detected!")
                    self.callback()
                    
        except Exception as e:
            print(f"[Wake Word] Porcupine error: {e}")
            print("[Wake Word] Falling back to VAD...")
            self._mode = "vad_whisper"
            self._run_vad_whisper()

    def _run_vad_whisper(self):
        try:
            import speech_recognition as sr
            recognizer = sr.Recognizer()
            recognizer.energy_threshold = 300
            recognizer.dynamic_energy_threshold = True
            
            # Use Groq for fast whisper if available
            groq_key = os.environ.get("GROQ_API_KEY", "")
            
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=1.0)
                
                while self._running:
                    try:
                        audio = recognizer.listen(source, timeout=1.0, phrase_time_limit=3.0)
                        
                        # Only transcribe if we got audio
                        if groq_key:
                            from groq import Groq
                            client = Groq(api_key=groq_key)
                            import tempfile
                            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                                f.write(audio.get_wav_data())
                                temp_path = f.name
                                
                            with open(temp_path, "rb") as file:
                                transcription = client.audio.transcriptions.create(
                                    file=(os.path.basename(temp_path), file.read()),
                                    model="whisper-large-v3",
                                    response_format="text",
                                )
                            os.remove(temp_path)
                            text = transcription.lower()
                        else:
                            # Local offline fallback (slow)
                            text = recognizer.recognize_sphinx(audio).lower()
                            
                        if "zara" in text or "sara" in text or "computer" in text:
                            print("[Wake Word] Detected (VAD/Whisper)!")
                            self.callback()
                            
                    except sr.WaitTimeoutError:
                        continue
                    except Exception as e:
                        pass
        except Exception as e:
            print(f"[Wake Word] VAD/Whisper error: {e}")
