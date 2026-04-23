"""Zara - lightweight always-on AI assistant core.

Interfaces with the Groq Cloud API for 300+ token/sec inference.
Designed for constrained environments: no heavy ML libs, stdlib + requests only.
"""

from __future__ import annotations

import os
import re
import threading
from collections import deque
from typing import Dict, List, Optional, Any

import requests

import action_engine
import memory_vault
from user_prefs import get_prefs
from zara_vision import get_vision, VisionMode

_handler_active = threading.Event()
_in_vision_handler = False

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

def get_dynamic_system_prompt() -> str:
    import json
    honorific = "Sir"
    if os.path.exists("zara_prefs.json"):
        try:
            with open("zara_prefs.json", "r") as f:
                honorific = json.load(f).get("honorific", "Sir")
        except: pass
    
    return (
        f"You are Zara, the ultimate AI assistant. Address the user as '{honorific}'. "
        "Keep responses CONCISE (1-3 sentences). Focus on speed and system mastery."
    )


def _handle_complex_task(task_description: str):
    """Spawns an agent team to handle a high-complexity request."""
    import agent_orchestrator
    # Initialize the orchestrator with Zara's own LLM logic as the brain
    orchestrator = agent_orchestrator.get_orchestrator(llm_callback=generate_response)
    if orchestrator:
        orchestrator.start()
        
        # Create a specialized coding team (Planner -> Coder -> Reviewer)
        workflow = orchestrator.create_coding_team(task_description)
        result = orchestrator.execute_workflow(workflow)
        
        return result
    return "Orchestrator unavailable."

def get_system_prompt():
    """Alias for user's requested function name."""
    return get_dynamic_system_prompt()

# SYSTEM_PROMPT is deprecated, use get_dynamic_system_prompt() instead.

ACTION_PROTOCOL_PROMPT = (
    "🎯 ZARA CAPABILITIES MANIFEST 🎯\n"
    "You have access to these capabilities. Use them when the user asks.\n\n"
    "=== FILE SYSTEM ACTIONS (use <EXECUTE> block) ===\n"
    "- Create folder: <EXECUTE>{\"action\": \"create_dir\", \"path\": \"~/Documents/Folder\"}</EXECUTE>\n"
    "- Write file: <EXECUTE>{\"action\": \"write_file\", \"path\": \"~/file.txt\", \"content\": \"text\"}</EXECUTE>\n"
    "- Run script: <EXECUTE>{\"action\": \"run_script\", \"command\": \"python script.py\"}</EXECUTE>\n"
    "- Open app: <EXECUTE>{\"action\": \"start_app\", \"app_name\": \"notepad\"}</EXECUTE>\n\n"
    "=== WEB ACTIONS (use <EXECUTE> block) ===\n"
    "- Open website: <EXECUTE>{\"action\": \"open_url\", \"url\": \"https://example.com\"}</EXECUTE>\n"
    "- Search web: <EXECUTE>{\"action\": \"web_search\", \"query\": \"search terms\"}</EXECUTE>\n"
    "- Web scrape: <EXECUTE>{\"action\": \"web_scrape\", \"url\": \"https://site.com\"}</EXECUTE>\n\n"
    "=== ADVANCED WEB BROWSING (use <EXECUTE> block) ===\n"
    "- Browse website: <EXECUTE>{\"action\": \"browse_web\", \"url\": \"https://example.com\", \"task\": \"find pricing\"}</EXECUTE>\n"
    "- Fill form: <EXECUTE>{\"action\": \"fill_form\", \"fields\": {\"name\": \"John\", \"email\": \"john@example.com\"}, \"submit\": true}</EXECUTE>\n"
    "- Click element: <EXECUTE>{\"action\": \"click_element\", \"text\": \"Sign In\"}</EXECUTE>\n"
    "- Complex Task (Multi-Agent): <EXECUTE>{\"action\": \"complex_task\", \"task\": \"Build a full data scraper for stock prices\"}</EXECUTE>\n"

    "=== KNOWLEDGE & RESEARCH (just answer conversationally) ===\n"
    "- Weather for any city (say: 'What's the weather in Tokyo?')\n"
    "- Dictionary definitions (say: 'Define serendipity')\n"
    "- Synonyms and rhymes (say: 'Synonyms for happy' or 'Rhymes with cat')\n"
    "- Wikipedia summaries (say: 'Tell me about quantum computing')\n"
    "- DuckDuckGo instant answers (say: 'Search for machine learning')\n"
    "- Country information (say: 'Tell me about France')\n"
    "- University information (say: 'Find universities in London')\n"
    "- Public holidays (say: 'Holidays in US this year')\n\n"
    "=== ENTERTAINMENT (just answer conversationally) ===\n"
    "- Random jokes (say: 'Tell me a joke')\n"
    "- Chuck Norris jokes (say: 'Chuck Norris joke')\n"
    "- Inspirational quotes (say: 'Give me a quote')\n"
    "- Cat facts (say: 'Tell me a cat fact')\n"
    "- Dog facts (say: 'Tell me a dog fact')\n"
    "- Useless facts (say: 'Give me a useless fact')\n"
    "- Advice (say: 'Give me advice')\n"
    "- Activity suggestions (say: 'I'm bored')\n"
    "- Number trivia (say: 'Tell me about the number 42')\n"
    "- Date facts (say: 'What happened on this day?')\n\n"
    "=== NEWS & TECH (just answer conversationally) ===\n"
    "- Hacker News top stories (say: 'What's on Hacker News?')\n"
    "- DEV.to articles (say: 'Top DEV.to articles')\n"
    "- GitHub user info (say: 'GitHub user torvalds')\n"
    "- NPM package info (say: 'NPM package react')\n"
    "- PyPI package info (say: 'PyPI package numpy')\n"
    "- HTTP status codes (say: 'What is HTTP 404?')\n"
    "- CVE vulnerabilities (say: 'CVE-2021-44228')\n\n"
    "=== FINANCE & CRYPTO (just answer conversationally) ===\n"
    "- Cryptocurrency prices (say: 'Bitcoin price' or 'Ethereum price')\n"
    "- Exchange rates (say: 'USD to EUR' or 'Convert 100 USD to JPY')\n\n"
    "=== SPACE & SCIENCE (just answer conversationally) ===\n"
    "- NASA picture of the day (say: 'Show me NASA picture')\n"
    "- ISS current location (say: 'Where is the ISS?')\n"
    "- Next SpaceX launch (say: 'When is the next SpaceX launch?')\n\n"
    "=== FOOD & RECIPES (just answer conversationally) ===\n"
    "- Recipe search (say: 'Recipe for pasta carbonara' or 'How to make pizza')\n\n"
    "=== UTILITIES (just answer conversationally) ===\n"
    "- IP address lookup (say: 'What's my IP?')\n"
    "- Email validation (say: 'Validate test@email.com')\n"
    "- URL shortening (say: 'Shorten https://example.com')\n"
    "- QR code generation (say: 'Generate QR code for hello world')\n"
    "- Time in any timezone (say: 'What time is it in Tokyo?')\n\n"
    "=== MEDIA CONTROLS (use <EXECUTE> block) ===\n"
    "- Play/pause: <EXECUTE>{\"action\": \"media_control\", \"command\": \"play_pause\"}</EXECUTE>\n"
    "- Next track: <EXECUTE>{\"action\": \"media_control\", \"command\": \"next\"}</EXECUTE>\n"
    "- Previous track: <EXECUTE>{\"action\": \"media_control\", \"command\": \"previous\"}</EXECUTE>\n"
    "- Volume up: <EXECUTE>{\"action\": \"media_control\", \"command\": \"volume_up\"}</EXECUTE>\n"
    "- Volume down: <EXECUTE>{\"action\": \"media_control\", \"command\": \"volume_down\"}</EXECUTE>\n"
    "- Mute: <EXECUTE>{\"action\": \"media_control\", \"command\": \"mute\"}</EXECUTE>\n\n"
    "=== AMBIENT MODE (use <EXECUTE> block) ===\n"
    "- Enter ambient mode: <EXECUTE>{\"action\": \"ambient_mode\", \"sound\": \"rain\"}</EXECUTE>\n"
    "  (Available sounds: rain, ocean, forest, white-noise)\n\n"
    "⚠️ CRITICAL RULES:\n"
    "1. ONLY use <EXECUTE> for: create_dir, write_file, run_script, start_app, open_url, web_search, web_scrape, media_control, ambient_mode\n"
    "2. For everything else (weather, jokes, facts, news, crypto, recipes, etc.), just ANSWER CONVERSATIONALLY - the system handles it automatically\n"
    "3. DO NOT create folders unless the user explicitly says 'create a folder' or 'make a directory'\n"
    "4. If the user asks 'what can you do?', list the categories above enthusiastically\n"
    "5. Be confident! You have dozens of capabilities - use them when asked.\n"
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

# Phrases that tell Zara to persist a memory instead of chatting.
# Matched case-insensitively at the start of the user's input.
SAVE_TRIGGERS = (
    "Zara, remember this:",
    "Zara remember this:",
    "Zara, remember that:",
    "Zara remember that:",
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
_history: deque[Dict[str, str]] = deque(maxlen=MAX_MESSAGES)


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


def _handle_what_can_you_do() -> str:
    """Tell the user what Zara can do."""
    return (
        "🎯 I'm Zara, and I can handle quite a lot, Sir:\n\n"
        "📚 KNOWLEDGE: Weather, definitions, synonyms, Wikipedia, country info, university search\n"
        "😄 ENTERTAINMENT: Jokes, quotes, cat/dog facts, advice, number trivia\n"
        "📰 NEWS: Hacker News, DEV.to articles, GitHub profiles, NPM/PyPI packages\n"
        "💰 FINANCE: Cryptocurrency prices, exchange rates\n"
        "🚀 SPACE: NASA picture of the day, ISS location, SpaceX launches\n"
        "🍳 FOOD: Recipe search for any dish\n"
        "🛠️ UTILITIES: IP lookup, email validation, URL shortening, QR codes, time zones\n"
        "🎮 SYSTEM: Create folders, write files, run scripts, open apps and websites\n"
        "🎵 MEDIA: Play/pause, next/previous track, volume control\n"
        "🤖 AUTONOMOUS: Web scraping, form filling, multi-step research, store management\n\n"
        "Just ask naturally — I'll handle the rest."
    )


def _handle_web_search_direct(text: str) -> str:
    """Direct web search that opens browser and speaks results."""
    import webbrowser
    from urllib.parse import quote_plus

    search_phrases = ["search for", "search", "google",
                      "look up", "find", "search the web for"]
    query = text.lower()
    for phrase in search_phrases:
        query = query.replace(phrase, "")
    query = query.strip()

    if not query:
        query = text

    search_url = f"https://www.google.com/search?q={quote_plus(query)}"
    try:
        webbrowser.open(search_url)
    except Exception:
        pass

    try:
        from free_web_tools import get_web_tools
        web = get_web_tools()
        instant = web.search_duckduckgo(query)
        if instant:
            return f"I've opened a Google search for '{query}'. Here's what I found instantly: {instant[:500]}"
    except Exception:
        pass

    return f"I've opened a Google search for '{query}' in your browser. Take a look!"


def _handle_volume(direction: str) -> str:
    """Handle volume control commands."""
    import json
    import action_engine

    command_map = {
        "up": "volume_up",
        "down": "volume_down",
        "mute": "mute"
    }

    payload = {
        "action": "media_control",
        "command": command_map.get(direction, direction)
    }

    executor = action_engine.ActionExecutor()

    # Execute and capture announcement
    executor.media_control(payload)

    # Return the announcement set by media_control
    return payload.get("announcement", "Done, Sir.")


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
        {"role": "system", "content": get_dynamic_system_prompt()},
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
    sys_text = get_dynamic_system_prompt()
    try:
        insight = memory_vault.get_latest_context_insight()
        if insight:
            sys_text += f"\n\nCURRENT OBJECTIVE / INSIGHT: {insight}\nKeep this context in mind as you assist."
    except Exception as e:
        print(f"[Zara Core] failed to pull context insight: {e}")

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

    # Prepend chat history (oldest first)
    for msg in list(_history):
        messages.append(msg)

    # Use vault only for long-term factual memories
    recent = memory_vault.get_recent_memories(limit=5)
    if recent:
        mem_text = "\n".join(f"- {m}" for m in reversed(recent))
        sys_text += f"\n\nRECENT CONTEXT:\n{mem_text}"

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
    """Generate a response using the Groq Cloud API."""
    if not user_text or not user_text.strip():
        return "I didn't catch that."
    
    # Check what capabilities the user is asking for
    if user_text.lower().strip() in ["what can you do", "what can you do?", "help", "capabilities"]:
        return _handle_what_can_you_do()

    # Let the LLM path be unblocked. Only lock around keyword handlers.
    return _generate_response_impl(user_text)


def _generate_response_impl(user_text: str) -> str:
    # ── 1. Check for internal/system triggers ──
    if _is_system_boot_trigger(user_text):
        msgs = _build_system_boot_messages(user_text)
        try:
            resp = _post_groq({"model": MODEL_NAME, "messages": msgs}, stream=False)
            if isinstance(resp, str):
                return resp
            return _visible_reply_text(resp.json()["choices"][0]["message"]["content"])
        except Exception:
            return "Systems online."

    # ── 2. Check for save memory triggers ──
    save_payload = _extract_save_payload(user_text)
    if save_payload:
        memory_vault.save_memory(f"User explicitly asked to remember: {save_payload}")
        return "I've saved that to my memory, Sir."

    # ── 3. Quick Keyword-based Handler Bypass ──
    # Try ALL matching handlers in priority order until one returns a response.
    # This prevents a loose match (returning None) from blocking stronger later matches.
    user_lower = user_text.lower()
    if _handler_active.is_set():
        return _call_groq_streaming(user_text)

    for keyword, handler in web_tool_keywords:
        is_match = False
        try:
            if ' ' in keyword or "'" in keyword:
                is_match = keyword in user_lower
            else:
                pattern = r'\b' + re.escape(keyword) + r'\b'
                is_match = bool(re.search(pattern, user_lower))
        except re.error:
            is_match = keyword in user_lower

        if not is_match:
            continue

        _handler_active.set()
        try:
            result = handler(user_text)
            if result is not None and str(result).strip():
                print(f"[Zara] Handler success ({keyword}): {str(result)[:80]}...")
                return result
            # None/empty means "not my intent" — continue to lower-priority matches.
        except Exception as e:
            print(f"[Zara] Handler error ({keyword}): {e}")
            # Fail fast on local handler errors instead of stalling on remote fallback.
            return "I hit an internal action error. Try that command again, Sir."
        finally:
            _handler_active.clear()

    return _call_groq_streaming(user_text)


def _call_groq_streaming(user_text: str) -> str:
    """Full streaming Groq implementation."""
    # Before generating response, check if the task is complex
    if len(user_text.split()) > 15 or "plan" in user_text.lower():
        from agent_orchestrator import get_orchestrator
        orch = get_orchestrator()
        # Start a general-purpose team
        workflow = orch.create_coding_team(user_text) # Generalist logic
        return orch.execute_workflow(workflow)

    try:
        relevant_memories = memory_vault.retrieve_memory(user_text)
    except Exception:
        relevant_memories = []

    messages = _build_messages(user_text, relevant_memories)

    if not GROQ_API_KEY:
        try:
            from smart_router import get_router
            router = get_router()
            response, _ = router.route(user_text, get_dynamic_system_prompt(), allow_cache=True)
            return response
        except Exception:
            return "I'm having trouble connecting. Check your internet or API keys."

    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "stream": True,
        "temperature": 0.7,
        "max_tokens": 1024,
    }

    try:
        resp = _post_groq(payload, stream=True)
        if isinstance(resp, str):
            # Fallback to local router if Groq returns an error string
            print(f"[Zara Core] Groq error: {resp}. Falling back to SmartRouter.")
            from smart_router import get_router
            response, _ = get_router().route(user_text, get_dynamic_system_prompt(), allow_cache=True)
            return response
    except Exception as e:
        print(f"[Zara Core] Groq stream initiation failed: {e}. Falling back to SmartRouter.")
        from smart_router import get_router
        response, _ = get_router().route(user_text, get_dynamic_system_prompt(), allow_cache=True)
        return response

    import json as _json
    import local_voice
    import main

    reply_accum = ""
    sentence_buffer = ""
    word_count = 0
    visible_length = 0
    in_execute_block = False
    action_block = ""

    if hasattr(main, "ui") and main.ui:
        main.ui.set_state("TALKING")

    def _flush_buffer(force: bool = False) -> None:
        nonlocal sentence_buffer, word_count
        phrase = sentence_buffer.strip()
        if not phrase:
            return
        if force:
            if phrase:
                local_voice.speak(phrase)
                sentence_buffer = ""
                word_count = 0
            return
        import re
        sentence_pattern = re.compile(r'^([^.!?:]*[.!?:])(?:\s|$)', re.DOTALL)
        match = sentence_pattern.match(phrase)
        if match:
            full_sentence = match.group(1).strip()
            if len(full_sentence.split()) >= 2:
                local_voice.speak(full_sentence)
                sentence_buffer = phrase[match.end():].lstrip()
                word_count = len(sentence_buffer.split()) if sentence_buffer else 0
                return
        if word_count >= 25:
            local_voice.speak(phrase)
            sentence_buffer = ""
            word_count = 0

    import re
    try:
        for line in resp.iter_lines():
            if not line:
                continue
            line_str = line.decode("utf-8")
            if line_str.startswith("data: "):
                line_str = line_str[6:]
            if line_str.strip() == "[DONE]":
                break
            try:
                chunk_data = _json.loads(line_str)
                chunk = chunk_data.get("choices", [{}])[0].get("delta", {}).get("content", "")
            except Exception:
                continue
            if not chunk:
                continue

            reply_accum += chunk

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
                                print(f"[Zara Action Err]: {e}")
                continue

            visible_reply = _visible_reply_text(reply_accum)

            if hasattr(main, "ui") and main.ui:
                main.ui.set_subtitle_text(visible_reply)

            if len(visible_reply) < visible_length:
                visible_length = len(visible_reply)

            visible_delta = visible_reply[visible_length:]
            visible_length = len(visible_reply)

            sentence_buffer += visible_delta
            word_count = len(sentence_buffer.split())
            _flush_buffer()
    except Exception as e:
        print(f"[Zara Core] Groq stream interrupted: {e}. Attempting failover synthesis.")
        if not reply_accum.strip():
            from smart_router import get_router
            response, _ = get_router().route(user_text, get_dynamic_system_prompt(), allow_cache=True)
            return response

    _flush_buffer(force=True)

    reply = _visible_reply_text(reply_accum).strip()
    if not reply:
        reply = "All set."

    try:
        memory_vault.store_memory(f"User: {user_text}")
        memory_vault.store_memory(f"Zara: {reply}")
    except Exception as e:
        print(f"[Zara Core] failed to save to vault: {e}")

    return reply



# ==================== EXTRACTED HANDLERS & KEYWORDS ====================

def _handle_send_message(text: str) -> Optional[str]:
    """Handle send message commands with confirmation flow"""
    try:
        import local_voice
        from messaging_agent import get_messaging_agent
        
        agent = get_messaging_agent(speak_callback=local_voice.speak)
        
        if agent.has_pending_confirmation():
            result = agent.handle_confirmation(text)
            if result:
                return result
        
        request = agent.parse_message_command(text)
        if request:
            agent.initiate_send(request)
            return "I drafted the message and queued confirmation, Sir."
        
    except Exception as e:
        print(f"[Messaging Handler] Error: {e}")
    return None

def _handle_play_music(text: str) -> Optional[str]:
    """Parse natural language to play music on Spotify."""
    import json
    import action_engine

    text_lower = text.lower()
    app = "spotify"
    query = text_lower

    command_patterns = [
        r'\bplay\b', r'\bput on\b', r'\blisten to\b',
        r'\bi want to hear\b', r'\bcan you play\b',
        r'\bsome\b(?=\s+music\b)', r'\bon spotify\b',
        r'\bon youtube\b', r'\bon apple music\b',
        r'\bi want you to\b', r'\bopen spotify\b', r'\bopen\b',
        r'\bme\b', r'\bany\b', r'\bsong\b',
    ]
    for pattern in command_patterns:
        query = re.sub(pattern, '', query, flags=re.IGNORECASE)
    query = re.sub(r'\s+', ' ', query).strip().strip(',').strip()
    query = re.sub(r'^(here|please|zara|sir|ma[\'’]?am)\b[,\s]*', '', query, flags=re.IGNORECASE)
    query = re.sub(r'^(and|then)\s+', '', query, flags=re.IGNORECASE)
    query = re.sub(r'[.!?,;:]+$', '', query).strip()

    # Try to parse "Song by Artist"
    song_name = ""
    artist_name = ""

    if query.lower().startswith("from "):
        artist_name = query[5:].strip()
    elif " by " in query:
        parts = query.split(" by ", 1)
        song_name = parts[0].strip()
        artist_name = parts[1].strip()
    elif " from " in query:
        parts = query.split(" from ", 1)
        song_name = parts[0].strip()
        artist_name = parts[1].strip()

    if song_name.lower() in {"and", "any", "some", "a", "the"}:
        song_name = ""

    # Prefer artist query when user asks "song from X".
    if artist_name and not song_name:
        query = artist_name

    # Pattern 4: generic requests ("some music", "any song", etc.)
    generic_music_queries = {
        "music", "some music", "something", "any music", "any song",
        "song", "a song", "play something", "something nice", "and music"
    }
    if not query or query.lower() in generic_music_queries:
        # Play user's recent favorites or discover weekly
        query = ""  # Empty = play whatever's recommended
        print("[Zara] Playing recommended music")

    # ── CLEAN QUERY ──────────────────────────────────────────
    if query:
        # Fix common misspellings
        corrections = {
            "stoneboy": "Stonebwoy",
            "chris brown": "Chris Brown",
            "burna": "Burna Boy",
        }
        for wrong, correct in corrections.items():
            if wrong in query.lower():
                query = re.sub(wrong, correct, query, flags=re.IGNORECASE)

    print(f"[Zara] Final query: '{query}'")

    # ── REMEMBER FOR FUTURE ──────────────────────────────────
    prefs = get_prefs()
    # Only log meaningful entries
    if song_name and len(song_name) > 2 and song_name not in ["music", "song", "some music"]:
        prefs.add_recent_song(song_name, artist_name)
    elif artist_name and len(artist_name) > 2:
        prefs.add_recent_song("", artist_name)
    elif query and len(query) > 2 and query not in ["music", "song", "some music"]:
        # If we only have a cleaned query string
        prefs.add_recent_song(query, "")

    # ── EXECUTE ──────────────────────────────────────────────
    try:
        executor = action_engine.ActionExecutor()
        payload = json.dumps({
            "action": "start_app",
            "app_name": app,
            "query": query,
            "music_action": "play_artist" if query else "play_recommended"
        })
        executor.execute_payload(payload)

        # Return appropriate response
        if song_name and artist_name:
            return f"Playing {song_name} by {artist_name}, Sir."
        elif query:
            return f"Playing {query}, Sir."
        else:
            return "Playing music, Sir."

    except Exception as e:
        print(f"[Zara] Handler exception: {e}")
        import traceback
        traceback.print_exc()
        return f"I had trouble playing music, Sir."

def _handle_vision_command(text: str) -> Optional[str]:
    """Handle vision-related commands."""
    from zara_eyes import get_eyes
    import local_voice
    
    eyes = get_eyes()
    text_lower = text.lower()
    
    if "what do you see" in text_lower or "what's on my screen" in text_lower:
        print("[Zara] Forcing fresh screen analysis...")
        
        # Force a fresh look
        context = eyes.look_at()
        
        if context and context.raw_description:
            response = f"I see {context.active_window}. {context.raw_description}"
            print(f"[Zara] Vision response: {response}")
            
            # SPEAK IT IMMEDIATELY
            import threading
            def speak_it():
                local_voice.speak(response)
            threading.Thread(target=speak_it, daemon=True).start()
            
            return response
        else:
            # Fallback
            try:
                import pyautogui
                import win32gui
                window_title = win32gui.GetWindowText(win32gui.GetForegroundWindow())
                response = f"I see the {window_title} window on your screen, Sir."
                local_voice.speak(response)
                return response
            except:
                response = "I'm looking at your screen, Sir. Everything appears normal."
                local_voice.speak(response)
                return response
    
    elif "what window" in text_lower or "what app" in text_lower:
        window = eyes.get_active_window()
        response = f"You're currently in {window}, Sir."
        import threading
        threading.Thread(target=lambda: local_voice.speak(response), daemon=True).start()
        return response

    elif "navigate to" in text_lower or "go to" in text_lower:
        import re
        import zara_vision
        vision = zara_vision.get_vision()
        match = re.search(r'(?:navigate to|go to)\s+(.+)', text_lower)
        if match:
            destination = match.group(1).strip()
            if vision.navigate_to(destination):
                return f"Navigated to {destination}, Sir."
            else:
                return f"I couldn't navigate to {destination}."

    # ── QUESTION ANSWERING ────────────────────────────
    elif any(word in text_lower for word in ["what color", "how many", "where is", "which button"]):
        import zara_vision
        vision = zara_vision.get_vision()
        return vision.answer_question(text)

    # ── UI ANALYSIS ───────────────────────────────────
    elif "analyze the screen" in text_lower or "what can i do here" in text_lower:
        import zara_vision
        vision = zara_vision.get_vision()
        result = vision.analyze_ui()
        response = f"{result.description}\n\n"
        if result.suggested_actions:
            response += "Suggested actions:\n• " + \
                "\n• ".join(result.suggested_actions[:5])
        return response
    # ── WAIT FOR SOMETHING ───────────────────────────
    elif "tell me when" in text_lower or "let me know when" in text_lower:
        import re
        import zara_vision
        vision = zara_vision.get_vision()
        match = re.search(
            r'(?:tell me when|let me know when)\s+(.+)', text_lower)
        if match:
            element = match.group(1).strip().replace(
                " appears", "").replace(" shows up", "")

            def monitor_and_notify():
                if vision.wait_for_element(element, timeout=60):
                    import local_voice
                    local_voice.speak(
                        f"Sir, {element} has appeared on the screen.")
                else:
                    import local_voice
                    local_voice.speak(
                        f"Sir, {element} did not appear within the time limit.")

            import threading
            threading.Thread(target=monitor_and_notify,
                             daemon=True).start()
            return f"I'm keeping an eye out for {element}, Sir."

    return "I'm looking, Sir."

def _handle_window_command(text: str) -> Optional[str]:
    """Handle window management commands."""
    from zara_window_manager import get_window_manager
    
    wm = get_window_manager()
    text_lower = text.lower()
    
    # ── FOCUS / SWITCH ──────────────────────────────────────
    if "switch to" in text_lower or "focus" in text_lower or "go to" in text_lower:
        import re
        match = re.search(r'(?:switch to|focus|go to)\s+(.+)', text_lower)
        if match:
            app = match.group(1).strip()
            if wm.focus_window(title_contains=app) or wm.focus_window(process_contains=app):
                return f"Switched to {app}, Sir."
            return f"I couldn't find {app}, Sir."
    
    # ── MINIMIZE ────────────────────────────────────────────
    elif "minimize" in text_lower:
        if "all" in text_lower or "everything" in text_lower:
            wm.minimize_all()
            return "All windows minimized, Sir."
        else:
            import re
            match = re.search(r'minimize\s+(.+)', text_lower)
            if match:
                app = match.group(1).strip()
                if wm.minimize_window(title_contains=app):
                    return f"Minimized {app}, Sir."
            else:
                # Minimize current window
                wm.minimize_window()
                return "Window minimized, Sir."
    
    # ── MAXIMIZE ────────────────────────────────────────────
    elif "maximize" in text_lower:
        import re
        match = re.search(r'maximize\s+(.+)', text_lower)
        if match:
            app = match.group(1).strip()
            if wm.maximize_window(title_contains=app):
                return f"Maximized {app}, Sir."
        else:
            wm.maximize_window()
            return "Window maximized, Sir."
    
    # ── CLOSE ───────────────────────────────────────────────
    elif "close" in text_lower and "window" in text_lower:
        import re
        match = re.search(r'close\s+(.+?)(?:\s+window|\s*$)', text_lower)
        if match:
            app = match.group(1).strip()
            if wm.close_window(title_contains=app):
                return f"Closed {app}, Sir."
        else:
            wm.close_window()
            return "Window closed, Sir."
    
    # ── SNAP ────────────────────────────────────────────────
    elif "snap" in text_lower:
        if "left" in text_lower:
            wm.snap_left()
            return "Window snapped to left, Sir."
        elif "right" in text_lower:
            wm.snap_right()
            return "Window snapped to right, Sir."
        elif "top" in text_lower or "maximize" in text_lower:
            wm.snap_top()
            return "Window maximized, Sir."
    
    # ── ARRANGE ─────────────────────────────────────────────
    elif "arrange" in text_lower or "tile" in text_lower:
        if "side by side" in text_lower:
            # Try to arrange current and previous window
            return "Which two windows would you like to arrange, Sir?"
        elif "grid" in text_lower:
            return "Tell me which windows to arrange, Sir."
    
    # ── MOVE ────────────────────────────────────────────────
    elif "move" in text_lower and "window" in text_lower:
        import re
        import pyautogui
        # Move to specific position: "move window to top left"
        if "top" in text_lower and "left" in text_lower:
            wm.move_window(None, 0, 0)
            return "Window moved to top left, Sir."
        elif "top" in text_lower and "right" in text_lower:
            screen_width = pyautogui.size()[0]
            wm.move_window(None, screen_width // 2, 0)
            return "Window moved to top right, Sir."
        elif "center" in text_lower:
            screen_width = pyautogui.size()[0]
            screen_height = pyautogui.size()[1]
            wm.move_window(None, screen_width // 4, screen_height // 4)
            return "Window centered, Sir."
    
    # ── LIST WINDOWS ────────────────────────────────────────
    elif "what windows" in text_lower or "list windows" in text_lower or "open windows" in text_lower:
        return wm.list_windows()
    
    # ── SHOW DESKTOP ────────────────────────────────────────
    elif "show desktop" in text_lower:
        wm.minimize_all()
        return "Desktop shown, Sir."
    
    elif "restore windows" in text_lower or "show windows" in text_lower:
        wm.restore_all()
        return "Windows restored, Sir."
    
    return None

# Check if this should use free web tools first
# Order: Specific phrases first to avoid shadowing (Issue A)

web_tool_keywords = [
        ("send a message", lambda txt: _handle_send_message(txt)),
        ("send message", lambda txt: _handle_send_message(txt)),
        ("text someone", lambda txt: _handle_send_message(txt)),
        ("message someone", lambda txt: _handle_send_message(txt)),
        ("dm ", lambda txt: _handle_send_message(txt)),
        ("send a dm", lambda txt: _handle_send_message(txt)),
    # Vision Commands
    ("what do you see", lambda txt: _handle_vision_command(txt)),
    ("what's on my screen", lambda txt: _handle_vision_command(txt)),
    ("is there an error", lambda txt: _handle_vision_command(txt)),
    ("analyze the screen", lambda txt: _handle_vision_command(txt)),
    ("analyze this", lambda txt: _handle_vision_command(txt)),
    ("look at", lambda txt: _handle_vision_command(txt)),
    ("read this", lambda txt: _handle_vision_command(txt)),
    ("read the", lambda txt: _handle_vision_command(txt)),
    ("what window", lambda txt: _handle_vision_command(txt)),

    # Web Interaction (Specific first)
    ("search the web", lambda txt: _handle_web_search_direct(txt)),
    ("look up on google", lambda txt: _handle_web_search_direct(txt)),
    ("search for", lambda txt: _handle_web_search_direct(txt)),
    ("google", lambda txt: _handle_web_search_direct(txt)),
    ("open website", lambda txt: _handle_browse_website(txt)),
    ("navigate to", lambda txt: _handle_browse_website(txt)),
    ("go to", lambda txt: _handle_browse_website(txt)),
    ("visit", lambda txt: _handle_browse_website(txt)),
    ("browse", lambda txt: _handle_browse_website(txt)),
    ("submit form", lambda txt: _handle_fill_form(txt)),
    ("fill form", lambda txt: _handle_fill_form(txt)),

    # Space & Science
    ("astronomy picture", lambda txt: _handle_nasa_apod()),
    ("nasa picture", lambda txt: _handle_nasa_apod()),
    ("space picture", lambda txt: _handle_nasa_apod()),
    ("nasa", lambda txt: _handle_nasa_apod()),
    ("rocket launch", lambda txt: _handle_spacex_launch()),
    ("next launch", lambda txt: _handle_spacex_launch()),
    ("spacex", lambda txt: _handle_spacex_launch()),
    ("space station", lambda txt: _handle_iss_location()),
    ("iss", lambda txt: _handle_iss_location()),
    ("astronomy", lambda txt: _handle_astronomy(txt)),
    ("sunrise", lambda txt: _handle_astronomy(txt)),
    ("sunset", lambda txt: _handle_astronomy(txt)),
    ("moon", lambda txt: _handle_astronomy(txt)),

    # Knowledge & Research
    ("meaning of", lambda txt: _handle_definition(txt)),
    ("what does", lambda txt: _handle_definition(txt) if "mean" in txt else None),
    ("definition", lambda txt: _handle_definition(txt)),
    ("define", lambda txt: _handle_definition(txt)),
    ("synonym", lambda txt: _handle_synonyms(txt)),
    ("rhyme", lambda txt: _handle_rhymes(txt)),
    ("weather", lambda txt: _handle_weather(txt)),
    ("temperature", lambda txt: _handle_weather(txt)),
    ("forecast", lambda txt: _handle_weather(txt)),
    ("tell me about", lambda txt: _handle_search(txt)),
    ("information on", lambda txt: _handle_search(txt)),
    ("search", lambda txt: _handle_search(txt)),
    ("find", lambda txt: _handle_search(txt)),
    ("look up", lambda txt: _handle_search(txt)),
    ("what is", lambda txt: _handle_search(txt)),
    ("who is", lambda txt: _handle_search(txt)),

    # Entertainment
    ("make me laugh", lambda txt: _handle_joke()),
    ("joke", lambda txt: _handle_joke()),
    ("funny", lambda txt: _handle_joke()),
    ("inspiration", lambda txt: _handle_quote()),
    ("motivation", lambda txt: _handle_quote()),
    ("quote", lambda txt: _handle_quote()),
    ("cat fact", lambda txt: _handle_cat_fact()),
    ("dog fact", lambda txt: _handle_dog_fact()),
    ("fact", lambda txt: _handle_useless_fact()),
    ("what should i do", lambda txt: _handle_bored_activity()),
    ("bored", lambda txt: _handle_bored_activity()),
    ("help me", lambda txt: _handle_advice()),
    ("advice", lambda txt: _handle_advice()),

    # Crypto & Finance
    ("exchange rate", lambda txt: _handle_exchange_rate(txt)),
    ("price of", lambda txt: _handle_crypto(txt) if any(c in txt for c in ["bitcoin", "ethereum", "doge", "crypto"]) else None),
    ("bitcoin", lambda txt: _handle_crypto("bitcoin")),
    ("btc", lambda txt: _handle_crypto("bitcoin")),
    ("ethereum", lambda txt: _handle_crypto("ethereum")),
    ("eth", lambda txt: _handle_crypto("ethereum")),
    ("dogecoin", lambda txt: _handle_crypto("dogecoin")),
    ("doge", lambda txt: _handle_crypto("dogecoin")),
    ("crypto", lambda txt: _handle_crypto(txt)),
    ("convert", lambda txt: _handle_exchange_rate(txt)),
    ("usd to", lambda txt: _handle_exchange_rate(txt)),

    # News & Tech
    ("hacker news", lambda txt: _handle_hacker_news()),
    ("hn", lambda txt: _handle_hacker_news()),
    ("dev.to", lambda txt: _handle_dev_to()),
    ("github", lambda txt: _handle_github(txt)),
    ("npm", lambda txt: _handle_npm(txt)),
    ("pypi", lambda txt: _handle_pypi(txt)),
    ("pip package", lambda txt: _handle_pypi(txt)),
    # System & Memory
    ("calculate", lambda txt: _handle_calculator(txt)),
    ("what is", lambda txt: _handle_calculator(txt) if any(c in txt for c in ["+", "-", "*", "/"]) else _handle_search(txt)),
    ("system status", lambda txt: _handle_system_status(txt)),
    ("cpu usage", lambda txt: _handle_system_status(txt)),
    ("ram usage", lambda txt: _handle_system_status(txt)),
    ("memory usage", lambda txt: _handle_system_status(txt)),
    ("remind me", lambda txt: _handle_reminder(txt)),

    # Utility
    ("what's my ip", lambda txt: _handle_ip_info(txt)),
    ("ip address", lambda txt: _handle_ip_info(txt)),
    ("my ip", lambda txt: _handle_ip_info(txt)),
    ("validate email", lambda txt: _handle_email_validation(txt)),
    ("check email", lambda txt: _handle_email_validation(txt)),
    ("shorten", lambda txt: _handle_shorten_url(txt)),
    ("qr code", lambda txt: _handle_qr_code(txt)),
    ("time in", lambda txt: _handle_timezone(txt)),
    ("what time", lambda txt: _handle_timezone(txt)),
    ("timezone", lambda txt: _handle_timezone(txt)),
    ("public holiday", lambda txt: _handle_holidays(txt)),
    ("holiday", lambda txt: _handle_holidays(txt)),
    ("what can you do", lambda txt: _handle_what_can_you_do()),
    ("capabilities", lambda txt: _handle_what_can_you_do()),
    ("skills", lambda txt: _handle_what_can_you_do()),
    ("what do you know", lambda txt: _handle_what_can_you_do()),
    ("help me understand", lambda txt: _handle_what_can_you_do()),

    # Media Search
    ("movie", lambda txt: _handle_movie_info(txt)),
    ("film", lambda txt: _handle_movie_info(txt)),
    ("book", lambda txt: _handle_book_info(txt)),
    ("novel", lambda txt: _handle_book_info(txt)),
    ("pokemon", lambda txt: _handle_pokemon(txt)),
    ("pokémon", lambda txt: _handle_pokemon(txt)),

    # Food & Recipes
    ("how do i make", lambda txt: _handle_recipe(txt)),
    ("how to make", lambda txt: _handle_recipe(txt)),
    ("how to cook", lambda txt: _handle_recipe(txt)),
    ("how to bake", lambda txt: _handle_recipe(txt)),
    ("recipe", lambda txt: _handle_recipe(txt)),
    ("cook", lambda txt: _handle_recipe(txt)),

    # Music & Media
    ("pause music", lambda txt: _handle_play_music(txt)),
    ("pause song", lambda txt: _handle_play_music(txt)),
    ("next track", lambda txt: _handle_play_music(txt)),
    ("next song", lambda txt: _handle_play_music(txt)),
    ("skip this", lambda txt: _handle_play_music(txt)),
    ("previous song", lambda txt: _handle_play_music(txt)),
    ("play music", lambda txt: _handle_play_music(txt)),
    ("play song", lambda txt: _handle_play_music(txt)),
    ("play some", lambda txt: _handle_play_music(txt)),
    ("put on", lambda txt: _handle_play_music(txt)),
    ("listen to", lambda txt: _handle_play_music(txt)),
    ("spotify", lambda txt: _handle_play_music(txt) if "play" in txt.lower() else _handle_open_app(txt)),
    
    # Contextual music guards
    ("play", lambda txt: _handle_play_music(txt) if any(w in txt.lower() for w in ["music", "song", "spotify", "artist", "album", "track", "by "]) else None),
    ("song", lambda txt: _handle_play_music(txt) if any(w in txt.lower() for w in ["play", "listen", "put on", "this", "next", "previous"]) else None),
    ("music", lambda txt: _handle_play_music(txt) if any(w in txt.lower() for w in ["play", "listen", "put on", "some", "turn up", "turn down"]) else None),

    # Volume control
    ("volume up", lambda txt: _handle_volume("up")),
    ("volume down", lambda txt: _handle_volume("down")),
    ("increase the volume", lambda txt: _handle_volume("up")),
    ("decrease the volume", lambda txt: _handle_volume("down")),
    ("turn it up", lambda txt: _handle_volume("up")),
    ("turn it down", lambda txt: _handle_volume("down")),
    ("mute", lambda txt: _handle_volume("mute")),
    
    # App launching
    ("open spotify", lambda txt: _handle_open_app(txt)),
    ("open chrome", lambda txt: _handle_open_app(txt)),
    ("launch", lambda txt: _handle_open_app(txt)),
    
    # Window management
    ("switch to", lambda txt: _handle_window_command(txt)),
    ("focus", lambda txt: _handle_window_command(txt)),
    ("minimize", lambda txt: _handle_window_command(txt)),
    ("maximize", lambda txt: _handle_window_command(txt)),
    ("close window", lambda txt: _handle_window_command(txt)),
    ("snap", lambda txt: _handle_window_command(txt)),
    ("arrange", lambda txt: _handle_window_command(txt)),
    ("tile", lambda txt: _handle_window_command(txt)),
    ("move window", lambda txt: _handle_window_command(txt)),
    ("list windows", lambda txt: _handle_window_command(txt)),
    ("open windows", lambda txt: _handle_window_command(txt)),
    ("show desktop", lambda txt: _handle_window_command(txt)),
    
    # Catch common artist names for direct music triggers
    ("chris brown", lambda txt: _handle_play_music(txt) if any(w in txt.lower() for w in ["play", "put on", "listen"]) else None),
    ("drake", lambda txt: _handle_play_music(txt) if any(w in txt.lower() for w in ["play", "put on", "listen"]) else None),
    ("stonebwoy", lambda txt: _handle_play_music(txt) if any(w in txt.lower() for w in ["play", "put on", "listen"]) else None),
    ("burna boy", lambda txt: _handle_play_music(txt) if any(w in txt.lower() for w in ["play", "put on", "listen"]) else None),
]



def _handle_volume(command: str) -> Optional[str]:
    """Route volume commands through the silent volume controller."""
    try:
        from volume_controller import get_volume_controller
        vc = get_volume_controller()
        honorific = "Sir"
        try:
            from gender_detector import get_honorific
            honorific = get_honorific()
        except Exception:
            pass

        if command == "up":
            success, new_level = vc.volume_up(0.10)
            return f"Volume up to {int(new_level * 100)}%, {honorific}." if success else f"Couldn't adjust volume, {honorific}."
        elif command == "down":
            success, new_level = vc.volume_down(0.10)
            return f"Volume down to {int(new_level * 100)}%, {honorific}." if success else f"Couldn't adjust volume, {honorific}."
        elif command == "mute":
            success, is_muted = vc.toggle_mute()
            state_str = "Muted" if is_muted else "Unmuted"
            return f"{state_str}, {honorific}."
        else:
            # Try natural language parse
            from volume_controller import handle_volume_command
            return handle_volume_command(command)
    except Exception as e:
        print(f"[Volume Handler] Error: {e}")
        return None


def _handle_weather(query: str) -> Optional[str]:
    """Get weather for a location."""
    try:
        from free_web_tools import get_web_tools
        tools = get_web_tools()
        
        import re
        # Find city after "in" or "for"
        city_match = re.search(r'(?:weather|forecast|temperature)\s+(?:in|for|at)\s+([A-Za-z\s]+?)(?:\?|$)', query, re.I)
        city = city_match.group(1).strip() if city_match else query.split()[-1].rstrip("?.!")
        
        return tools.get_weather(city)
    except Exception as e:
        print(f"[Zara Weather Handler] Error: {e}")
        return None


def _handle_joke() -> str:
    """Get a random joke."""
    try:
        from free_web_tools import get_web_tools
        tools = get_web_tools()
        return tools.get_random_joke()
    except:
        return "Why did the AI cross the road? To debug the other side! 😄"


def _handle_quote() -> str:
    """Get a random quote."""
    try:
        from free_web_tools import get_web_tools
        tools = get_web_tools()
        return tools.get_random_quote()
    except:
        return "💬 \"The only limit to our realization of tomorrow is our doubts of today.\" — Franklin D. Roosevelt"


def _handle_chuck_norris() -> str:
    """Get a Chuck Norris joke."""
    try:
        from free_web_tools import get_web_tools
        tools = get_web_tools()
        return tools.get_chuck_norris_joke()
    except:
        return "💪 Chuck Norris doesn't need an API."


def _handle_definition(query: str) -> Optional[str]:
    """Get definition of a word."""
    try:
        from free_web_tools import get_web_tools
        tools = get_web_tools()
        import re
        # Remove command words and take the remaining phrase
        cleaned = re.sub(
            r'\b(define|definition|meaning of|what does|mean)\b', '',
            query, flags=re.IGNORECASE
        ).strip().rstrip("?.")
        word = cleaned if cleaned else query.split()[-1]
        return tools.get_word_definition(word)
    except Exception as e:
        print(f"[Zara Definition Handler] Error: {e}")
        return None


def _handle_synonyms(query: str) -> Optional[str]:
    """Get synonyms for a word."""
    try:
        from free_web_tools import get_web_tools
        tools = get_web_tools()
        words = query.split()
        word = words[-1] if words else "happy"
        return tools.get_synonyms(word)
    except:
        return None


def _handle_rhymes(query: str) -> Optional[str]:
    """Get rhyming words."""
    try:
        from free_web_tools import get_web_tools
        tools = get_web_tools()
        words = query.split()
        word = words[-1] if words else "day"
        return tools.get_rhymes(word)
    except:
        return None


def _handle_search(query: str) -> Optional[str]:
    """Clean search query and research."""
    try:
        # Aggressive cleaning
        command_phrases = ["search for", "find info on", "tell me about", "google", "look up", "search", "find", "who is", "what is"]
        cleaned = query.lower()
        for phrase in command_phrases:
            if cleaned.startswith(phrase):
                cleaned = cleaned[len(phrase):].strip()
        
        # Clean extra spaces/punctuation only if needed
        import re
        cleaned = re.sub(r'[^\w\s]', ' ', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        # Extract likely topic (words after "for" or "about")
        if not cleaned or len(cleaned) < 3:
            words = query.split()
            for i, word in enumerate(words):
                if word.lower() in ["for", "about", "on"]:
                    cleaned = " ".join(words[i+1:])
                    break

        # Remove any remaining non-ASCII
        cleaned = ''.join(c for c in cleaned if ord(c) < 128).strip()

        print(f"[Zara] Search: '{query[:50]}...' -> '{cleaned}'")

        if not cleaned or len(cleaned) < 2:
            return "I didn't catch what you want me to search for. Could you repeat that?"

        from free_web_tools import get_web_tools
        tools = get_web_tools()
        return tools.research(cleaned)
    except Exception as e:
        print(f"[Zara Search] Error: {e}")
        return None


def _handle_browse_website(text: str) -> Optional[str]:
    """Handle natural language web browsing requests."""
    import re
    import json
    import action_engine

    url_match = re.search(
        r'(?:go to|open|browse|visit|navigate to)\s+([a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?)', text)
    url_match = url_match or re.search(r'(https?://[^\s]+)', text)

    if url_match:
        url = url_match.group(1)
        if not url.startswith("http"):
            url = "https://" + url

        executor = action_engine.ActionExecutor()
        payload = json.dumps({"action": "browse_web", "url": url})
        executor.execute_payload(payload)

        return f"Opening {url} in my browser. What should I look for?"

    search_match = re.search(
        r'(?:search|find|look for)\s+(.+?)(?:\s+on\s+|\s+in\s+|$)', text)
    if search_match:
        query = search_match.group(1).strip()
        executor = action_engine.ActionExecutor()
        payload = json.dumps({"action": "browse_web", "task": query})
        executor.execute_payload(payload)

        return f"Searching for {query}. One moment."

    return None


def _handle_fill_form(text: str) -> Optional[str]:
    """Handle form filling requests."""
    import json
    import action_engine

    executor = action_engine.ActionExecutor()
    payload = json.dumps({"action": "fill_form", "fields": {}})
    executor.execute_payload(payload)
    return "Filling the form."


def _generate_llm_response(user_text: str) -> str:
    """Direct LLM response without handler routing."""
    try:
        relevant_memories = memory_vault.retrieve_memory(user_text)
    except:
        relevant_memories = []

    messages = _build_messages(user_text, relevant_memories)

    if not GROQ_API_KEY:
        try:
            from smart_router import get_router
            router = get_router()
            response, _ = router.route(
                user_text, get_dynamic_system_prompt(), allow_cache=True)
            return response
        except:
            return "I'm having trouble connecting. Check your internet."

    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "stream": False,
        "temperature": 0.7,
        "max_tokens": 300,
    }

    resp = _post_groq(payload, stream=False)
    if isinstance(resp, str):
        return resp

    try:
        data = resp.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "I'm not sure how to respond.")
    except:
        return "I'm having trouble processing that. Could you rephrase?"


def _handle_cat_fact() -> str:
    """Get a random cat fact."""
    try:
        from free_web_tools import get_web_tools
        return get_web_tools().get_cat_fact()
    except:
        return "🐱 Cats spend 70% of their lives sleeping."


def _handle_dog_fact() -> str:
    """Get a random dog fact."""
    try:
        from free_web_tools import get_web_tools
        return get_web_tools().get_dog_fact()
    except:
        return "🐕 Dogs can understand up to 250 words."


def _handle_useless_fact() -> str:
    """Get a random useless fact."""
    try:
        from free_web_tools import get_web_tools
        return get_web_tools().get_useless_fact()
    except:
        return "🤔 A group of porcupines is called a prickle."


def _handle_advice() -> str:
    """Get random advice."""
    try:
        from free_web_tools import get_web_tools
        return get_web_tools().get_advice()
    except:
        return "💡 Take care of yourself."


def _handle_bored_activity() -> str:
    """Get a random activity suggestion."""
    try:
        from free_web_tools import get_web_tools
        return get_web_tools().get_bored_activity()
    except:
        return "🎯 Try learning something new!"


def _handle_number_fact(query: str) -> str:
    """Get a fact about a number."""
    try:
        from free_web_tools import get_web_tools
        numbers = re.findall(r'\d+', query)
        number = int(numbers[0]) if numbers else None
        return get_web_tools().get_number_fact(number)
    except:
        return "🔢 42 is the answer to life, the universe, and everything."


def _handle_date_fact() -> str:
    """Get a fact about today's date."""
    try:
        from free_web_tools import get_web_tools
        return get_web_tools().get_date_fact()
    except:
        return "📅 On this day in history, something happened."


def _handle_hacker_news() -> Optional[str]:
    """Get top Hacker News stories."""
    try:
        from free_web_tools import get_web_tools
        return get_web_tools().get_hacker_news_top(5)
    except:
        return None


def _handle_dev_to() -> Optional[str]:
    """Get top Dev.to articles."""
    try:
        from free_web_tools import get_web_tools
        return get_web_tools().get_dev_to_top(5)
    except:
        return None


def _handle_github(query: str) -> Optional[str]:
    """Get GitHub user info."""
    try:
        from free_web_tools import get_web_tools
        tools = get_web_tools()
        username = query.split()[-1] if len(query.split()) > 1 else "torvalds"
        return tools.get_github_user(username)
    except:
        return None


def _handle_npm(query: str) -> Optional[str]:
    """Get NPM package info."""
    try:
        from free_web_tools import get_web_tools
        tools = get_web_tools()
        package = query.split()[-1] if len(query.split()) > 1 else "react"
        return tools.get_npm_package(package)
    except:
        return None


def _handle_calculator(query: str) -> Optional[str]:
    """Safe evaluation of math expressions."""
    import re
    math_expr = query.lower().replace('what is', '').replace('calculate', '').strip()
    math_expr = re.sub(r'[a-z]+', '', math_expr)
    if not re.match(r'^[\d+\-*/().^ ]+$', math_expr) or not math_expr.strip():
        return None
    try:
        math_expr = math_expr.replace('^', '**')
        result = eval(math_expr, {"__builtins__": None}, {})
        # Format nice float if needed
        if isinstance(result, float) and result.is_integer():
            result = int(result)
        return f"The result is {result}."
    except:
        return None


def _handle_system_status(query: str = "") -> Optional[str]:
    """Get CPU, RAM info."""
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.2)
        ram = psutil.virtual_memory().percent
        return f"System Status: CPU is at {cpu} percent, and Memory is at {ram} percent, Sir."
    except Exception as e:
        print(f"[Zara] psutil error: {e}")
        return "I cannot access system hardware metrics at the moment, Sir."


def _handle_reminder(text: str) -> Optional[str]:
    """Basic reminder using threading timer."""
    import re
    import threading
    import local_voice
    
    match = re.search(r'remind me to (.+?) in (\d+)\s*(second|minute|hour)s?', text.lower())
    if match:
        task = match.group(1).strip()
        amount = int(match.group(2))
        unit = match.group(3)
        
        multiplier = 1
        if unit == 'minute': multiplier = 60
        elif unit == 'hour': multiplier = 3600
        
        delay = amount * multiplier
        
        def reminder_callback():
            local_voice.speak(f"Sir, here is your reminder to {task}.")
            
        threading.Timer(delay, reminder_callback).start()
        return f"I have set a reminder to {task} in {amount} {unit}{'s' if amount > 1 else ''}, Sir."
    return None


def _handle_pypi(query: str) -> Optional[str]:
    """Get PyPI package info."""
    try:
        from free_web_tools import get_web_tools
        tools = get_web_tools()
        package = query.split()[-1] if len(query.split()) > 1 else "numpy"
        return tools.get_pypi_package(package)
    except:
        return None


def _handle_http_status(query: str) -> Optional[str]:
    """Get HTTP status code description."""
    try:
        from free_web_tools import get_web_tools
        numbers = re.findall(r'\b([1-5]\d{2})\b', query)
        if numbers:
            return get_web_tools().get_http_status(int(numbers[0]))
    except:
        pass
    return None


def _handle_cve(query: str) -> Optional[str]:
    """Get CVE vulnerability info."""
    try:
        from free_web_tools import get_web_tools
        cve_match = re.search(r'(CVE-\d{4}-\d{4,})', query, re.IGNORECASE)
        if cve_match:
            return get_web_tools().get_cve_info(cve_match.group(1))
    except:
        pass
    return None


def _handle_crypto(query: str) -> Optional[str]:
    """Get cryptocurrency price."""
    try:
        from free_web_tools import get_web_tools
        tools = get_web_tools()
        coin_map = {
            "bitcoin": "bitcoin", "btc": "bitcoin",
            "ethereum": "ethereum", "eth": "ethereum",
            "dogecoin": "dogecoin", "doge": "dogecoin",
            "solana": "solana", "sol": "solana",
            "cardano": "cardano", "ada": "cardano",
            "ripple": "ripple", "polkadot": "polkadot",
        }
        q = query.lower()
        coin_name = next((v for k, v in coin_map.items() if k in q), None)
        if not coin_name:
            # Generic "crypto" query — return top 3
            results = []
            for coin in ["bitcoin", "ethereum", "solana"]:
                r = tools.get_crypto_price(coin)
                if r:
                    results.append(r)
            return "\n\n".join(results) if results else None
        return tools.get_crypto_price(coin_name)
    except Exception:
        return None


def _handle_exchange_rate(query: str) -> Optional[str]:
    """Get exchange rate."""
    try:
        from free_web_tools import get_web_tools
        tools = get_web_tools()
        currencies = re.findall(r'\b([A-Z]{3})\b', query.upper())
        if len(currencies) >= 2:
            return tools.get_exchange_rate(currencies[0], currencies[1])
        elif len(currencies) == 1:
            return tools.get_exchange_rate(currencies[0], "EUR")
    except:
        pass
    return None


def _handle_country_info(query: str) -> Optional[str]:
    """Get country information."""
    try:
        from free_web_tools import get_web_tools
        tools = get_web_tools()
        country = query.replace("country", "").replace("info", "").strip()
        if country:
            return tools.get_country_info(country)
    except:
        pass
    return None


def _handle_university_info(query: str) -> Optional[str]:
    """Search for universities."""
    try:
        from free_web_tools import get_web_tools
        tools = get_web_tools()
        name = query.replace("university", "").replace("uni", "").strip()
        if name:
            return tools.get_university_info(name)
    except:
        pass
    return None


def _handle_holidays(query: str) -> Optional[str]:
    """Get public holidays."""
    try:
        from free_web_tools import get_web_tools
        tools = get_web_tools()
        import re
        code_match = re.search(r'\b([A-Z]{2})\b', query.upper())
        country = code_match.group(1) if code_match else "US"
        return tools.get_public_holidays(country)
    except:
        return None


def _handle_qr_code(query: str) -> Optional[str]:
    """Generate QR code URL."""
    try:
        from free_web_tools import get_web_tools
        tools = get_web_tools()
        import re
        text_match = re.search(
            r'(?:for|of)\s+["\']?([^"\']+)["\']?', query, re.IGNORECASE)
        content = text_match.group(1) if text_match else query.replace(
            "qr", "").replace("code", "").strip() or "Zara"
        url = tools.get_qr_code(content)
        return f"🎯 QR Code generated: {url}"
    except:
        return None


def _handle_shorten_url(query: str) -> Optional[str]:
    """Shorten a URL."""
    try:
        from free_web_tools import get_web_tools
        tools = get_web_tools()
        url_match = re.search(r'https?://[^\s]+', query)
        if url_match:
            url = url_match.group(0)
            shortened = tools.shorten_url(url)
            if shortened:
                return f"🔗 Shortened: {shortened}"
    except:
        pass
    return None


def _handle_email_validation(query: str) -> Optional[str]:
    """Validate an email address."""
    try:
        from free_web_tools import get_web_tools
        tools = get_web_tools()
        email_match = re.search(
            r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', query)
        if email_match:
            email = email_match.group(0)
            return tools.validate_email(email)
    except:
        pass
    return None


def _handle_ip_info(query: str = "") -> Optional[str]:
    """Get IP address information."""
    try:
        from free_web_tools import get_web_tools
        tools = get_web_tools()
        ip_match = re.search(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b', query)
        ip = ip_match.group(0) if ip_match else ""
        return tools.get_ip_info(ip)
    except:
        pass
    return None


def _handle_timezone(query: str) -> Optional[str]:
    """Get current time in a timezone."""
    city_tz_map = {
        "tokyo": "Asia/Tokyo", "london": "Europe/London", "new york": "America/New_York",
        "los angeles": "America/Los_Angeles", "paris": "Europe/Paris",
        "sydney": "Australia/Sydney", "dubai": "Asia/Dubai", "berlin": "Europe/Berlin",
        "chicago": "America/Chicago", "beijing": "Asia/Shanghai",
        "moscow": "Europe/Moscow", "toronto": "America/Toronto",
        "singapore": "Asia/Singapore", "hong kong": "Asia/Hong_Kong",
        "accra": "Africa/Accra", "lagos": "Africa/Lagos", "nairobi": "Africa/Nairobi",
        "cairo": "Africa/Cairo", "johannesburg": "Africa/Johannesburg",
    }
    query_lower = query.lower()
    timezone = None
    for city, tz in city_tz_map.items():
        if city in query_lower:
            timezone = tz
            break
    if not timezone:
        import re
        tz_match = re.search(r'([A-Za-z]+/[A-Za-z_]+)', query)
        if tz_match:
            timezone = tz_match.group(1)
    if not timezone:
        return None
    from free_web_tools import get_web_tools
    return get_web_tools().get_timezone_time(timezone)


def _handle_open_app(text: str) -> Optional[str]:
    """Handle simple app opening commands."""
    import json
    import action_engine

    text_lower = text.lower()

    app_map = {
        "spotify": "spotify",
        "chrome": "chrome",
        "vs code": "code",
        "vscode": "code",
        "notepad": "notepad",
        "calculator": "calc",
        "settings": "ms-settings:",
        "discord": "discord",
        "file explorer": "explorer",
    }

    for keyword, app in app_map.items():
        if keyword in text_lower and ("open" in text_lower or "launch" in text_lower):
            executor = action_engine.ActionExecutor()
            payload = json.dumps({"action": "start_app", "app_name": app})
            executor.execute_payload(payload)
            return f"Opening {keyword.title()}, Sir."

    return None


# ==================== NEW MEDIA & SCIENCE HANDLERS ====================

def _handle_movie_info(text: str) -> Optional[str]:
    """Get movie information from TMDB."""
    import re
    movie_match = re.search(
        r'(?:movie|film)\s+["\']?([^"\']+ )["\']?', text, re.IGNORECASE)
    movie_match = movie_match or re.search(
        r'(?:about|for)\s+["\']?([^"\']+ )["\']?(?:\s+movie|\s+film)', text, re.IGNORECASE)

    if movie_match:
        try:
            import requests
            api_key = os.environ.get("TMDB_API_KEY", "")
            if not api_key:
                return "TMDB API key not configured. Get one at https://www.themoviedb.org/settings/api"

            movie_name = movie_match.group(1).strip()
            # Search for movie
            search_resp = requests.get(
                "https://api.themoviedb.org/3/search/movie",
                params={"api_key": api_key, "query": movie_name},
                timeout=10
            )
            if search_resp.status_code == 200:
                results = search_resp.json().get("results", [])
                if results:
                    movie = results[0]
                    title = movie.get("title", movie.get(
                        "original_title", "Unknown"))
                    overview = movie.get("overview", "No overview available.")
                    rating = movie.get("vote_average", "N/A")
                    release = movie.get("release_date", "Unknown")

                    return (
                        f"🎬 {title}\n"
                        f"   📅 Release: {release}\n"
                        f"   ⭐ Rating: {rating}/10\n"
                        f"   📝 {overview[:300]}..."
                    )
            return f"Couldn't find movie '{movie_name}'."
        except Exception as e:
            print(f"[Zara] TMDB error: {e}")
    return None


def _handle_book_info(text: str) -> Optional[str]:
    """Get book information from Open Library."""
    import re
    book_match = re.search(
        r'(?:book|novel)\s+["\']?([^"\']+ )["\']?', text, re.IGNORECASE)
    book_match = book_match or re.search(
        r'(?:about|for)\s+["\']?([^"\']+ )["\']?(?:\s+book)', text, re.IGNORECASE)

    if book_match:
        try:
            import requests
            book_name = book_match.group(1).strip()
            resp = requests.get(
                "https://openlibrary.org/search.json",
                params={"q": book_name, "limit": 1},
                timeout=10
            )
            if resp.status_code == 200:
                docs = resp.json().get("docs", [])
                if docs:
                    book = docs[0]
                    title = book.get("title", "Unknown")
                    author = ", ".join(book.get("author_name", ["Unknown"]))
                    year = book.get("first_publish_year", "Unknown")

                    return (
                        f"📚 {title}\n"
                        f"   ✍️ Author: {author}\n"
                        f"   📅 First published: {year}\n"
                        f"   🔗 https://openlibrary.org{book.get('key', '')}"
                    )
            return f"Couldn't find book '{book_name}'."
        except Exception as e:
            print(f"[Zara] Open Library error: {e}")
    return None


def _handle_nasa_apod() -> Optional[str]:
    """Get NASA Astronomy Picture of the Day."""
    try:
        import requests
        api_key = os.environ.get("NASA_API_KEY", "DEMO_KEY")
        resp = requests.get(
            "https://api.nasa.gov/planetary/apod",
            params={"api_key": api_key},
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            return (
                f"🌌 NASA Astronomy Picture of the Day\n"
                f"   📷 {data.get('title', '')}\n"
                f"   📅 {data.get('date', '')}\n"
                f"   📝 {data.get('explanation', '')[:300]}...\n"
                f"   🖼️ {data.get('url', '')}"
            )
    except Exception as e:
        print(f"[Zara] NASA error: {e}")
    return None


def _handle_iss_location() -> Optional[str]:
    """Get current ISS location."""
    try:
        import requests
        resp = requests.get(
            "http://api.open-notify.org/iss-now.json", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            pos = data.get("iss_position", {})
            lat = pos.get("latitude", "unknown")
            lon = pos.get("longitude", "unknown")

            # Get reverse geocoding
            geo_resp = requests.get(
                f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json",
                headers={"User-Agent": "ZaraAI/1.0"},
                timeout=10
            )
            location = "over the ocean"
            if geo_resp.status_code == 200:
                geo_data = geo_resp.json()
                location = geo_data.get("display_name", "unknown")[:100]

            return (
                f"🛰️ ISS Current Location:\n"
                f"   📍 Latitude: {lat}\n"
                f"   📍 Longitude: {lon}\n"
                f"   🌍 Near: {location}"
            )
    except Exception as e:
        print(f"[Zara] ISS error: {e}")
    return None


def _handle_astronomy(text: str) -> Optional[str]:
    """Get sunrise/sunset times for a location."""
    try:
        from free_web_tools import get_web_tools
        tools = get_web_tools()
        import re
        city_match = re.search(
            r'(?:in|for)\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)', text, re.IGNORECASE)
        city = city_match.group(1) if city_match else "London"
        return tools.get_astronomy(city)
    except Exception as e:
        print(f"[Zara Astronomy Handler] Error: {e}")
        return None


def _handle_pokemon(text: str) -> Optional[str]:
    """Get Pokémon information."""
    import re
    poke_match = re.search(
        r'(?:pok[eé]mon|about)\s+(\w+)', text, re.IGNORECASE)

    if poke_match:
        try:
            import requests
            pokemon = poke_match.group(1).lower().strip()
            resp = requests.get(
                f"https://pokeapi.co/api/v2/pokemon/{pokemon}", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                name = data.get("name", pokemon).title()
                types = ", ".join(t["type"]["name"]
                                  for t in data.get("types", []))
                abilities = ", ".join(a["ability"]["name"]
                                      for a in data.get("abilities", []))
                stats = {s["stat"]["name"]: s["base_stat"]
                         for s in data.get("stats", [])}

                return (
                    f"⚡ {name}\n"
                    f"   🏷️ Types: {types}\n"
                    f"   💪 Abilities: {abilities}\n"
                    f"   📊 HP: {stats.get('hp', '?')} | Attack: {stats.get('attack', '?')} | Defense: {stats.get('defense', '?')}\n"
                    f"   🖼️ {data.get('sprites', {}).get('front_default', '')}"
                )
            return f"Pokémon '{pokemon}' not found."
        except Exception as e:
            print(f"[Zara] Pokémon error: {e}")
    return None


def _handle_recipe(text: str) -> Optional[str]:
    """Get recipe from TheMealDB."""
    import re
    recipe_match = re.search(
        r'(?:recipe for|how to make|cook)\s+(.+?)(?:$|\?|\.)', text, re.IGNORECASE)

    if recipe_match:
        try:
            import requests
            query = recipe_match.group(1).strip()
            resp = requests.get(
                "https://www.themealdb.com/api/json/v1/1/search.php",
                params={"s": query},
                timeout=10
            )
            if resp.status_code == 200:
                meals = resp.json().get("meals", [])
                if meals:
                    meal = meals[0]
                    ingredients = []
                    for i in range(1, 21):
                        ing = meal.get(f"strIngredient{i}")
                        meas = meal.get(f"strMeasure{i}")
                        if ing and ing.strip():
                            ingredients.append(f"{meas} {ing}".strip())

                    return (
                        f"🍽️ {meal.get('strMeal', 'Recipe')}\n"
                        f"   📍 Category: {meal.get('strCategory', 'N/A')}\n"
                        f"   🌍 Cuisine: {meal.get('strArea', 'N/A')}\n"
                        f"   📝 Ingredients:\n      • " +
                        "\n      • ".join(ingredients[:10]) + "\n"
                        f"   🔗 {meal.get('strSource', 'No source')}\n"
                        f"   🎬 {meal.get('strYoutube', 'No video')}"
                    )
            return f"No recipe found for '{query}'."
        except Exception as e:
            print(f"[Zara] Recipe error: {e}")
    return None


def _handle_spacex_launch() -> Optional[str]:
    """Get next SpaceX launch."""
    try:
        import requests
        resp = requests.get(
            "https://api.spacexdata.com/v5/launches/next", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return (
                f"🚀 Next SpaceX Launch\n"
                f"   📋 Mission: {data.get('name', 'Unknown')}\n"
                f"   📅 Date: {data.get('date_utc', 'Unknown')}\n"
                f"   🎯 Rocket: {data.get('rocket', 'Unknown')}\n"
                f"   📍 Launchpad: {data.get('launchpad', 'Unknown')}\n"
                f"   📺 {data.get('links', {}).get('webcast', '')}"
            )
    except Exception as e:
        print(f"[Zara] SpaceX error: {e}")
    return None


def reset_memory() -> None:
    """Wipe the rolling conversation window."""
    _history.clear()


if __name__ == "__main__":
    print("Zara is online. Type 'quit' to exit.\n")
    while True:
        try:
            user_in = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if user_in.lower() in {"quit", "exit"}:
            break
        print("Zara:", generate_response(user_in), "\n")
