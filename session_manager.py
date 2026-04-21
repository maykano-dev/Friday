"""Zara - Session Manager (OpenClaw-inspired persistence)

Maintains continuity across reboots by serializing conversation state,
pending tasks, and context cards to disk. On restart, Zara remembers
exactly where you left off.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict, field
from enum import Enum


class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    WAITING_FOLLOWUP = "waiting_followup"


@dataclass
class PendingTask:
    """A task Zara needs to follow up on."""
    id: str
    description: str
    created_at: float
    status: TaskStatus
    followup_trigger: Optional[str] = None  # Condition to check for followup
    followup_prompt: Optional[str] = None    # What to say when triggered
    last_check: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "PendingTask":
        d["status"] = TaskStatus(d["status"])
        return cls(**d)


class SessionManager:
    """Persists conversation state and pending tasks across Zara restarts."""

    SESSION_FILE = os.path.join(
        os.path.dirname(__file__), "session_state.json")
    DEBOUNCE_SECONDS = 5.0  # Minimum interval between disk writes

    def __init__(self):
        self.conversation_history: List[Dict[str, str]] = []
        self.pending_tasks: List[PendingTask] = []
        self.active_context: Dict[str, Any] = {}
        self.last_active_time: float = time.time()
        self._last_save_time: float = 0.0
        self._save_timer: Optional[threading.Timer] = None
        self._save_lock = threading.Lock()
        self._load_session()

    def _load_session(self) -> None:
        """Restore previous session state from disk."""
        if not os.path.exists(self.SESSION_FILE):
            return

        try:
            with open(self.SESSION_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.conversation_history = data.get(
                "conversation_history", [])[-20:]  # Keep last 20
            self.active_context = data.get("active_context", {})
            self.last_active_time = data.get("last_active_time", time.time())

            # Restore pending tasks
            for task_data in data.get("pending_tasks", []):
                self.pending_tasks.append(PendingTask.from_dict(task_data))

            print(f"[Session] Restored {len(self.pending_tasks)} pending tasks, "
                  f"{len(self.conversation_history)} conversation turns")
        except Exception as e:
            print(f"[Session] Failed to load session: {e}")

    def save_session(self) -> None:
        """Persist current state to disk (debounced to avoid excessive writes)."""
        with self._save_lock:
            # Cancel any pending timer
            if self._save_timer is not None:
                self._save_timer.cancel()
                self._save_timer = None

            now = time.time()
            time_since_last = now - self._last_save_time

            if time_since_last >= self.DEBOUNCE_SECONDS:
                # Enough time has elapsed — write immediately
                self._do_save()
            else:
                # Schedule a write for when the debounce window expires
                delay = self.DEBOUNCE_SECONDS - time_since_last
                self._save_timer = threading.Timer(delay, self._do_save)
                self._save_timer.daemon = True
                self._save_timer.start()

    def _do_save(self) -> None:
        """Actual disk write. Called by save_session() after debounce."""
        with self._save_lock:
            self._save_timer = None
        try:
            data = {
                "conversation_history": self.conversation_history,
                "pending_tasks": [t.to_dict() for t in self.pending_tasks],
                "active_context": self.active_context,
                "last_active_time": time.time(),
                "saved_at": datetime.utcnow().isoformat()
            }
            with open(self.SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            self._last_save_time = time.time()
        except Exception as e:
            print(f"[Session] Failed to save session: {e}")

    def add_task(self, description: str, followup_trigger: str = None,
                 followup_prompt: str = None) -> PendingTask:
        """Register a task for future follow-up."""
        import uuid
        task = PendingTask(
            id=str(uuid.uuid4())[:8],
            description=description,
            created_at=time.time(),
            status=TaskStatus.PENDING,
            followup_trigger=followup_trigger,
            followup_prompt=followup_prompt,
            metadata={}
        )
        self.pending_tasks.append(task)
        self.save_session()
        print(f"[Session] Added task: {description}")
        return task

    def check_followups(self) -> List[str]:
        """Check all pending tasks for followup conditions.

        Returns list of followup prompts that should be spoken.
        """
        followups = []
        now = time.time()

        for task in self.pending_tasks:
            if task.status != TaskStatus.WAITING_FOLLOWUP:
                continue

            # Time-based followup (e.g., "remind me in 1 hour")
            if task.followup_trigger == "time" and task.metadata:
                trigger_time = task.metadata.get("trigger_time", 0)
                if now >= trigger_time:
                    followups.append(
                        task.followup_prompt or f"Reminder: {task.description}")
                    task.status = TaskStatus.COMPLETED
                    task.last_check = now

            # File-based followup (e.g., "let me know when download finishes")
            elif task.followup_trigger == "file_exists" and task.metadata:
                file_path = task.metadata.get("path", "")
                if os.path.exists(file_path):
                    followups.append(
                        task.followup_prompt or f"File ready: {os.path.basename(file_path)}")
                    task.status = TaskStatus.COMPLETED
                    task.last_check = now

        if followups:
            self.save_session()

        return followups

    def get_resume_greeting(self) -> Optional[str]:
        """Generate a greeting that acknowledges previous session."""
        if not self.conversation_history:
            return None

        # Check if session was recent (within 4 hours)
        time_away = time.time() - self.last_active_time
        if time_away < 14400:  # 4 hours
            last_topic = self.conversation_history[-2]["content"][:100] if len(
                self.conversation_history) >= 2 else ""
            pending_count = len([t for t in self.pending_tasks if t.status in [
                                TaskStatus.PENDING, TaskStatus.WAITING_FOLLOWUP]])

            if pending_count > 0:
                return f"Welcome back. You have {pending_count} pending tasks. Want me to review them?"
            elif last_topic:
                return f"Welcome back. We were discussing: {last_topic}. Shall I continue?"

        return None

    def record_exchange(self, user_text: str, Zara_response: str) -> None:
        """Record a conversation turn."""
        self.conversation_history.append(
            {"role": "user", "content": user_text})
        self.conversation_history.append(
            {"role": "assistant", "content": Zara_response})

        # Keep history manageable
        if len(self.conversation_history) > 40:
            self.conversation_history = self.conversation_history[-40:]

        self.last_active_time = time.time()
        self.save_session()


# Global singleton
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
