"""Friday - Temporal Context Engine (Proactive Reflection).

Runs a Background Daemon performing Latent Semantic Analysis on the database
using a Reflection-Insight-Action (RIA) framework.
"""

from __future__ import annotations

import threading
import time
import requests
from typing import Optional

import memory_vault
import ui_engine

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "qwen2.5:1.5b"


class ProactiveEngine:
    """Daemon thread that generates background RIA summaries."""

    def __init__(
        self,
        ui: ui_engine.NeuralVisualizer,
        interval_seconds: int = 1800,    # 30 minutes
        check_interval_seconds: int = 60,
    ) -> None:
        self.ui = ui
        self.interval = max(1, int(interval_seconds))
        self.check_interval = max(1, int(check_interval_seconds))

        self._lock = threading.Lock()
        self._last_interaction = time.time()
        self._last_alert = 0.0

        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def notify_user_spoke(self) -> None:
        with self._lock:
            self._last_interaction = time.time()
            self._last_alert = 0.0

    def _run(self) -> None:
        while self._running:
            try:
                self._tick()
            except Exception as e:
                print(f"[Proactive Engine] tick failed: {e}")

            for _ in range(self.check_interval):
                if not self._running:
                    return
                time.sleep(1)

    def _tick(self) -> None:
        now = time.time()
        with self._lock:
            elapsed = now - self._last_interaction
            since_alert = now - self._last_alert

        # State Detection: If state == "IDLE" for > 30 mins
        if elapsed >= self.interval and since_alert >= self.interval:
            with self._lock:
                self._last_alert = now
                
            self._generate_and_inject_objective()

    def _generate_and_inject_objective(self) -> None:
        # Fetch the last 50 interaction logs
        memories = memory_vault.get_recent_memories(limit=50)
        if not memories:
            return

        self.ui.set_bg_task("Thinking...")
        try:
            memories_str = "\n".join(f"- {m}" for m in memories)
            prompt = (
                "What is the user's current trajectory? What are the unresolved blockers?\n\n"
                f"Logs:\n{memories_str}\n"
            )
            
            payload = {
                "model": MODEL_NAME,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0.6, "num_ctx": 1024},
            }
            
            resp = requests.post(OLLAMA_URL, json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            message = data.get("message") or {}
            content = (message.get("content") or "").strip()
            
            if content:
                print(f"\n[Proactive Engine] Target Insight formulated: {content}")
                memory_vault.inject_context_insight(content)
        except Exception as e:
            print(f"[Proactive Engine] RIA Synthesis Failed: {e}")
        finally:
            self.ui.set_bg_task("")
