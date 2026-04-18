"""Friday — Main event loop.

Architecture:
  - ContinuousListener (daemon) handles the mic on its own thread.
  - VoiceEngine (daemon) handles TTS rendering + playback on two threads.
  - The main loop here only:
      1. Polls the listener's result_queue for transcribed text.
      2. Dispatches to friday_core for streaming LLM response.
      3. Sleeps 10ms per tick to keep CPU usage minimal.
"""

import json
import os
import time
import threading
from queue import Empty

import friday_core
import local_voice
import local_ears
from ui_engine import ContextCard, NeuralVisualizer, WebResultCard
from proactive_engine import ProactiveEngine
from session_manager import get_session_manager
from agent_orchestrator import get_orchestrator
from output_router import get_router
from secure_sandbox import get_sandbox

ui = None
session_mgr = None
router = None
orchestrator = None
sandbox = None


def get_greeting() -> str:
    """Ask Friday's brain to generate a unique greeting."""
    boot_prompt = "SYSTEM_BOOT: Give me a unique, concise, and witty one-sentence greeting."
    return friday_core.generate_response(boot_prompt)


def _process_utterance(text: str, proactive) -> None:
    """Handle a single user utterance with immediate visual feedback."""
    global ui

    # IMMEDIATE FEEDBACK
    if ui:
        ui.set_user_text(text)
        ui.set_state("LISTENING")

    time.sleep(0.05)  # Let UI update

    if ui:
        ui.set_state("THINKING")
        ui.set_subtitle_text("...")

    if proactive:
        proactive.notify_user_spoke()

    friday_reply = friday_core.generate_response(text)
    print(f"Friday: {friday_reply}")

    time.sleep(0.8)
    if ui:
        ui.set_subtitle_text("")
        ui.set_user_text("")
        ui.set_state("STANDBY")


def run_friday():
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

    print("\n[System: Booting Apex Friday Core...]")

    # ── 1. Boot UI ──────────────────────────────────────────────────────
    ui = NeuralVisualizer()
    ui.start()

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
        return friday_core.generate_response(f"{system_prompt}\n\n{user_prompt}")

    orchestrator = get_orchestrator(llm_callback)
    orchestrator.start()

    # ── 2. Startup Greeting ─────────────────────────────────────────────
    ui.set_state("THINKING")
    ui.set_subtitle_text("")

    # Check for session resume
    resume_greeting = session_mgr.get_resume_greeting() if session_mgr else None
    if resume_greeting:
        print(f"Friday: {resume_greeting}")
        ui.set_state("TALKING")
        ui.set_subtitle_text(resume_greeting)
        local_voice.speak(resume_greeting)
    else:
        greeting = get_greeting()
        print(f"Friday: {greeting}")
        ui.set_state("TALKING")
        ui.set_subtitle_text(greeting)
        local_voice.speak(greeting)

    # ── 3. Boot background daemons ──────────────────────────────────────
    proactive = ProactiveEngine(ui=ui, interval_seconds=1800)
    proactive.start()

    try:
        from learning_engine import LearningEngine
        learning = LearningEngine(ui=ui)
        learning.start()
    except Exception as e:
        print(f"[System] LearningEngine skipped: {e}")
        learning = None

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
            except Empty:
                user_text = None

            if user_text:
                # Process on a background thread so we don't block the poll
                threading.Thread(
                    target=_process_utterance,
                    args=(user_text, proactive),
                    daemon=True,
                ).start()

            # Give the CPU a tiny break — prevents 98% usage
            time.sleep(0.01)

    except KeyboardInterrupt:
        print("\n[System: Shutting down Friday...]")

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
        ui.stop()


if __name__ == "__main__":
    run_friday()
