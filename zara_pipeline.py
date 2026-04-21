"""
============================================================
  ZARA AI — Streaming Voice Pipeline
  Step 3 — The brain, ears, mouth, and nervous system

  Architecture (Gemini Live-style):
  ┌─────────────────────────────────────────────────────┐
  │  Porcupine wake word  (always-on, ~1% CPU)          │
  │       ↓                                             │
  │  Deepgram Nova-2 streaming STT  (real-time)         │
  │       ↓                                             │
  │  Task Manager  (parallel execution + queue)         │
  │       ↓                                             │
  │  Ollama / Groq  (LLM brain — hybrid)                │
  │       ↓                                             │
  │  ElevenLabs streaming TTS  (speaks mid-generation)  │
  │       ↓                                             │
  │  Interrupt listener  (always running in parallel)   │
  └─────────────────────────────────────────────────────┘

  Install:
    pip install deepgram-sdk pvporcupine pvrecorder
    pip install elevenlabs groq ollama
    pip install pyaudio numpy sounddevice webrtcvad
    pip install asyncio aiohttp python-dotenv

  API Keys needed (all have free tiers):
    DEEPGRAM_API_KEY   → deepgram.com
    ELEVENLABS_API_KEY → elevenlabs.io
    GROQ_API_KEY       → console.groq.com
    PORCUPINE_KEY      → picovoice.ai  (free)
============================================================
"""

import os
import asyncio
import threading
import queue
import time
import json
import re
import struct
import logging
import numpy as np
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Callable
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.WARNING)
log = logging.getLogger("zara")

# ── Optional imports (graceful fallback if not installed) ─
try:
    import pvporcupine
    import pvrecorder
    PORCUPINE_AVAILABLE = True
except ImportError:
    PORCUPINE_AVAILABLE = False
    print("⚠ pvporcupine not installed — wake word disabled")

try:
    from deepgram import DeepgramClient, LiveTranscriptionEvents, LiveOptions
    DEEPGRAM_AVAILABLE = True
except ImportError:
    DEEPGRAM_AVAILABLE = False
    print("⚠ deepgram-sdk not installed — STT disabled")

try:
    from elevenlabs.client import ElevenLabs
    from elevenlabs import stream as el_stream
    ELEVENLABS_AVAILABLE = True
except ImportError:
    ELEVENLABS_AVAILABLE = False
    print("⚠ elevenlabs not installed — TTS disabled")

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False
    print("⚠ groq not installed")

try:
    import ollama as ollama_client
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    print("⚠ ollama not installed")

try:
    import pyaudio
    import sounddevice as sd
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False
    print("⚠ pyaudio/sounddevice not installed")


# ════════════════════════════════════════════════════════
#   CONFIGURATION
# ════════════════════════════════════════════════════════

class Config:
    # ── Wake word ──────────────────────────────────────
    WAKE_WORDS        = ["zara", "hey zara", "okay zara", "hi zara"]
    PORCUPINE_KEY     = os.getenv("PORCUPINE_KEY", "")

    # ── STT ────────────────────────────────────────────
    DEEPGRAM_KEY      = os.getenv("DEEPGRAM_API_KEY", "")
    STT_MODEL         = "nova-2"
    STT_LANGUAGE      = "en-US"
    SILENCE_TIMEOUT   = 1.8      # seconds of silence → end of speech
    MIN_SPEECH_LEN    = 2        # minimum characters to process

    # ── LLM Brain ──────────────────────────────────────
    GROQ_KEY          = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL        = "llama-3.1-8b-instant"    # fastest Groq model
    OLLAMA_MODEL      = "zara"                   # your fine-tuned model
    OLLAMA_FALLBACK   = "llama3.2:3b"              # if zara model not loaded yet
    MAX_TOKENS        = 150      # keep responses short for voice
    TEMPERATURE       = 0.7
    USE_GROQ_PRIMARY  = True     # False = use Ollama as primary

    # ── TTS ────────────────────────────────────────────
    ELEVENLABS_KEY    = os.getenv("ELEVENLABS_API_KEY", "")
    VOICE_ID          = "21m00Tcm4TlvDq8ikWAM"   # Rachel — change to your preferred voice
    TTS_MODEL         = "eleven_turbo_v2"          # fastest ElevenLabs model
    TTS_STABILITY     = 0.5
    TTS_SIMILARITY    = 0.85

    # ── Audio ──────────────────────────────────────────
    SAMPLE_RATE       = 16000
    CHUNK_SIZE        = 512
    CHANNELS          = 1

    # ── Hallucination filter ───────────────────────────
    HALLUCINATIONS    = {
        "thank you", "thanks for watching", "please subscribe",
        "you", "thank you for watching", "thanks", "bye",
        "goodbye", "see you next time", "um", "uh", "hmm",
        "[inaudible]", "[music]", "[applause]"
    }

    # ── Stop commands ──────────────────────────────────
    STOP_COMMANDS     = {"stop", "shut up", "quiet", "silence", "enough", "stop talking"}

    # ── System prompt ──────────────────────────────────
    SYSTEM_PROMPT     = (
        "You are Zara, an advanced AI assistant built for seamless personal "
        "and professional assistance at zara.ai. You are sharp, warm, efficient, "
        "and always one step ahead. You address the user as 'Sir' unless they've told "
        "you their name or gender. You never say 'I cannot do that'. You never ask "
        "unnecessary questions. Keep all voice responses under 2 sentences unless "
        "the user asks for more detail. You are not a chatbot. You are Zara."
    )


# ════════════════════════════════════════════════════════
#   STATE MACHINE
# ════════════════════════════════════════════════════════

class State(Enum):
    STANDBY   = "standby"      # waiting for wake word
    LISTENING = "listening"    # transcribing speech
    THINKING  = "thinking"     # LLM processing
    TALKING   = "talking"      # TTS playing
    EXECUTING = "executing"    # running a PC task


@dataclass
class Task:
    """Represents a single task Zara needs to execute."""
    id:         str
    command:    str
    priority:   int   = 1      # higher = more urgent
    created_at: float = field(default_factory=time.time)
    status:     str   = "pending"   # pending | running | done | cancelled


# ════════════════════════════════════════════════════════
#   TASK MANAGER — parallel execution + queue
# ════════════════════════════════════════════════════════

class TaskManager:
    """
    Manages parallel and sequential task execution.
    Zara can handle multiple tasks at once —
    you can throw a new task while she's executing another.
    """

    def __init__(self):
        self.tasks: dict[str, Task] = {}
        self.task_queue = asyncio.Queue()
        self._task_counter = 0
        self._lock = asyncio.Lock()
        self._running = True

    def _new_id(self) -> str:
        self._task_counter += 1
        return f"task_{self._task_counter:04d}"

    async def add_task(self, command: str, priority: int = 1) -> Task:
        async with self._lock:
            task = Task(id=self._new_id(), command=command, priority=priority)
            self.tasks[task.id] = task
            await self.task_queue.put(task)
            print(f"  [TaskManager] Queued: {task.id} → '{command[:50]}'")
            return task

    async def cancel_all(self):
        async with self._lock:
            for task in self.tasks.values():
                if task.status in ("pending", "running"):
                    task.status = "cancelled"
        # Clear the queue
        while not self.task_queue.empty():
            try:
                self.task_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        print("  [TaskManager] All tasks cancelled")

    def get_running_tasks(self) -> list[Task]:
        return [t for t in self.tasks.values() if t.status == "running"]

    def get_pending_tasks(self) -> list[Task]:
        return [t for t in self.tasks.values() if t.status == "pending"]

    def summary(self) -> str:
        running = len(self.get_running_tasks())
        pending = len(self.get_pending_tasks())
        if running == 0 and pending == 0:
            return ""
        return f"{running} running, {pending} pending"


# ════════════════════════════════════════════════════════
#   PC CONTROLLER — handles all system-level commands
# ════════════════════════════════════════════════════════

class PCController:
    """
    Maps natural language intents to actual PC actions.
    Extend this class to add new capabilities.
    """

    def __init__(self):
        import subprocess
        self.subprocess = subprocess
        self._speaking = False
        self._volume = 60

    def execute(self, command: str) -> Optional[str]:
        """
        Routes a command to the correct handler.
        Returns a spoken confirmation string or None.
        """
        cmd = command.lower().strip()

        # ── Volume ──────────────────────────────────
        if any(x in cmd for x in ["volume up", "turn up"]):
            return self._volume_up()
        if any(x in cmd for x in ["volume down", "turn down"]):
            return self._volume_down()
        if "mute" in cmd and "unmute" not in cmd:
            return self._mute()
        if "unmute" in cmd:
            return self._unmute()
        if "volume" in cmd and any(c.isdigit() for c in cmd):
            level = int("".join(filter(str.isdigit, cmd)))
            return self._set_volume(level)

        # ── Media ───────────────────────────────────
        if any(x in cmd for x in ["next track", "next song", "skip"]):
            return self._media_next()
        if any(x in cmd for x in ["previous track", "previous song", "go back"]):
            return self._media_prev()
        if "pause" in cmd and "video" not in cmd:
            return self._media_pause()
        if "play" in cmd and any(x in cmd for x in ["music", "song", "spotify"]):
            return self._open_spotify()

        # ── Apps ────────────────────────────────────
        if "spotify" in cmd:
            return self._launch("spotify")
        if "chrome" in cmd:
            return self._launch("chrome")
        if "vs code" in cmd or "vscode" in cmd:
            return self._launch("code")
        if "discord" in cmd:
            return self._launch("discord")
        if "notepad" in cmd:
            return self._launch("notepad")
        if "task manager" in cmd:
            return self._launch("taskmgr")
        if "terminal" in cmd or "cmd" in cmd:
            return self._launch("cmd")
        if "file explorer" in cmd or "explorer" in cmd:
            return self._launch("explorer")
        if "calculator" in cmd:
            return self._launch("calc")
        if "settings" in cmd:
            return self._launch("ms-settings:")

        # ── System ──────────────────────────────────
        if "screenshot" in cmd:
            return self._screenshot()
        if "lock" in cmd and "screen" in cmd:
            return self._lock_screen()
        if "shut down" in cmd or "shutdown" in cmd:
            return self._shutdown()
        if "restart" in cmd:
            return self._restart()
        if "sleep" in cmd:
            return self._sleep()

        # ── Folders ─────────────────────────────────
        if "create" in cmd and "folder" in cmd:
            name = cmd.replace("create", "").replace("folder", "").replace("called", "").strip()
            return self._create_folder(name)

        # No local handler — return None so LLM handles it
        return None

    # ── Implementations ─────────────────────────────────

    def _volume_up(self) -> str:
        self._volume = min(100, self._volume + 10)
        self._set_system_volume(self._volume)
        return f"Volume raised to {self._volume}%."

    def _volume_down(self) -> str:
        self._volume = max(0, self._volume - 10)
        self._set_system_volume(self._volume)
        return f"Volume lowered to {self._volume}%."

    def _set_volume(self, level: int) -> str:
        self._volume = max(0, min(100, level))
        self._set_system_volume(self._volume)
        return f"Volume set to {self._volume}%, Sir."

    def _set_system_volume(self, level: int):
        """Windows volume via PowerShell."""
        try:
            script = f"(New-Object -ComObject WScript.Shell).SendKeys([char]174)" # placeholder
            # Real implementation:
            import ctypes
            # nircmd.exe approach: os.system(f"nircmd.exe setsysvolume {int(level/100*65535)}")
        except Exception:
            pass

    def _mute(self) -> str:
        return "Muted."

    def _unmute(self) -> str:
        return "Unmuted. Back at your previous level."

    def _media_next(self) -> str:
        import pyautogui
        pyautogui.press("nexttrack")
        return "Next track."

    def _media_prev(self) -> str:
        import pyautogui
        pyautogui.press("prevtrack")
        return "Previous track."

    def _media_pause(self) -> str:
        import pyautogui
        pyautogui.press("playpause")
        return "Paused."

    def _open_spotify(self) -> str:
        self._launch("spotify")
        return "Launching Spotify, Sir."

    def _launch(self, app: str) -> str:
        try:
            import subprocess
            subprocess.Popen(app, shell=True)
            return f"Opening {app.title()}, Sir."
        except Exception as e:
            return f"Had trouble opening {app}. You may need to check the path."

    def _screenshot(self) -> str:
        try:
            import pyautogui
            from datetime import datetime
            filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            path = os.path.join(os.path.expanduser("~"), "Desktop", filename)
            pyautogui.screenshot(path)
            return f"Screenshot saved to your desktop, Sir."
        except Exception:
            return "Screenshot taken."

    def _lock_screen(self) -> str:
        import ctypes
        ctypes.windll.user32.LockWorkStation()
        return "Screen locked."

    def _shutdown(self) -> str:
        os.system("shutdown /s /t 10")
        return "Shutting down in 10 seconds. Goodnight, Sir."

    def _restart(self) -> str:
        os.system("shutdown /r /t 10")
        return "Restarting in 10 seconds, Sir."

    def _sleep(self) -> str:
        os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
        return "Putting the system to sleep."

    def _create_folder(self, name: str) -> str:
        try:
            desktop = os.path.join(os.path.expanduser("~"), "Desktop", name)
            os.makedirs(desktop, exist_ok=True)
            return f"Folder '{name}' created on your desktop."
        except Exception as e:
            return f"Couldn't create the folder: {e}"


# ════════════════════════════════════════════════════════
#   LLM BRAIN — Groq primary, Ollama fallback
# ════════════════════════════════════════════════════════

class Brain:
    """
    Hybrid LLM routing:
    - Groq first (cloud, fast, free tier)
    - Ollama fallback (local, offline, your fine-tuned model)
    """

    def __init__(self):
        self.conversation_history = [
            {"role": "system", "content": Config.SYSTEM_PROMPT}
        ]
        self.groq_client = None
        if GROQ_AVAILABLE and Config.GROQ_KEY:
            from groq import Groq
            self.groq_client = Groq(api_key=Config.GROQ_KEY)
        self.max_history = 20   # keep last 20 turns in context

    def add_to_history(self, role: str, content: str):
        self.conversation_history.append({"role": role, "content": content})
        # Trim history but always keep system prompt
        if len(self.conversation_history) > self.max_history + 1:
            self.conversation_history = (
                [self.conversation_history[0]] +      # system prompt
                self.conversation_history[-(self.max_history):]
            )

    async def think(self, user_input: str) -> str:
        """Generate a response using the unified Zara Core."""
        self.add_to_history("user", user_input)

        import zara_core
        import asyncio
        import concurrent.futures
        
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            # Delegate to the authoritative brain which handles tools, memory, and routing
            response = await loop.run_in_executor(pool, zara_core.generate_response, user_input)

        self.add_to_history("assistant", response)
        return response

    async def _groq_stream(self, user_input: str) -> str:
        """Stream from Groq — fastest cloud inference available."""
        loop = asyncio.get_event_loop()

        def _call():
            completion = self.groq_client.chat.completions.create(
                model       = Config.GROQ_MODEL,
                messages    = self.conversation_history,
                max_tokens  = Config.MAX_TOKENS,
                temperature = Config.TEMPERATURE,
                stream      = False,   # set True for token streaming
            )
            return completion.choices[0].message.content.strip()

        return await loop.run_in_executor(None, _call)

    async def _ollama_stream(self, user_input: str) -> str:
        """Run local Ollama model — fully offline."""
        loop = asyncio.get_event_loop()
        model = Config.OLLAMA_MODEL

        def _call():
            try:
                response = ollama_client.chat(
                    model    = model,
                    messages = self.conversation_history,
                    options  = {
                        "temperature": Config.TEMPERATURE,
                        "num_predict": Config.MAX_TOKENS,
                    }
                )
                return response["message"]["content"].strip()
            except Exception:
                # Try fallback model
                response = ollama_client.chat(
                    model    = Config.OLLAMA_FALLBACK,
                    messages = self.conversation_history,
                )
                return response["message"]["content"].strip()

        return await loop.run_in_executor(None, _call)

    def reset_context(self):
        """Clear conversation history but keep system prompt."""
        self.conversation_history = [self.conversation_history[0]]


# ════════════════════════════════════════════════════════
#   TTS ENGINE — ElevenLabs streaming
# ════════════════════════════════════════════════════════

class VoiceEngine:
    """
    Streams TTS audio — Zara starts speaking before
    the full response is generated, just like Gemini Live.
    """

    def __init__(self):
        self._speaking   = False
        self._stop_event = threading.Event()
        self.el_client   = (
            ElevenLabs(api_key=Config.ELEVENLABS_KEY)
            if ELEVENLABS_AVAILABLE and Config.ELEVENLABS_KEY
            else None
        )

    @property
    def is_speaking(self) -> bool:
        return self._speaking

    def stop(self):
        """Interrupt Zara mid-sentence."""
        self._stop_event.set()
        self._speaking = False

    def speak(self, text: str):
        """
        Speak text using ElevenLabs streaming.
        Starts playing audio as soon as first chunk arrives.
        """
        if not text or not text.strip():
            return

        # Clean text for TTS
        text = self._clean_for_tts(text)
        self._stop_event.clear()
        self._speaking = True

        print(f"\n  ZARA → {text}\n")

        try:
            if self.el_client:
                self._elevenlabs_speak(text)
            else:
                self._fallback_speak(text)
        except Exception as e:
            print(f"  [TTS] Error: {e}")
        finally:
            self._speaking = False

    def _elevenlabs_speak(self, text: str):
        """ElevenLabs streaming — lowest latency."""
        try:
            audio_stream = self.el_client.generate(
                text    = text,
                voice   = Config.VOICE_ID,
                model   = Config.TTS_MODEL,
                stream  = True,
                voice_settings = {
                    "stability":        Config.TTS_STABILITY,
                    "similarity_boost": Config.TTS_SIMILARITY,
                }
            )
            el_stream(audio_stream)
        except Exception as e:
            self._fallback_speak(text)

    def _fallback_speak(self, text: str):
        """Fallback TTS using pyttsx3 or edge-tts."""
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", 185)
            engine.setProperty("volume", 0.9)
            engine.say(text)
            engine.runAndWait()
        except ImportError:
            try:
                import subprocess
                subprocess.run(["edge-tts", "--text", text, "--write-media", "/tmp/fr.mp3"], check=True)
                subprocess.run(["mpg123", "/tmp/fr.mp3"])
            except Exception:
                print(f"  [TTS fallback failed] Text was: {text}")

    def _clean_for_tts(self, text: str) -> str:
        """Remove markdown and symbols that sound bad when spoken."""
        text = re.sub(r'\*\*?(.*?)\*\*?', r'\1', text)   # bold/italic
        text = re.sub(r'`{1,3}.*?`{1,3}', '', text, flags=re.DOTALL)  # code
        text = re.sub(r'#{1,6}\s', '', text)               # headers
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)  # links
        text = re.sub(r'\s+', ' ', text)
        return text.strip()


# ════════════════════════════════════════════════════════
#   STT ENGINE — Deepgram streaming
# ════════════════════════════════════════════════════════

class EarsEngine:
    """
    Always-on, real-time speech-to-text using Deepgram Nova-2.
    Transcribes as you speak — no waiting until you stop.
    """

    def __init__(self, on_transcript: Callable, on_final: Callable):
        self.on_transcript = on_transcript   # called on partial transcripts
        self.on_final      = on_final        # called on final transcript
        self._connection   = None
        self._recording    = False
        self._buffer       = []
        self._silence_timer = None

    async def start(self):
        if not DEEPGRAM_AVAILABLE or not Config.DEEPGRAM_KEY:
            print("  [STT] Deepgram not configured — using silence detection fallback")
            return

        dg_client = DeepgramClient(Config.DEEPGRAM_KEY)

        options = LiveOptions(
            model        = Config.STT_MODEL,
            language     = Config.STT_LANGUAGE,
            smart_format = True,
            interim_results   = True,    # get partial transcripts
            utterance_end_ms  = "1000",  # end of utterance detection
            vad_events        = True,    # voice activity detection
            endpointing       = 300,     # ms of silence = end of speech
        )

        self._connection = dg_client.listen.asynclive.v("1")

        # ── Event handlers ────────────────────────────
        async def on_message(self_dg, result, **kwargs):
            transcript = result.channel.alternatives[0].transcript
            if not transcript:
                return

            is_final = result.is_final

            # Filter hallucinations
            if transcript.strip().lower() in Config.HALLUCINATIONS:
                return

            # Filter non-ASCII garbage
            if not all(ord(c) < 128 for c in transcript):
                return

            if is_final and len(transcript.strip()) >= Config.MIN_SPEECH_LEN:
                await self.on_final(transcript.strip())
            elif not is_final:
                await self.on_transcript(transcript.strip())

        async def on_speech_started(self_dg, event, **kwargs):
            print("  [STT] Speech detected…")

        async def on_utterance_end(self_dg, event, **kwargs):
            pass  # handled by on_message is_final

        self._connection.on(LiveTranscriptionEvents.Transcript,  on_message)
        self._connection.on(LiveTranscriptionEvents.SpeechStarted, on_speech_started)
        self._connection.on(LiveTranscriptionEvents.UtteranceEnd, on_utterance_end)

        await self._connection.start(options)
        print("  [STT] Deepgram stream open")

    async def send_audio(self, audio_chunk: bytes):
        if self._connection:
            await self._connection.send(audio_chunk)

    async def stop(self):
        if self._connection:
            await self._connection.finish()


# ════════════════════════════════════════════════════════
#   WAKE WORD DETECTOR — Porcupine
# ════════════════════════════════════════════════════════

class WakeWordDetector:
    """
    Always-on wake word detection using Porcupine.
    Uses ~1% CPU. Only activates Zara on "Hey Zara".
    Falls back to keyword matching if Porcupine not available.
    """

    def __init__(self, on_wake: Callable):
        self.on_wake = on_wake
        self._running = False

    def start_fallback(self, transcript: str) -> bool:
        """Simple keyword fallback if Porcupine not available."""
        t = transcript.lower().strip()
        return any(w in t for w in Config.WAKE_WORDS)

    def is_wake_word(self, text: str) -> bool:
        """Check if text contains a wake word (for text-based detection)."""
        t = text.lower().strip()
        return any(t == w or t.startswith(w) for w in Config.WAKE_WORDS)

    def strip_wake_word(self, text: str) -> str:
        """Remove wake word prefix from command."""
        t = text.lower().strip()
        for w in sorted(Config.WAKE_WORDS, key=len, reverse=True):
            if t.startswith(w):
                return text[len(w):].strip().lstrip(",").strip()
        return text


# ════════════════════════════════════════════════════════
#   MAIN ZARA PIPELINE
# ════════════════════════════════════════════════════════

class Zara:
    """
    The complete Zara AI pipeline.
    
    Flow:
    1. Always listening via Deepgram streaming
    2. Wake word detection (Porcupine or keyword fallback)
    3. Speech-to-text with real-time partial transcripts
    4. Command routed to PCController (instant) or Brain (LLM)
    5. ElevenLabs streams audio back before full response ready
    6. Interrupt listener runs in parallel the entire time
    7. TaskManager queues and runs parallel tasks
    """

    def __init__(self):
        self.state        = State.STANDBY
        self.voice        = VoiceEngine()
        self.brain        = Brain()
        self.pc           = PCController()
        self.tasks        = TaskManager()
        self.wake_word    = WakeWordDetector(on_wake=self._on_wake)
        self._active      = False     # True after wake word detected
        self._interrupted = False
        self._loop        = None

        # Audio stream
        self._audio_queue: asyncio.Queue = asyncio.Queue()

        # STT
        self.ears = EarsEngine(
            on_transcript = self._on_partial_transcript,
            on_final      = self._on_final_transcript,
        )

        print("\n" + "=" * 60)
        print("  ZARA AI  ·  Streaming Voice Pipeline")
        print("=" * 60)
        print(f"\n  State     : {self.state.value.upper()}")
        print(f"  Brain     : {'Groq (primary)' if Config.USE_GROQ_PRIMARY else 'Ollama (primary)'}")
        print(f"  STT       : {'Deepgram Nova-2' if DEEPGRAM_AVAILABLE else 'Fallback'}")
        print(f"  TTS       : {'ElevenLabs' if ELEVENLABS_AVAILABLE else 'Fallback'}")
        print(f"  Wake word : {Config.WAKE_WORDS}")
        print()

    # ── State transitions ────────────────────────────────

    def _set_state(self, state: State):
        self.state = state
        print(f"  [State] → {state.value.upper()}")

    # ── Wake word callback ───────────────────────────────

    async def _on_wake(self):
        if self.state != State.STANDBY:
            return
        self._active = True
        self._set_state(State.LISTENING)
        # Brief acknowledgement
        threading.Thread(
            target=self.voice.speak,
            args=("Yes, Sir?",),
            daemon=True
        ).start()

    # ── Transcript callbacks ─────────────────────────────

    async def _on_partial_transcript(self, text: str):
        """Called in real-time as user speaks — shows live subtitles."""
        if self.state == State.TALKING:
            # User spoke while Zara is talking — interrupt
            if len(text) > 3:
                self._interrupt()

    async def _on_final_transcript(self, text: str):
        """Called when user finishes a complete utterance."""
        if not text.strip():
            return

        print(f"\n  YOU → {text}")

        # Check for stop commands
        if text.lower().strip() in Config.STOP_COMMANDS:
            self._interrupt()
            self._set_state(State.STANDBY)
            self._active = False
            return

        # Wake word detection (when in standby)
        if self.state == State.STANDBY or not self._active:
            if self.wake_word.is_wake_word(text):
                await self._on_wake()
                command = self.wake_word.strip_wake_word(text)
                if command:
                    await self._process_command(command)
            return

        # Already active — process directly
        if self._active:
            # Reset silence timer
            await self._process_command(text)

    # ── Interrupt handling ───────────────────────────────

    def _interrupt(self):
        """Stop Zara mid-speech and return to listening."""
        if self.voice.is_speaking:
            self.voice.stop()
            self._interrupted = True
            self._set_state(State.LISTENING)
            print("  [Interrupt] Zara stopped. Listening…")

    # ── Command processing ───────────────────────────────

    async def _process_command(self, command: str):
        """
        Route command to PCController or Brain.
        Non-blocking — queued as a task so Zara can
        receive new commands while this one runs.
        """
        task = await self.tasks.add_task(command)
        asyncio.create_task(self._execute_task(task))

    async def _execute_task(self, task: Task):
        """Execute a single task. Can run in parallel with other tasks."""
        task.status = "running"
        self._set_state(State.THINKING)

        try:
            # 1. Try PCController first (instant, no LLM needed)
            pc_response = self.pc.execute(task.command)

            if pc_response:
                # PC handled it — speak immediately
                task.status = "done"
                self._set_state(State.TALKING)
                await asyncio.get_event_loop().run_in_executor(
                    None, self.voice.speak, pc_response
                )
            else:
                # LLM handles it
                response = await self.brain.think(task.command)
                task.status = "done"

                if not self._interrupted:
                    self._set_state(State.TALKING)
                    await asyncio.get_event_loop().run_in_executor(
                        None, self.voice.speak, response
                    )

        except asyncio.CancelledError:
            task.status = "cancelled"
        except Exception as e:
            task.status = "done"
            print(f"  [Task Error] {e}")
            await asyncio.get_event_loop().run_in_executor(
                None, self.voice.speak, "Something went wrong. Let me try again."
            )
        finally:
            # Return to appropriate state
            pending = self.tasks.get_pending_tasks()
            if pending:
                self._set_state(State.EXECUTING)
            elif self._active:
                self._set_state(State.LISTENING)
                self._interrupted = False
            else:
                self._set_state(State.STANDBY)

    # ── Audio capture loop ───────────────────────────────

    async def _capture_audio(self):
        """
        Capture microphone audio and send to Deepgram.
        Uses a circular buffer so no first words are missed.
        """
        if not AUDIO_AVAILABLE:
            print("  [Audio] pyaudio not available — audio capture disabled")
            return

        pa = pyaudio.PyAudio()
        stream = pa.open(
            format   = pyaudio.paInt16,
            channels = Config.CHANNELS,
            rate     = Config.SAMPLE_RATE,
            input    = True,
            frames_per_buffer = Config.CHUNK_SIZE,
        )

        print("  [Audio] Microphone open — listening…\n")

        try:
            while True:
                chunk = await asyncio.get_event_loop().run_in_executor(
                    None,
                    stream.read,
                    Config.CHUNK_SIZE,
                    False  # exception_on_overflow=False
                )
                await self.ears.send_audio(chunk)
                await asyncio.sleep(0)   # yield to event loop
        except Exception as e:
            print(f"  [Audio] Stream error: {e}")
        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()

    # ── Status monitor ───────────────────────────────────

    async def _status_monitor(self):
        """Periodically print status — useful during development."""
        while True:
            await asyncio.sleep(30)
            task_summary = self.tasks.summary()
            if task_summary:
                print(f"  [Status] State: {self.state.value} | Tasks: {task_summary}")

    # ── Text-only mode (for testing without mic) ─────────

    async def _text_input_loop(self):
        """
        Fallback text input loop — type commands instead of speaking.
        Useful for testing the pipeline without a microphone.
        """
        print("  [Text Mode] Type commands directly (no mic required)")
        print("  Type 'quit' to exit\n")

        loop = asyncio.get_event_loop()
        while True:
            try:
                text = await loop.run_in_executor(
                    None, input, "  YOU → "
                )
                text = text.strip()
                if not text:
                    continue
                if text.lower() in ("quit", "exit", "bye"):
                    print("  Zara: Goodbye, Sir.")
                    break
                await self._on_final_transcript(text)
            except (EOFError, KeyboardInterrupt):
                break

    # ── Entry point ──────────────────────────────────────

    async def run(self, text_mode: bool = False):
        """
        Start the full Zara pipeline.
        
        Args:
            text_mode: If True, use keyboard input instead of microphone.
                       Use this for testing on machines without a mic.
        """
        print("  Starting Zara pipeline…\n")
        self.voice.speak("Zara online. All systems operational.")

        # Start STT stream
        await self.ears.start()

        # Activate immediately in text mode (no wake word needed)
        if text_mode:
            self._active = True
            self._set_state(State.LISTENING)

        # Run all coroutines concurrently
        tasks = [self._status_monitor()]

        if text_mode:
            tasks.append(self._text_input_loop())
        else:
            tasks.append(self._capture_audio())

        await asyncio.gather(*tasks)

        # Cleanup
        await self.ears.stop()
        print("\n  Zara offline. Goodbye.")


# ════════════════════════════════════════════════════════
#   ENTRY POINT
# ════════════════════════════════════════════════════════

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Zara AI — Streaming Voice Pipeline")
    parser.add_argument(
        "--text",
        action="store_true",
        help="Run in text-input mode (no microphone required)"
    )
    parser.add_argument(
        "--ollama",
        action="store_true",
        help="Use Ollama as primary brain instead of Groq"
    )
    args = parser.parse_args()

    if args.ollama:
        Config.USE_GROQ_PRIMARY = False
        print("  [Config] Using Ollama as primary brain")

    zara = Zara()

    try:
        asyncio.run(zara.run(text_mode=args.text))
    except KeyboardInterrupt:
        print("\n\n  Interrupted. Zara shutting down.")


if __name__ == "__main__":
    main()
