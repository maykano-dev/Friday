"""Zara - lightweight always-on AI assistant core.

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
from user_prefs import get_prefs
from zara_vision import get_vision, VisionMode

_in_handler = False
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

SYSTEM_PROMPT = (
    "You are Zara, an advanced AI assistant and autonomous agent built at zara.ai. "
    "The user is SPEAKING to you. You are sharp, warm, efficient, and always one step ahead. "
    "You address male users as 'Sir' and female users as 'Ma'am', and adapt to each user naturally. "
    "You never say 'I cannot do that' — you find a way or offer the closest alternative. "
    "You never ask unnecessary questions. You manage multiple tasks simultaneously.\n\n"
    "CRITICAL RULES:\n"
    "1. Keep responses CONCISE - 1 to 3 short sentences maximum.\n"
    "2. DO NOT output <EXECUTE> blocks for simple actions like opening apps, playing music, "
    "creating folders, writing files, or searching the web. Just respond naturally—the system executes automatically.\n"
    "3. ONLY use <EXECUTE> for complex multi-step tasks like 'browse_web', 'fill_form', 'web_research', "
    "or 'verified_execute' (coding tasks).\n"
    "4. If the user's input is unclear, say 'I didn't catch that. Could you repeat it?' and STOP.\n"
    "5. NEVER mention typing, keyboards, or screens.\n\n"
    "You have access to tools: weather, jokes, news, crypto, web search, file creation, app launching, "
    "web browsing, form filling, and more.\n"
    "Be warm but BRIEF. One to three sentences is perfect."
)

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

    # Prepend chat history
    recent = memory_vault.get_recent_memories(limit=10)
    for m in recent:
        if m.startswith("User:"):
            messages.append(
                {"role": "user", "content": m.replace("User: ", "", 1)})
        elif m.startswith("Zara:"):
            messages.append(
                {"role": "assistant", "content": m.replace("Zara: ", "", 1)})

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
    """Send user_text to the best available endpoint and return reply."""
    global _in_handler

    if _in_handler:
        print("[Zara] WARNING: Recursive handler call detected, using LLM fallback")
        return _generate_llm_response(user_text)

    if not user_text or not user_text.strip():
        return "I didn't catch that."

    # Intercept explicit save commands
    save_payload = _extract_save_payload(user_text)
    if save_payload is not None:
        if save_payload:
            memory_vault.store_memory(save_payload)
        return "Saved to memory."

    # Handle system boot trigger
    if _is_system_boot_trigger(user_text):
        if not GROQ_API_KEY:
            return "Zara initialized. Ready for input."
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
            return "Zara initialized. Ready for input."
        reply = _visible_reply_text(reply).strip()
        return reply or "Zara initialized. Ready for input."

    # Voice ingest triggers
    user_lower = user_text.lower().strip()
    for trigger in VOICE_INGEST_TRIGGERS:
        if trigger in user_lower:
            try:
                import pygame
                import time
                from ui_engine import MANUAL_INGEST_CMD
                pygame.event.post(pygame.event.Event(MANUAL_INGEST_CMD))
                time.sleep(0.5)
            except:
                pass
            break

    # ========== NEW: Smart Router Integration ==========

    print(f"[Zara] Processing: '{user_text}'")

    def _handle_play_music(text: str) -> Optional[str]:
        """Smart music handler - learns preferences, works like Alexa."""
        import re
        import json
        import action_engine
        from user_prefs import get_prefs

        prefs = get_prefs()
        text_lower = text.lower()

        # ── DETECT APP (if specified) ─────────────────────────────
        detected_app = None
        if "spotify" in text_lower:
            detected_app = "spotify"
            prefs.set_music_app("spotify")
        elif "youtube" in text_lower:
            detected_app = "youtube_music"
            prefs.set_music_app("youtube_music")
        elif "apple music" in text_lower:
            detected_app = "apple_music"
            prefs.set_music_app("apple_music")

        # Use learned app if none specified
        app = detected_app or prefs.get_music_app()

        # If still no app, detect installed apps and pick first
        if not app:
            installed = prefs.detect_installed_music_apps()
            if installed:
                app = installed[0]
                prefs.set_music_app(app)
            else:
                app = "spotify"  # Fallback

        print(f"[Zara] Using music app: {app}")

        # ── EXTRACT QUERY ────────────────────────────────────────
        query = ""
        song_name = ""
        artist_name = ""

        # Remove command words
        cleaned = text_lower
        for word in ["play", "put on", "listen to", "i want to hear", "can you play"]:
            cleaned = cleaned.replace(word, "")
        cleaned = cleaned.strip()

        # Pattern 1: "[SONG] by [ARTIST]"
        match = re.search(r'(.+?)\s+by\s+(.+?)(?:\s+on\s+|\s*$)', cleaned)
        if match:
            song_name = match.group(1).strip()
            artist_name = match.group(2).strip()
            query = f"{artist_name} {song_name}"
            print(f"[Zara] Song: '{song_name}', Artist: '{artist_name}'")

        # Pattern 2: "play [ARTIST]"
        if not query:
            # If it's just an artist name
            known_artists = prefs.get_favorite_artists()
            for artist in known_artists:
                if artist.lower() in cleaned:
                    artist_name = artist
                    query = artist
                    print(f"[Zara] Playing artist: '{artist}'")
                    break

        # Pattern 3: Just a song name (no artist) - SMART SEARCH
        if not query and cleaned:
            # This could be just a song name - we'll search for it
            song_name = cleaned
            query = cleaned
            print(f"[Zara] Searching for song: '{song_name}'")

        # Pattern 4: "some music" or "music"
        if not query or query in ["music", "some music", "something"]:
            # Play user's recent favorites or discover weekly
            query = ""  # Empty = play whatever's recommended
            print("[Zara] Playing recommended music")

        # ── CLEAN QUERY ──────────────────────────────────────────
        if query:
            query = re.sub(r'[^\w\s]', ' ', query)
            query = re.sub(r'\s+', ' ', query).strip()

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
        if song_name and artist_name:
            prefs.add_recent_song(song_name, artist_name)
        elif query:
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
    web_tool_keywords = {
        # Knowledge & Research
        "weather": lambda txt: _handle_weather(txt),
        "temperature": lambda txt: _handle_weather(txt),
        "forecast": lambda txt: _handle_weather(txt),
        "define": lambda txt: _handle_definition(txt),
        "definition": lambda txt: _handle_definition(txt),
        "meaning of": lambda txt: _handle_definition(txt),
        "what does": lambda txt: _handle_definition(txt) if "mean" in txt else None,
        "synonym": lambda txt: _handle_synonyms(txt),
        "rhyme": lambda txt: _handle_rhymes(txt),
        "search": lambda txt: _handle_search(txt),
        "find": lambda txt: _handle_search(txt),
        "look up": lambda txt: _handle_search(txt),
        "tell me about": lambda txt: _handle_search(txt),
        "what is": lambda txt: _handle_search(txt),
        "who is": lambda txt: _handle_search(txt),
        "information on": lambda txt: _handle_search(txt),

        # Entertainment
        "joke": lambda txt: _handle_joke(),
        "funny": lambda txt: _handle_joke(),
        "make me laugh": lambda txt: _handle_joke(),
        "quote": lambda txt: _handle_quote(),
        "inspiration": lambda txt: _handle_quote(),
        "motivation": lambda txt: _handle_quote(),
        "cat fact": lambda txt: _handle_cat_fact(),
        "dog fact": lambda txt: _handle_dog_fact(),
        "fact": lambda txt: _handle_useless_fact(),
        "bored": lambda txt: _handle_bored_activity(),
        "what should i do": lambda txt: _handle_bored_activity(),
        "advice": lambda txt: _handle_advice(),
        "help me": lambda txt: _handle_advice(),

        # Crypto & Finance
        "bitcoin": lambda txt: _handle_crypto("bitcoin"),
        "btc": lambda txt: _handle_crypto("bitcoin"),
        "ethereum": lambda txt: _handle_crypto("ethereum"),
        "eth": lambda txt: _handle_crypto("ethereum"),
        "doge": lambda txt: _handle_crypto("dogecoin"),
        "dogecoin": lambda txt: _handle_crypto("dogecoin"),
        "crypto": lambda txt: _handle_crypto(txt),
        "price of": lambda txt: _handle_crypto(txt) if any(c in txt for c in ["bitcoin", "ethereum", "doge", "crypto"]) else None,
        "exchange rate": lambda txt: _handle_exchange_rate(txt),
        "convert": lambda txt: _handle_exchange_rate(txt),
        "usd to": lambda txt: _handle_exchange_rate(txt),

        # News & Tech
        "hacker news": lambda txt: _handle_hacker_news(),
        "hn": lambda txt: _handle_hacker_news(),
        "dev.to": lambda txt: _handle_dev_to(),
        "github": lambda txt: _handle_github(txt),
        "npm": lambda txt: _handle_npm(txt),
        "pypi": lambda txt: _handle_pypi(txt),
        "pip package": lambda txt: _handle_pypi(txt),

        # Food
        "recipe": lambda txt: _handle_recipe(txt),
        "how do i make": lambda txt: _handle_recipe(txt),
        "how to cook": lambda txt: _handle_recipe(txt),
        "how to bake": lambda txt: _handle_recipe(txt),

        # Space & Science
        "nasa": lambda txt: _handle_nasa_apod(),
        "space picture": lambda txt: _handle_nasa_apod(),
        "astronomy": lambda txt: _handle_astronomy(txt),
        "sunrise": lambda txt: _handle_astronomy(txt),
        "sunset": lambda txt: _handle_astronomy(txt),
        "moon": lambda txt: _handle_astronomy(txt),
        "iss": lambda txt: _handle_iss_location(),
        "space station": lambda txt: _handle_iss_location(),
        "spacex": lambda txt: _handle_spacex_launch(),
        "rocket launch": lambda txt: _handle_spacex_launch(),

        # Utility
        "my ip": lambda txt: _handle_ip_info(txt),
        "what's my ip": lambda txt: _handle_ip_info(txt),
        "ip address": lambda txt: _handle_ip_info(txt),
        "validate email": lambda txt: _handle_email_validation(txt),
        "check email": lambda txt: _handle_email_validation(txt),
        "shorten": lambda txt: _handle_shorten_url(txt),
        "qr code": lambda txt: _handle_qr_code(txt),
        "time in": lambda txt: _handle_timezone(txt),
        "what time": lambda txt: _handle_timezone(txt),
        "timezone": lambda txt: _handle_timezone(txt),
        "holiday": lambda txt: _handle_holidays(txt),
        "public holiday": lambda txt: _handle_holidays(txt),
        "what can you do": lambda txt: _handle_what_can_you_do(),
        "capabilities": lambda txt: _handle_what_can_you_do(),
        "skills": lambda txt: _handle_what_can_you_do(),
        "what do you know": lambda txt: _handle_what_can_you_do(),
        "help me understand": lambda txt: _handle_what_can_you_do(),

        # Direct web search
        "google": lambda txt: _handle_web_search_direct(txt),
        "search for": lambda txt: _handle_web_search_direct(txt),
        "search the web": lambda txt: _handle_web_search_direct(txt),
        "look up on google": lambda txt: _handle_web_search_direct(txt),
        "browse": lambda txt: _handle_browse_website(txt),
        "go to": lambda txt: _handle_browse_website(txt),
        "open website": lambda txt: _handle_browse_website(txt),
        "visit": lambda txt: _handle_browse_website(txt),
        "navigate to": lambda txt: _handle_browse_website(txt),
        "fill form": lambda txt: _handle_fill_form(txt),
        "submit form": lambda txt: _handle_fill_form(txt),

        # Entertainment & Media
        "movie": lambda txt: _handle_movie_info(txt),
        "film": lambda txt: _handle_movie_info(txt),
        "book": lambda txt: _handle_book_info(txt),
        "novel": lambda txt: _handle_book_info(txt),
        "pokemon": lambda txt: _handle_pokemon(txt),
        "pokémon": lambda txt: _handle_pokemon(txt),

        # Space & Science
        "nasa picture": lambda txt: _handle_nasa_apod(),
        "astronomy picture": lambda txt: _handle_nasa_apod(),
        "iss": lambda txt: _handle_iss_location(),
        "space station": lambda txt: _handle_iss_location(),
        "spacex": lambda txt: _handle_spacex_launch(),
        "next launch": lambda txt: _handle_spacex_launch(),

        # Food
        "recipe": lambda txt: _handle_recipe(txt),
        "how to make": lambda txt: _handle_recipe(txt),
        "cook": lambda txt: _handle_recipe(txt),

        # Music & Media
        "play music": lambda txt: _handle_play_music(txt),
        "play song": lambda txt: _handle_play_music(txt),
        "play some": lambda txt: _handle_play_music(txt),
        "put on": lambda txt: _handle_play_music(txt),
        "pause music": lambda txt: _handle_play_music(txt),
        "pause song": lambda txt: _handle_play_music(txt),
        "next song": lambda txt: _handle_play_music(txt),
        "next track": lambda txt: _handle_play_music(txt),
        "skip this": lambda txt: _handle_play_music(txt),
        "previous song": lambda txt: _handle_play_music(txt),
        "spotify": lambda txt: _handle_play_music(txt) if "play" in txt.lower() else None,

        # Volume control
        "volume up": lambda txt: _handle_volume("up"),
        "volume down": lambda txt: _handle_volume("down"),
        "increase the volume": lambda txt: _handle_volume("up"),
        "decrease the volume": lambda txt: _handle_volume("down"),
        "turn it up": lambda txt: _handle_volume("up"),
        "turn it down": lambda txt: _handle_volume("down"),
        "mute": lambda txt: _handle_volume("mute"),

        # Vision Commands
        "what do you see": lambda txt: _handle_vision_command(txt),
        "what's on my screen": lambda txt: _handle_vision_command(txt),
        "look at": lambda txt: _handle_vision_command(txt),
        "read this": lambda txt: _handle_vision_command(txt),
        "read the": lambda txt: _handle_vision_command(txt),
        "is there an error": lambda txt: _handle_vision_command(txt),
        "analyze the screen": lambda txt: _handle_vision_command(txt),
        "open spotify": lambda txt: _handle_open_app(txt),
        "open chrome": lambda txt: _handle_open_app(txt),
        "launch": lambda txt: _handle_open_app(txt),
        
        # Music - catch ALL variations
        "play": lambda txt: _handle_play_music(txt),
        "song": lambda txt: _handle_play_music(txt),
        "music": lambda txt: _handle_play_music(txt),
        "spotify": lambda txt: _handle_play_music(txt),
        " by ": lambda txt: _handle_play_music(txt),
        "put on": lambda txt: _handle_play_music(txt),
        "listen to": lambda txt: _handle_play_music(txt),
        
        # Vision - Awareness
        "what do you see": lambda txt: _handle_vision_command(txt),
        "what's on my screen": lambda txt: _handle_vision_command(txt),
        "look at": lambda txt: _handle_vision_command(txt),
        "analyze this": lambda txt: _handle_vision_command(txt),
        "is there an error": lambda txt: _handle_vision_command(txt),
        "what window": lambda txt: _handle_vision_command(txt),
        
        # Window management
        "switch to": lambda txt: _handle_window_command(txt),
        "focus": lambda txt: _handle_window_command(txt),
        "minimize": lambda txt: _handle_window_command(txt),
        "maximize": lambda txt: _handle_window_command(txt),
        "close window": lambda txt: _handle_window_command(txt),
        "snap": lambda txt: _handle_window_command(txt),
        "arrange": lambda txt: _handle_window_command(txt),
        "tile": lambda txt: _handle_window_command(txt),
        "move window": lambda txt: _handle_window_command(txt),
        "list windows": lambda txt: _handle_window_command(txt),
        "open windows": lambda txt: _handle_window_command(txt),
        "show desktop": lambda txt: _handle_window_command(txt),
        
        # Catch artist names
        "chris brown": lambda txt: _handle_play_music(txt),
        "drake": lambda txt: _handle_play_music(txt),
        "stonebwoy": lambda txt: _handle_play_music(txt),
        "burna boy": lambda txt: _handle_play_music(txt),
    }

    matched_keyword = None
    matched_handler = None

    import re

    for keyword, handler in web_tool_keywords.items():
        # Match whole words only
        pattern = r'\b' + re.escape(keyword) + r'\b'
        if re.search(pattern, user_lower):
            matched_keyword = keyword
            matched_handler = handler
            print(f"[Zara] Matched keyword: '{keyword}'")
            break

    if matched_handler:
        if _in_handler:
            return _generate_llm_response(user_text)
        
        _in_handler = True
        try:
            print(f"[Zara] Handler: {matched_keyword}")
            result = matched_handler(user_text)
            
            # If handler returns a string, speak it
            if result:
                print(f"[Zara] Handler success: {result[:80]}...")
                import local_voice
                import threading
                threading.Thread(target=lambda: local_voice.speak(result), daemon=True).start()
                return result
            
            return None
            
        except Exception as e:
            print(f"[Zara] Handler error: {e}")
            import traceback
            traceback.print_exc()
            return _generate_llm_response(user_text)
        finally:
            _in_handler = False

    # Check if this is a research query
    research_keywords = ["search", "find", "look up",
                         "what is", "who is", "information about"]
    if any(kw in user_lower for kw in research_keywords):
        try:
            from smart_router import get_router
            router = get_router()
            response, endpoint = router.route(
                user_text,
                system_prompt=SYSTEM_PROMPT,
                allow_cache=True,
                allow_web_search=True
            )
            print(f"[Zara] Smart router used: {endpoint.value}")

            # Store in memory
            try:
                memory_vault.store_memory(f"User: {user_text}")
                memory_vault.store_memory(f"Zara: {response}")
            except:
                pass

            # Process any actions in the response
            action_match = _EXECUTE_PATTERN.search(response)
            if action_match:
                json_payload = action_match.group(1).strip()
                if json_payload:
                    try:
                        _action_executor.execute_payload(json_payload)
                    except Exception as e:
                        print(f"[Zara Action Err]: {e}")
                response = _visible_reply_text(response)

            return response
        except Exception as e:
            print(f"[Zara] Smart router failed, falling back to Groq: {e}")

    # ========== End Smart Router Integration ==========

    # Fall back to original Groq streaming for conversation
    try:
        relevant_memories = memory_vault.retrieve_memory(user_text)
    except Exception as e:
        print(f"[Zara Core] memory retrieval failed: {e}")
        relevant_memories = []

    messages = _build_messages(user_text, relevant_memories)

    if not GROQ_API_KEY:
        # Try Ollama fallback
        try:
            from smart_router import get_router
            router = get_router()
            response, _ = router.route(
                user_text, SYSTEM_PROMPT, allow_cache=True)
            return response
        except:
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
                word_count = len(sentence_buffer.split()
                                 ) if sentence_buffer else 0
                return

        if word_count >= 25:
            local_voice.speak(phrase)
            sentence_buffer = ""
            word_count = 0
            return

    for line in resp.iter_lines():
        if not line:
            continue
        line_str = line.decode("utf-8")

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


# ==================== FREE WEB TOOLS HANDLERS ====================

def _handle_weather(query: str) -> Optional[str]:
    """Get weather for a location."""
    try:
        from free_web_tools import get_web_tools
        tools = get_web_tools()
        city = query.split()[-1] if len(query.split()) > 1 else "London"
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
        words = query.split()
        word = words[-1] if words else "python"
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
        command_words = [
            "search", "find", "look up", "google", "for me",
            "tell me about", "what is", "who is", "information on",
            "search for", "google for", "look for", "can you",
            "could you", "please", "i need", "i want"
        ]

        cleaned = query.lower()
        for word in command_words:
            cleaned = cleaned.replace(word, "")

        # Remove common phrases
        phrases = ["and tell me about it", "and tell me", "for me", "about it"]
        for phrase in phrases:
            cleaned = cleaned.replace(phrase, "")

        # Clean punctuation and extra spaces
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
                user_text, SYSTEM_PROMPT, allow_cache=True)
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


def _handle_crypto(coin: str = "bitcoin") -> Optional[str]:
    """Get cryptocurrency price."""
    try:
        from free_web_tools import get_web_tools
        tools = get_web_tools()
        coin_name = "bitcoin"
        for c in ["bitcoin", "ethereum", "dogecoin", "solana", "cardano", "ripple", "polkadot"]:
            if c in coin.lower():
                coin_name = c
                break
        return tools.get_crypto_price(coin_name)
    except:
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
    try:
        from free_web_tools import get_web_tools
        tools = get_web_tools()
        tz_match = re.search(r'([A-Za-z]+/[A-Za-z_]+)', query)
        if tz_match:
            return tools.get_timezone_time(tz_match.group(1))
    except:
        pass
    return None


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
