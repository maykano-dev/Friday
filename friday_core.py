"""Friday - lightweight always-on AI assistant core.

Interfaces with the Groq Cloud API for 300+ token/sec inference.
Designed for constrained environments: no heavy ML libs, stdlib + requests only.
"""

from __future__ import annotations

import os
import re
from collections import deque
from typing import Dict, List, Optional, Any

import requests

import action_engine
import memory_vault

# ── Groq Cloud API ──────────────────────────────────────────────────────────
# Auto-load .env
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL_NAME = "llama-3.3-70b-versatile"
REQUEST_TIMEOUT = 30  # Groq is fast — 30s is generous

# A "turn" here means one user message + one assistant reply (2 messages).
# Keeping the last 6 turns => up to 12 messages in the rolling window.
MAX_TURNS = 6
MAX_MESSAGES = MAX_TURNS * 2

SYSTEM_PROMPT = (
    "You are Friday, a highly capable, witty, and natural assistant. "
    "Your goal is to help with any task while maintaining a smooth, human-like conversation. "
    "Treat all messages in the chat history as COMPLETED context; do not repeat or re-execute "
    "any actions mentioned in history unless specifically requested again in the current message. "
    "Always use <EXECUTE> tags for system actions. Formulate your spoken responses as complete, "
    "natural sentences. Do not use robotic filler like 'Done' or 'Execute' unless it fits "
    "the natural flow of conversation."
)

ACTION_PROTOCOL_PROMPT = (
    "ACTION PROTOCOL: If you need to trigger a system action, append an action block at the "
    "VERY END of your reply formatted exactly like this:\n"
    "<EXECUTE>{\"action\": \"create_dir\", \"path\": \"C:/absolute/path/here\"}</EXECUTE>\n"
    "Rules for the action block:\n"
    "- Use strictly valid JSON with DOUBLE quotes only.\n"
    "- Use forward slashes in paths.\n"
    "- Put NOTHING after the closing </EXECUTE> tag.\n"
    "- Keep all markup inside the action block only."
)

SYSTEM_BOOT_TRIGGER = "SYSTEM_BOOT:"
SYSTEM_BOOT_PROMPT = (
    "The next message is an internal startup trigger, not a user request. "
    "Reply with one unique, concise, witty, casual startup greeting. "
    "Do not use action tags."
)

# Regex used to lift an embedded action payload out of the model's reply.
_EXECUTE_PATTERN = re.compile(r"<EXECUTE>(.*?)</EXECUTE>", re.DOTALL)
_action_executor = action_engine.ActionExecutor()
_EXECUTE_OPEN_TAG = "<EXECUTE>"
_EXECUTE_CLOSE_TAG = "</EXECUTE>"

# Phrases that tell Friday to persist a memory instead of chatting.
# Matched case-insensitively at the start of the user's input.
SAVE_TRIGGERS = (
    "friday, remember this:",
    "friday remember this:",
    "friday, remember that:",
    "friday remember that:",
    "save this to memory:",
    "save to memory:",
    "remember this:",
    "remember that:",
)

VOICE_INGEST_TRIGGERS = (
    "ingest",
    "look at this",
    "analyze this",
    "what is this",
)

# Rolling short-term memory: only user/assistant turns live here.
# The system prompt is prepended fresh on every call, so it never gets evicted.
_history: Deque[Dict[str, str]] = deque(maxlen=MAX_MESSAGES)


def _extract_save_payload(user_text: str) -> Optional[str]:
    """If `user_text` begins with a save trigger, return the text to store.

    Returns None if the input is not a save command.
    """
    lowered = user_text.lstrip().lower()
    for trigger in SAVE_TRIGGERS:
        if lowered.startswith(trigger):
            # Strip trigger from the original (preserving original casing).
            stripped = user_text.lstrip()
            payload = stripped[len(trigger):].strip()
            return payload
    return None


def _is_system_boot_trigger(user_text: str) -> bool:
    """Return True when the prompt is an internal boot-time trigger."""
    return user_text.lstrip().upper().startswith(SYSTEM_BOOT_TRIGGER)


def _post_groq(payload: Dict[str, Any], *, stream: bool) -> requests.Response | str:
    """Send a request to Groq and normalize transport-layer errors."""
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(
            GROQ_URL,
            json=payload,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
            stream=stream,
        )
        resp.raise_for_status()
        return resp
    except requests.exceptions.ConnectionError:
        return "Can't reach the Groq API. Check your internet connection."
    except requests.exceptions.Timeout:
        return "Groq took too long to respond. Please try again."
    except requests.exceptions.HTTPError as e:
        return f"Groq API error: {e.response.status_code} — {e.response.text[:200]}."
    except requests.exceptions.RequestException as e:
        return f"Network error: {e}."


def _visible_reply_text(raw_text: str) -> str:
    """Strip complete and partial EXECUTE markup from user-facing text."""
    cleaned = _EXECUTE_PATTERN.sub("", raw_text)

    # Hide an opened execute block even before the closing tag arrives.
    open_tag_index = cleaned.find(_EXECUTE_OPEN_TAG)
    if open_tag_index != -1 and _EXECUTE_CLOSE_TAG not in cleaned[open_tag_index:]:
        cleaned = cleaned[:open_tag_index]

    # Hide a trailing partial execute tag fragment such as "<EXE" or "</EXEC".
    partial_start = cleaned.rfind("<")
    if partial_start != -1:
        fragment = cleaned[partial_start:]
        if _EXECUTE_OPEN_TAG.startswith(fragment) or _EXECUTE_CLOSE_TAG.startswith(fragment):
            cleaned = cleaned[:partial_start]

    return cleaned


def _build_system_boot_messages(user_text: str) -> List[Dict[str, str]]:
    """Build a minimal hidden boot prompt without chat or memory side effects."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": SYSTEM_BOOT_PROMPT},
        {"role": "user", "content": user_text},
    ]


def _build_messages(
    user_text: str,
    relevant_memories: Optional[List[str]] = None,
) -> List[Dict[str, str]]:
    """Assemble the full message list sent to Groq Cloud API.

    `relevant_memories`, if provided, are injected as additional system-role
    notes right after the main system prompt so the model treats them as
    authoritative context rather than part of the ongoing dialog.
    """
    sys_text = SYSTEM_PROMPT
    try:
        insight = memory_vault.get_latest_context_insight()
        if insight:
            sys_text += f"\n\nCURRENT OBJECTIVE / INSIGHT: {insight}\nKeep this context in mind as you assist."
    except Exception as e:
        print(f"[Friday Core] failed to pull context insight: {e}")

    # Parse Virtual Context Wing Layout
    import main
    context_files_text = ""
    image_data_list = []

    if hasattr(main, "ui") and main.ui:
        for card in main.ui.context_cards:
            if card.card_type == "IMAGE":
                image_data_list.append(card.content)
            else:
                # Cap arbitrarily to avoid buffer overflow
                context_files_text += f"\n\n--- FILE CONTEXT ---\n{card.content[:2000]}\n"

    if context_files_text:
        sys_text += f"\n\nThe user has loaded the following files into your Context Wing:{context_files_text}"

    if image_data_list:
        sys_text += "\n\nOBSERVER MODE ACTIVE: The user has shown you visual data. Observe it carefully."

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": sys_text},
        {"role": "system", "content": ACTION_PROTOCOL_PROMPT},
    ]

    # Prepend chat history
    recent = memory_vault.get_recent_memories(limit=10)
    for m in recent:
        if m.startswith("User:"):
            messages.append(
                {"role": "user", "content": m.replace("User: ", "", 1)})
        elif m.startswith("Friday:"):
            messages.append(
                {"role": "assistant", "content": m.replace("Friday: ", "", 1)})

    # Chroma Context Injection
    semantic_matches = memory_vault.semantic_search(user_text)
    if semantic_matches:
        sem_context = "\n".join(semantic_matches)
        sys_text += f"\n\n[ Semantic Memory Search matches: ]\n{sem_context}\n"

    user_msg = {"role": "user", "content": user_text}
    if image_data_list:
        user_msg["images"] = image_data_list

    messages.append(user_msg)

    return messages


def generate_response(user_text: str) -> str:
    """Send `user_text` to Groq Cloud API and return the reply string.

    Maintains a rolling context window of the last 6 turns. Returns a
    human-readable error string if the server is unreachable or misbehaving,
    so the caller never has to handle exceptions.
    """
    if not user_text or not user_text.strip():
        return "I didn't catch that."

    # Intercept explicit save commands and bypass the Groq call entirely.
    save_payload = _extract_save_payload(user_text)
    if save_payload is not None:
        if save_payload:
            memory_vault.store_memory(save_payload)
        return "Saved to memory."

    if _is_system_boot_trigger(user_text):
        if not GROQ_API_KEY:
            return "Friday initialized. Ready for input."

        payload = {
            "model": MODEL_NAME,
            "messages": _build_system_boot_messages(user_text),
            "stream": False,
            "temperature": 0.9,
            "max_tokens": 80,
        }

        resp = _post_groq(payload, stream=False)
        if isinstance(resp, str):
            return resp

        try:
            data = resp.json()
            reply = data.get("choices", [{}])[0].get(
                "message", {}).get("content", "")
        except ValueError:
            return "Friday initialized. Ready for input."

        reply = _visible_reply_text(reply).strip()
        return reply or "Friday initialized. Ready for input."

    user_lower = user_text.lower().strip()
    for trigger in VOICE_INGEST_TRIGGERS:
        if trigger in user_lower:
            try:
                import pygame
                import time
                from ui_engine import MANUAL_INGEST_CMD
                pygame.event.post(pygame.event.Event(MANUAL_INGEST_CMD))
                # Wait for ui_engine thread to naturally mount the payload
                time.sleep(0.5)
            except:
                pass
            break

    # Pull any long-term memories relevant to this turn so we can inject
    # them into the system context before the model sees the user's words.
    try:
        relevant_memories = memory_vault.retrieve_memory(user_text)
    except Exception as e:
        print(f"[Friday Core] memory retrieval failed: {e}")
        relevant_memories = []

    messages = _build_messages(user_text, relevant_memories)

    if not GROQ_API_KEY:
        return "GROQ_API_KEY is not set. Please add it to your .env file."

    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "stream": True,
        "temperature": 0.7,
        "max_tokens": 1024,
    }

    resp = _post_groq(payload, stream=True)
    if isinstance(resp, str):
        return resp

    import json
    import local_voice
    import main

    reply_accum = ""
    sentence_buffer = ""
    word_count = 0
    visible_length = 0
    in_execute_block = False
    action_block = ""
    sentence_endings = (".", "!", "?")
    sentence_pattern = re.compile(r"^(.+?[.!?])(?=\s|$)", re.DOTALL)

    if hasattr(main, "ui") and main.ui:
        main.ui.set_state("TALKING")

    def _flush_buffer(force: bool = False) -> None:
        """Speak only complete thoughts so TTS keeps natural cadence."""
        nonlocal sentence_buffer, word_count
        while True:
            phrase = sentence_buffer.strip()
            if not phrase:
                sentence_buffer = ""
                word_count = 0
                return

            match = sentence_pattern.match(phrase)
            if match:
                local_voice.speak(match.group(1).strip())
                sentence_buffer = phrase[match.end():].lstrip()
                word_count = len(sentence_buffer.split()) if sentence_buffer else 0
                continue

            if word_count >= 20:
                local_voice.speak(phrase)
                sentence_buffer = ""
                word_count = 0
                return

            if force:
                if not phrase.endswith(sentence_endings):
                    phrase = f"{phrase}."
                local_voice.speak(phrase)
                sentence_buffer = ""
                word_count = 0
            return

    for line in resp.iter_lines():
        if not line:
            continue
        line_str = line.decode("utf-8")

        # Groq uses OpenAI SSE format: "data: {json}" or "data: [DONE]"
        if line_str.startswith("data: "):
            line_str = line_str[6:]
        if line_str.strip() == "[DONE]":
            break

        try:
            chunk_data = json.loads(line_str)
            chunk = chunk_data.get("choices", [{}])[0].get(
                "delta", {}).get("content", "")
        except:
            continue
        if not chunk:
            continue

        reply_accum += chunk

        # Check execution parsing blocks
        if "<EXECUTE>" in reply_accum and not in_execute_block:
            in_execute_block = True

        if in_execute_block:
            action_block += chunk
            if "</EXECUTE>" in action_block:
                in_execute_block = False
                match = _EXECUTE_PATTERN.search(reply_accum)
                if match:
                    json_payload = match.group(1).strip()
                    if json_payload:
                        try:
                            _action_executor.execute_payload(json_payload)
                        except Exception as e:
                            print(f"[Friday Action Err]: {e}")
            continue

        visible_reply = _visible_reply_text(reply_accum)

        # Update subtitle live
        if hasattr(main, "ui") and main.ui:
            main.ui.set_subtitle_text(visible_reply)

        # Accumulate into sentence buffer
        if len(visible_reply) < visible_length:
            visible_length = len(visible_reply)

        visible_delta = visible_reply[visible_length:]
        visible_length = len(visible_reply)

        sentence_buffer += visible_delta
        word_count += len(visible_delta.split())
        _flush_buffer()

    # Flush any remaining text
    _flush_buffer(force=True)

    reply = _visible_reply_text(reply_accum).strip()
    if not reply:
        reply = "All set."

    try:
        memory_vault.store_memory(f"User: {user_text}")
        memory_vault.store_memory(f"Friday: {reply}")
    except Exception as e:
        print(f"[Friday Core] failed to save to vault: {e}")

    return reply


def reset_memory() -> None:
    """Wipe the rolling conversation window."""
    _history.clear()


if __name__ == "__main__":
    print("Friday is online. Type 'quit' to exit.\n")
    while True:
        try:
            user_in = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if user_in.lower() in {"quit", "exit"}:
            break
        print("Friday:", generate_response(user_in), "\n")
