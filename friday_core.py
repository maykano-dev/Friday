"""Friday - lightweight always-on AI assistant core.

Interfaces with a local Ollama server running qwen2.5:1.5b.
Designed for constrained environments: no heavy ML libs, stdlib + requests only.
"""

from __future__ import annotations

import re
from collections import deque
from typing import Dict, List, Optional, Any

import requests

import action_engine
import memory_vault


OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "gemma4:31b-cloud"
REQUEST_TIMEOUT = 60  # seconds

# A "turn" here means one user message + one assistant reply (2 messages).
# Keeping the last 6 turns => up to 12 messages in the rolling window.
MAX_TURNS = 6
MAX_MESSAGES = MAX_TURNS * 2

SYSTEM_PROMPT = (
    "You are Friday, a highly capable general assistant. Your goal is to help any user with any task, from coding and writing to web research and PC management. Be concise, witty, and fast. Formulate your spoken response in exactly ONE short sentence. Always use <EXECUTE> tags for system actions like creating folders or opening apps."
    "\n\n"
    "ACTION PROTOCOL: If the user asks you to create a folder or directory, "
    "append an action block at the VERY END of your reply formatted exactly like this:\n"
    "<EXECUTE>{\"action\": \"create_dir\", \"path\": \"C:/absolute/path/here\"}</EXECUTE>\n"
    "Rules for the action block:\n"
    "- Use strictly valid JSON with DOUBLE quotes only.\n"
    "- Use forward slashes in the path (e.g. C:/Users/Maikano/Desktop/ProjectX).\n"
    "- Put NOTHING after the closing </EXECUTE> tag.\n"
    "- Keep the spoken part before the tag short, like 'Done.' or 'On it.'"
)

# Regex used to lift an embedded action payload out of the model's reply.
_EXECUTE_PATTERN = re.compile(r"<EXECUTE>(.*?)</EXECUTE>", re.DOTALL)
_action_executor = action_engine.ActionExecutor()

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


def _build_messages(
    user_text: str,
    relevant_memories: Optional[List[str]] = None,
) -> List[Dict[str, str]]:
    """Assemble the full message list sent to Ollama.

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
                context_files_text += f"\n\n--- FILE CONTEXT ---\n{card.content[:2000]}\n" # Cap arbitrarily to avoid buffer overflow
                
    if context_files_text:
        sys_text += f"\n\nThe user has loaded the following files into your Context Wing:{context_files_text}"
        
    if image_data_list:
        sys_text += "\n\nOBSERVER MODE ACTIVE: The user has shown you visual data. Observe it carefully."

    messages: List[Dict[str, Any]] = [{"role": "system", "content": sys_text}]

    # Prepend chat history
    recent = memory_vault.get_recent_memories(limit=10)
    for m in recent:
        if m.startswith("User:"):
            messages.append({"role": "user", "content": m.replace("User: ", "", 1)})
        elif m.startswith("Friday:"):
            messages.append({"role": "assistant", "content": m.replace("Friday: ", "", 1)})

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
    """Send `user_text` to the local Ollama server and return the reply string.

    Maintains a rolling context window of the last 6 turns. Returns a
    human-readable error string if the server is unreachable or misbehaving,
    so the caller never has to handle exceptions.
    """
    if not user_text or not user_text.strip():
        return "I didn't catch that."

    # Intercept explicit save commands and bypass the Ollama call entirely.
    save_payload = _extract_save_payload(user_text)
    if save_payload is not None:
        if save_payload:
            memory_vault.store_memory(save_payload)
        return "Saved to memory, sir."
        
    user_lower = user_text.lower().strip()
    for trigger in VOICE_INGEST_TRIGGERS:
        if trigger in user_lower:
            try:
                import pygame
                import time
                from ui_engine import MANUAL_INGEST_CMD
                pygame.event.post(pygame.event.Event(MANUAL_INGEST_CMD))
                time.sleep(0.5) # Wait for ui_engine thread to naturally mount the payload
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
    
    # Check if the last msg has images to determine model
    model_to_use = MODEL_NAME
    if messages and "images" in messages[-1]:
        model_to_use = "llama3.2-vision"

    payload = {
        "model": model_to_use,
        "messages": messages,
        "stream": True,  # NOW STREAMING!
        "options": {
            "temperature": 0.7,
            "num_ctx": 1024,
            "num_thread": 4,
        },
    }

    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=REQUEST_TIMEOUT, stream=True)
        resp.raise_for_status()
    except requests.exceptions.ConnectionError:
        return "I can't reach the local Ollama server. Is it running on port 11434?"
    except requests.exceptions.Timeout:
        return "The model took too long to respond. Please try again."
    except requests.exceptions.HTTPError as e:
        return f"Ollama returned an error: {e.response.status_code}."
    except requests.exceptions.RequestException as e:
        return f"Network error talking to Ollama: {e}."

    import json, local_voice, main

    reply_accum = ""
    sentence_buffer = ""
    in_execute_block = False
    action_block = ""
    
    if hasattr(main, "ui") and main.ui: main.ui.set_state("TALKING")

    # Regex block boundaries natively
    for line in resp.iter_lines():
        if not line: continue
        try:
            chunk_data = json.loads(line.decode("utf-8"))
            chunk = chunk_data.get("message", {}).get("content", "")
        except: continue
        
        reply_accum += chunk
        
        # Check execution parsing blocks!
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
                        try: _action_executor.execute_payload(json_payload)
                        except Exception as e: print(f"[Friday Action Err]: {e}")
            continue

        sentence_buffer += chunk
        if hasattr(main, "ui") and main.ui: main.ui.set_subtitle_text(reply_accum.replace("<EXECUTE>","").replace("</EXECUTE>",""))
            
        # Fast Sentence Yield boundary — includes comma for snappy clause-level playback
        if any(p in sentence_buffer for p in [". ", "? ", "! ", ", ", "\n"]):
            out_sentence = sentence_buffer.strip()
            if out_sentence:
                local_voice.speak(out_sentence)
            sentence_buffer = ""
            
    # Flush trailing text
    if sentence_buffer.strip():
        local_voice.speak(sentence_buffer.strip())

    reply = _EXECUTE_PATTERN.sub("", reply_accum).strip()
    if not reply:
        reply = "Done."

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
