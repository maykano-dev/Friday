"""Zara — Main event loop.

Architecture:
  - ContinuousListener (daemon) handles the mic on its own thread.
  - VoiceEngine (daemon) handles TTS rendering + playback on two threads.
  - The main loop here only:
      1. Polls the listener's result_queue for transcribed text.
      2. Dispatches to zara_core for streaming LLM response.
      3. Sleeps 10ms per tick to keep CPU usage minimal.
"""

import json
import os
import time
import threading
from queue import Empty

import zara_core
import local_voice
import local_ears
from ui_engine import ContextCard, NeuralVisualizer, WebResultCard
from proactive_engine import ProactiveEngine
from session_manager import get_session_manager
from agent_orchestrator import get_orchestrator
from secure_sandbox import get_sandbox
from output_router import get_router
from engagement_engine import EngagementEngine
import action_engine
import state
import ws_bridge  # ← Real-time dashboard bridge

ui = None
session_mgr = None
router = None
orchestrator = None
sandbox = None

_utterance_lock = threading.Lock()
_output_router = get_router()


def get_greeting() -> str:
    """Ask Zara's brain to generate a unique greeting."""
    boot_prompt = "SYSTEM_BOOT: Give me a unique, concise, and confident one-sentence startup greeting as Zara."
    return zara_core.generate_response(boot_prompt)


def _process_utterance(text: str, proactive) -> None:
    """Handle a single user utterance with immediate visual feedback."""
    global ui, session_mgr, _output_router
    
    with _utterance_lock:
        # IMMEDIATE FEEDBACK
        if ui:
            ui.set_user_text(text)
            ui.set_state("THINKING")
            ui.set_subtitle_text("...")
        ws_bridge.set_state("THINKING")
        ws_bridge.add_message("user", text)
        ws_bridge.set_live_transcript(text, live=False)

        if proactive:
            proactive.notify_user_spoke()

        zara_reply = zara_core.generate_response(text)
        print(f"Zara (Raw): {zara_reply}")

        if session_mgr and zara_reply:
            session_mgr.record_exchange(text, zara_reply)

        # Smart Output Routing
        routed = _output_router.route(zara_reply)
        
        if routed.visual and ui:
            ui.context_cards.append(ContextCard("TEXT", routed.visual))
            
        if routed.action:
            try:
                executor = action_engine.ActionExecutor()
                executor.execute_payload(routed.action)
            except Exception as e:
                print(f"[Main] Action execution failed: {e}")

        if routed.spoken:
            if ui:
                ui.set_subtitle_text(routed.spoken)
                ui.set_state("TALKING")
            ws_bridge.set_state("TALKING")
            ws_bridge.add_message("zara", routed.spoken)
            local_voice.speak(routed.spoken)

    # Wait for speech to finish before resetting UI (OUTSIDE THE LOCK)
    deadline = time.time() + 30  # Safety timeout
    while getattr(state.is_talking, 'value', False) and time.time() < deadline:
        time.sleep(0.05)

    if ui:
        ui.set_subtitle_text("")
        ui.set_user_text("")
        ui.set_state("STANDBY")
    ws_bridge.set_state("STANDBY")


def run_Zara():
    global ui, session_mgr, router, sandbox, orchestrator

    # ── Keyboard Hotkey ─────────────────────────────────────────────────
    try:
        import keyboard
        import pygame
        from ui_engine import MANUAL_INGEST_CMD

        def _inject_clipboard():
            pygame.event.post(pygame.event.Event(MANUAL_INGEST_CMD))

        keyboard.add_hotkey("ctrl+alt+v", _inject_clipboard)
        print("[System: Global Clipboard listener active (Ctrl+Alt+V)]")
    except ImportError:
        print(
            "[System WARNING: 'keyboard' module not installed. Global Hotkey disabled.]")

    print("\n[System: Booting Zara Core...]")

    # ── 1. Boot UI ──────────────────────────────────────────────────────
    ui = NeuralVisualizer()
    ui.start()

    # ── 1.1 Start WebSocket bridge for React dashboard ──────────────────
    ws_bridge.start_bridge()

    # Seed API health from env
    ws_bridge.set_api_health({
        "groq":       "online" if os.getenv("GROQ_API_KEY") else "offline",
        "deepgram":   "online" if os.getenv("DEEPGRAM_API_KEY") else "offline",
        "elevenlabs": "online" if os.getenv("ELEVENLABS_API_KEY") else "offline",
        "ollama":     "offline",
    })

    # ── CHECK FOR RESUME STATE ───────────────────────────────────────
    if os.path.exists("resume_state.json"):

        try:
            with open("resume_state.json", "r", encoding="utf-8") as f:
                saved_cards = json.load(f)
            for c in saved_cards:
                if c.get("card_type") == "WEB":
                    ui.context_cards.append(WebResultCard(
                        c.get("url", ""), status="complete"))
                else:
                    ui.context_cards.append(ContextCard(
                        c.get("card_type", "TEXT"), c.get("content", ""), label=c.get("label", "")))
            print("[System] Memory state resumed. Context Wing restored.")
        except Exception as e:
            print(f"[System Error] Failed to resume state: {e}")

    # ── 1.5. Initialize new modules ──────────────────────────────────────
    session_mgr = get_session_manager()
    router = get_router()
    sandbox = get_sandbox()

    # Setup orchestrator with LLM callback
    def llm_callback(system_prompt: str, user_prompt: str) -> str:
        return zara_core.generate_response(f"{system_prompt}\n\n{user_prompt}")

    orchestrator = get_orchestrator(llm_callback)
    orchestrator.start()

    # ── 2. Startup Greeting ─────────────────────────────────────────────
    ui.set_state("THINKING")
    ui.set_subtitle_text("")

    # Check for session resume
    resume_greeting = session_mgr.get_resume_greeting() if session_mgr else None
    if resume_greeting:
        print(f"Zara: {resume_greeting}")
        ui.set_state("TALKING")
        ui.set_subtitle_text(resume_greeting)
        local_voice.speak(resume_greeting)
    else:
        greeting = get_greeting()
        print(f"Zara: {greeting}")
        ui.set_state("TALKING")
        ui.set_subtitle_text(greeting)
        local_voice.speak(greeting)
    
    # Mark startup as complete so future speech triggers ducking
    local_voice.mark_startup_complete()

    # ── ACTIVATE ZARA'S EYES ─────────────────────────────────────
    try:
        from zara_eyes import get_eyes
        eyes = get_eyes()

        # Set up error callback - Zara proactively helps!
        def on_error(error_context):
            error_msg = error_context.error_message
            print(f"[Zara] Proactively detected error: {error_msg}")

            # Zara speaks up when she sees an error!
            import local_voice
            # Shortened message for better UX
            local_voice.speak(
                f"Sir, I noticed an error on your screen. Would you like me to help?")

        eyes.on_error_detected = on_error

        # eyes.start()
        print("[Zara] Eyes ready for on-demand use")
    except Exception as e:
        print(f"[Zara] Eyes failed to activate: {e}")

    # ── 3. Boot background daemons ──────────────────────────────────────
    proactive = ProactiveEngine(ui=ui, interval_seconds=1800)
    proactive.start()

    # Smart Engagement Engine (Idle + File Scanning)
    def _proactive_callback(prompt):
        import state
        # Don't interrupt if busy
        if getattr(state.is_talking, 'value', False):
            return
        if _utterance_lock.locked():
            return
        threading.Thread(
            target=_process_utterance,
            args=(prompt, proactive),
            daemon=True
        ).start()

    engagement = EngagementEngine(idle_timeout_seconds=600, scan_dir=None)
    engagement.start(callback=_proactive_callback)

    try:
        from learning_engine import LearningEngine
        learning = LearningEngine(ui=ui)
        learning.start()
    except Exception as e:
        print(f"[System] LearningEngine skipped: {e}")
        learning = None

    # ── 3.5. Start Wake Word Engine ─────────────────────────────────────
    try:
        from wake_word_engine import WakeWordEngine
        import local_voice
        import pygame
        
        def wake_callback():
            local_voice.interrupt()
            if ui:
                ui.set_state("LISTENING")
            try:
                # Play an acknowledgment chime if it exists
                if os.path.exists("assets/chime.wav"):
                    pygame.mixer.Sound("assets/chime.wav").play()
            except:
                pass
                
        wake_engine = WakeWordEngine(callback=wake_callback)
        wake_engine.start()
        print("[System] Wake Word Engine online.")
    except Exception as e:
        print(f"[System] Wake Word Engine failed to start: {e}")

    # ── 4. Start the Continuous Listener (daemon) ───────────────────────
    # Pass the UI object to the listener here
    listener = local_ears.get_listener(ui=ui)
    listener.start()

    # ── 5. Main event loop — lightweight poll ───────────────────────────
    try:
        while True:
            # Check if the listener has a new transcription
            try:
                user_text = listener.result_queue.get_nowait()
                print(f"[Main] DEBUG: Got text from queue: '{user_text}'")
            except Empty:
                user_text = None

            if user_text:
                print(f"[Main] DEBUG: Processing: '{user_text}'")
                threading.Thread(
                    target=_process_utterance,
                    args=(user_text, proactive),
                    daemon=True,
                ).start()

            # Give the CPU a tiny break — prevents 98% usage
            time.sleep(0.01)

    except KeyboardInterrupt:
        print("\n[System: Shutting down Zara...]")

        try:
            state_data = [card.to_dict() for card in ui.context_cards]
            with open("resume_state.json", "w", encoding="utf-8") as f:
                json.dump(state_data, f)
            print("[System] State saved to resume_state.json")
        except Exception as e:
            print(f"[System Error] Failed to save state: {e}")

        listener.stop()
        if learning:
            learning.stop()
        proactive.stop()
        
        try:
            from zara_eyes import get_eyes
            get_eyes().stop()
        except:
            pass
            
        ui.stop()


if __name__ == "__main__":
    run_Zara()
