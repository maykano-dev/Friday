"""Zara - background learning and post-mortem analysis.

Monitors the system for idle time (ui=STANDBY) and queries Ollama to construct
lessons and best practice summaries from previously failed coding run attempts.
"""

from __future__ import annotations

import time
import threading
import requests

import memory_vault
from ui_engine import NeuralVisualizer

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "qwen2.5:1.5b"
POLL_INTERVAL = 10  # Seconds to wait between DB checks


class LearningEngine(threading.Thread):
    def __init__(self, ui: NeuralVisualizer, poll_interval: int = POLL_INTERVAL):
        super().__init__(daemon=True)
        self.ui = ui
        self.poll_interval = poll_interval
        self._running = False

    def start(self) -> None:
        self._running = True
        super().start()

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        while self._running:
            time.sleep(self.poll_interval)

            if not self._running:
                break

            if self.ui.state == "STANDBY":
                tasks = memory_vault.get_unprocessed_failed_tasks()
                if not tasks:
                    continue

                # Take the oldest un-summarized failed task
                task = tasks[0]
                task_id = task["id"]
                code = task["code"]

                print(
                    f"\n[Learning Engine] Reflecting on failed task {task_id}...")

                summary = self._generate_best_practices(code)

                if summary:
                    memory_vault.mark_task_processed(task_id, summary)
                    print(
                        f"[Learning Engine] Task {task_id} summarized and committed to vault.")

    def _generate_best_practices(self, code: str) -> str:
        prompt = (
            "You are Zara, analyzing a piece of code that failed execution. "
            "Examine this code carefully and write a concise 1-2 sentence "
            "'Best Practices' summary explaining the potential flaw and how to avoid it. "
            "Focus completely on the lesson, do not write additional greetings.\n\n"
            f"Code:\n{code}\n"
        )

        payload = {
            "model": MODEL_NAME,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0.5, "num_ctx": 1024},
        }

        try:
            resp = requests.post(OLLAMA_URL, json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            message = data.get("message") or {}
            return (message.get("content") or "").strip()
        except Exception as e:
            print(f"[Learning Engine] Failed to reach Ollama: {e}")
            return ""
