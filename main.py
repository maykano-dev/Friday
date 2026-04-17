import time
from datetime import datetime
from queue import Empty, Queue

import local_ears
import friday_core
import local_voice
import action_engine
from learning_engine import LearningEngine
from ui_engine import NeuralVisualizer
from proactive_engine import ProactiveEngine

ui = None

def get_greeting():
    """Generates a zero-latency, time-aware startup greeting."""
    hour = datetime.now().hour
    if hour < 12:
        return "Good morning, sir. All systems are online."
    elif hour < 18:
        return "Good afternoon, sir. All systems are online."
    else:
        return "Good evening, sir. Core systems are online and ready."

def run_friday():

    # Hook Keyboard Listener for Manual Ingest
    try:
        import keyboard
        import pygame
        from ui_engine import MANUAL_INGEST_CMD
        def _inject_clipboard():
            pygame.event.post(pygame.event.Event(MANUAL_INGEST_CMD))
            
        keyboard.add_hotkey("ctrl+alt+v", _inject_clipboard)
        print("[System: Global Clipboard listener active (Ctrl+Alt+V)]")
    except ImportError:
        print("[System WARNING: 'keyboard' module not installed. Global Hotkey disabled. Run 'pip install keyboard'.]")

    global ui
    print("\n[System: Booting Apex Friday Core...]")
    
    # 1. Boot the UI in the background
    ui = NeuralVisualizer()
    ui.start()
    
    # 2. Instant Startup Greeting
    greeting = get_greeting()
    print(f"Friday: {greeting}")
    ui.set_state("TALKING")
    ui.set_subtitle_text(greeting)
    local_voice.speak(greeting)

    # 3. Boot the Proactive Engine in its own daemon thread. It NEVER
    # speaks directly -- it only synthesizes Goal Summaries in the background.
    proactive = ProactiveEngine(ui=ui, interval_seconds=1800)
    proactive.start()

    # 3b. Boot the Learning Engine
    learning = LearningEngine(ui=ui)
    learning.start()

    try:
        while True:
            # 4. Standby / Listening Mode
            ui.set_state("STANDBY")
            user_text = local_ears.listen_and_transcribe()

            if not user_text:
                continue

            print(f"\nYou: {user_text}")
            ui.set_user_text(user_text)

            # The user actually spoke -- reset the ProactiveEngine's idle timer.
            proactive.notify_user_spoke()

            # 5. Thinking Mode
            ui.set_state("THINKING")
            friday_reply = friday_core.generate_response(user_text)
            print(f"Friday: {friday_reply}")

            # 6. Talking Mode setup done internally via generator hooks...
            # The subtitle is now driven natively via UI integration inside stream.
            
            # --- THE FIX: COOL DOWN ---
            # 1.2s "dead zone" after she stops talking so the mic doesn't
            # catch her echo or the speaker click-off as a new utterance.
            print("[System: Cooling down audio sensors...]")
            time.sleep(1.2)
            ui.set_subtitle_text("")
            ui.set_user_text("")
            ui.set_state("STANDBY")

    except KeyboardInterrupt:
        print("\n[System: Shutting down Friday...]")
        learning.stop()
        proactive.stop()
        ui.stop()

if __name__ == "__main__":
    run_friday()
