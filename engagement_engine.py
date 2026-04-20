"""Zara - proactive engagement engine.

Watches two triggers from a background daemon thread:

  * Idle Timer    -> if the user hasn't spoken for `idle_timeout_seconds`,
                     fire a random conversation starter.
  * Context Trigger -> if a watched keyword appears in a recently modified
                     file under `scan_dir`, fire a contextual prompt.

When triggered, it calls a registered callback with a single string. The
callback (in main.py) is responsible for queueing the prompt so the main
loop can route it through zara_core.generate_response() at a safe moment
(i.e. when the mic is closed).
"""

from __future__ import annotations

import os
import random
import threading
import time
from typing import Callable, Iterable, List, Optional, Set, Tuple


# Phrases framed as Zara's own initiations. They are passed straight into
# zara_core.generate_response() as if the user said them, so the LLM will
# treat them as conversational prompts and reply in Zara's voice.
DEFAULT_CONVERSATION_STARTERS: List[str] = [
    "Sir, you have been quiet for a while. Briefly check in and ask if I can help.",
    "Sir, I notice it has been some time since you last spoke. Suggest a short break in one sentence.",
    "It is unusually quiet. Greet the user warmly and ask if there is anything they need.",
    "Sir, you have been heads-down for a while. Recommend a quick stretch or a glass of water in one short line.",
    "It has been a while. Offer to summarize what we were last discussing, in one sentence.",
]

DEFAULT_CONTEXT_KEYWORDS: List[str] = [
    "Error",
    "Exception",
    "TODO",
    "FIXME",
    "C2G Logistics",
]

# Only consider files with these extensions when scanning for keywords.
_DEFAULT_SCAN_EXTS: Tuple[str, ...] = (
    ".py", ".txt", ".md", ".log", ".json", ".js", ".ts",
    ".html", ".css", ".yml", ".yaml", ".ini", ".cfg",
)


class EngagementEngine:
    """Background daemon that proactively pokes the assistant when warranted."""

    def __init__(
        self,
        idle_timeout_seconds: int = 1800,           # 30 minutes
        scan_dir: Optional[str] = None,             # None disables file scanning
        keywords: Optional[Iterable[str]] = None,
        starters: Optional[Iterable[str]] = None,
        check_interval_seconds: int = 30,
        scan_window_seconds: int = 300,             # only files modified <5min ago
        scan_exts: Optional[Iterable[str]] = None,
        max_file_bytes: int = 1_000_000,
    ) -> None:
        self.idle_timeout = max(1, int(idle_timeout_seconds))
        self.scan_dir = scan_dir
        self.keywords = list(keywords or DEFAULT_CONTEXT_KEYWORDS)
        self.starters = list(starters or DEFAULT_CONVERSATION_STARTERS)
        self.check_interval = max(1, int(check_interval_seconds))
        self.scan_window = max(1, int(scan_window_seconds))
        self.scan_exts = tuple(e.lower() for e in (scan_exts or _DEFAULT_SCAN_EXTS))
        self.max_file_bytes = int(max_file_bytes)

        self._lock = threading.Lock()
        self._last_interaction = time.time()
        self._last_idle_alert = 0.0

        # Each (path, keyword, mtime_int) tuple is alerted on at most once.
        self._seen_triggers: Set[Tuple[str, str, int]] = set()

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._callback: Optional[Callable[[str], None]] = None

        # Seed: anything that already matches at startup is considered "old"
        # and won't fire a proactive alert. Only NEW occurrences will.
        if self.scan_dir and os.path.isdir(self.scan_dir):
            try:
                self._prime_seen_triggers()
            except Exception as e:
                print(f"[Zara Engagement] prime scan failed: {e}")

    # ---- Public API --------------------------------------------------------

    def start(self, callback: Callable[[str], None]) -> None:
        """Start the background loop. `callback(prompt_text)` is invoked on a trigger."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._callback = callback
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def notify_user_spoke(self) -> None:
        """Main loop calls this whenever the user actually speaks."""
        with self._lock:
            self._last_interaction = time.time()
            self._last_idle_alert = 0.0

    # ---- Background loop ---------------------------------------------------

    def _run(self) -> None:
        while self._running:
            try:
                self._check_idle()
                self._check_context()
            except Exception as e:
                print(f"[Zara Engagement] check failed: {e}")

            # Sleep in 1s slices so stop() responds quickly.
            for _ in range(self.check_interval):
                if not self._running:
                    return
                time.sleep(1)

    # ---- Trigger checks ----------------------------------------------------

    def _check_idle(self) -> None:
        now = time.time()
        with self._lock:
            elapsed = now - self._last_interaction
            since_alert = now - self._last_idle_alert

        # Fire only if we've been idle past the threshold AND we haven't
        # already alerted within the same idle window (prevents spam).
        if elapsed >= self.idle_timeout and since_alert >= self.idle_timeout:
            starter = random.choice(self.starters)
            with self._lock:
                self._last_idle_alert = now
            self._dispatch(starter)

    def _check_context(self) -> None:
        if not self.scan_dir or not os.path.isdir(self.scan_dir):
            return

        for path, content, mtime_int in self._iter_recent_files():
            for kw in self.keywords:
                if kw in content:
                    fp = (path, kw, mtime_int)
                    if fp in self._seen_triggers:
                        continue
                    self._seen_triggers.add(fp)
                    prompt = (
                        f"You just noticed the keyword '{kw}' in the file "
                        f"'{os.path.basename(path)}'. Briefly offer to help "
                        f"the user with it, in one short sentence."
                    )
                    self._dispatch(prompt)
                    return  # at most one context alert per scan cycle

    # ---- File-scan helpers -------------------------------------------------

    def _iter_recent_files(self):
        """Yield (path, content, mtime_int) for recently-modified scanned files."""
        now = time.time()
        try:
            entries = os.listdir(self.scan_dir)
        except OSError:
            return

        for entry in entries:
            full = os.path.join(self.scan_dir, entry)
            if not os.path.isfile(full):
                continue
            if not entry.lower().endswith(self.scan_exts):
                continue
            try:
                size = os.path.getsize(full)
                mtime = os.path.getmtime(full)
            except OSError:
                continue
            if size > self.max_file_bytes:
                continue
            if now - mtime > self.scan_window:
                continue
            try:
                with open(full, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except OSError:
                continue
            yield full, content, int(mtime)

    def _prime_seen_triggers(self) -> None:
        """At startup, mark every existing match as already-seen so we only
        fire on NEW keyword occurrences, not on the static codebase."""
        if not self.scan_dir or not os.path.isdir(self.scan_dir):
            return
        try:
            entries = os.listdir(self.scan_dir)
        except OSError:
            return

        for entry in entries:
            full = os.path.join(self.scan_dir, entry)
            if not os.path.isfile(full):
                continue
            if not entry.lower().endswith(self.scan_exts):
                continue
            try:
                if os.path.getsize(full) > self.max_file_bytes:
                    continue
                mtime_int = int(os.path.getmtime(full))
                with open(full, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except OSError:
                continue
            for kw in self.keywords:
                if kw in content:
                    self._seen_triggers.add((full, kw, mtime_int))

    # ---- Internal ----------------------------------------------------------

    def _dispatch(self, prompt: str) -> None:
        if self._callback is None:
            return
        try:
            self._callback(prompt)
        except Exception as e:
            print(f"[Zara Engagement] callback failed: {e}")
