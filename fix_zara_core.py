import sys

def fix_zara_core(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    out_lines = []
    
    # 1. We will extract all the 4-space indented functions and outdent them
    # 2. We will extract web_tool_keywords and outdent it
    # 3. We will delete the duplicate loop
    # 4. We will replace SYSTEM_PROMPT
    # 5. We will replace _call_groq_streaming
    
    # Wait, the easiest way to do this is to just read line by line.
    
    i = 0
    in_system_prompt = False
    in_call_groq_streaming = False
    in_wrongly_indented_handlers = False
    in_web_tool_keywords = False
    in_duplicate_loop = False
    
    extracted_handlers = []
    extracted_keywords = []
    
    while i < len(lines):
        line = lines[i]
        
        # SYSTEM_PROMPT replacement
        if line.startswith("SYSTEM_PROMPT = ("):
            in_system_prompt = True
            # Insert get_dynamic_system_prompt
            out_lines.append('''def get_dynamic_system_prompt() -> str:
    """Build system prompt with correct honorific for detected gender."""
    try:
        from gender_detector import get_honorific
        honorific = get_honorific()
    except Exception:
        honorific = "Sir"
    
    return (
        f"You are Zara, an advanced AI assistant and autonomous agent built at zara.ai. "
        f"The user is SPEAKING to you. You are sharp, warm, efficient, and always one step ahead. "
        f"Address this user as '{honorific}'. "
        f"You never say 'I cannot do that' — you find a way or offer the closest alternative. "
        f"You never ask unnecessary questions. You manage multiple tasks simultaneously.\\n\\n"
        f"CRITICAL RULES:\\n"
        f"1. Keep responses CONCISE - 1 to 3 short sentences maximum.\\n"
        f"2. DO NOT output <EXECUTE> blocks for simple actions like opening apps, playing music, "
        f"creating folders, writing files, or searching the web.\\n"
        f"3. ONLY use <EXECUTE> for complex multi-step tasks like browse_web, fill_form, web_research, "
        f"or verified_execute.\\n"
        f"4. If input is unclear, say 'I didn't catch that. Could you repeat it?' and STOP.\\n"
        f"5. NEVER mention typing, keyboards, or screens.\\n\\n"
        f"Be warm but BRIEF. One to three sentences is perfect."
    )

SYSTEM_PROMPT = ""  # Deprecated, use get_dynamic_system_prompt()
''')
            i += 1
            continue
            
        if in_system_prompt:
            if line.startswith(")"):
                in_system_prompt = False
            i += 1
            continue
            
        # Replace _call_groq_streaming up to the start of the next def
        if line.startswith("def _call_groq_streaming(user_text: str) -> str:"):
            in_call_groq_streaming = True
            out_lines.append(line)
            # We will provide the implementation later or just copy the user's patch.
            # Actually, the user's patch for _call_groq_streaming handles everything, including smart_router.
            # But the user's patch is huge. Let's just write the patch.
            
            patch = """    \"\"\"Full streaming Groq implementation.\"\"\"
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

    resp = _post_groq(payload, stream=True)
    if isinstance(resp, str):
        return resp

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
        sentence_pattern = re.compile(r'^([^.!?:]*[.!?:])(?:\\s|$)', re.DOTALL)
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
"""
            out_lines.append(patch)
            i += 1
            continue
            
        if in_call_groq_streaming:
            if line.startswith("    def _handle_") or line.startswith("    web_tool_keywords = ["):
                in_call_groq_streaming = False
            else:
                i += 1
                continue
                
        # Extract handlers that are wrongly indented by 4 spaces
        if line.startswith("    def _handle_"):
            in_wrongly_indented_handlers = True
            extracted_handlers.append(line[4:])
            i += 1
            continue
            
        if in_wrongly_indented_handlers:
            if line.startswith("    web_tool_keywords = ["):
                in_wrongly_indented_handlers = False
            elif line.startswith("    def _handle_"):
                extracted_handlers.append(line[4:])
                i += 1
                continue
            elif line.startswith("        ") or line.strip() == "" or line.startswith("    #") or line.startswith('    """'):
                extracted_handlers.append(line[4:] if len(line) > 4 else "\n")
                i += 1
                continue
            else:
                in_wrongly_indented_handlers = False
                
        # Extract web_tool_keywords
        if line.startswith("    web_tool_keywords = ["):
            in_web_tool_keywords = True
            extracted_keywords.append("web_tool_keywords = [\n")
            # Inject messaging handler
            extracted_keywords.append('        ("send a message", lambda txt: _handle_send_message(txt)),\n')
            extracted_keywords.append('        ("send message", lambda txt: _handle_send_message(txt)),\n')
            extracted_keywords.append('        ("text someone", lambda txt: _handle_send_message(txt)),\n')
            extracted_keywords.append('        ("message someone", lambda txt: _handle_send_message(txt)),\n')
            extracted_keywords.append('        ("dm ", lambda txt: _handle_send_message(txt)),\n')
            extracted_keywords.append('        ("send a dm", lambda txt: _handle_send_message(txt)),\n')
            i += 1
            continue
            
        if in_web_tool_keywords:
            if line.startswith("    ]"):
                extracted_keywords.append("]\n")
                in_web_tool_keywords = False
                # The duplicate loop comes after this.
                in_duplicate_loop = True
                i += 1
                continue
            else:
                extracted_keywords.append(line[4:] if len(line) > 4 else "\n")
                i += 1
                continue
                
        # Delete duplicate loop and redundant smart router integration
        if in_duplicate_loop:
            # We skip lines until we reach "def _handle_weather" which is the start of FREE WEB TOOLS
            if line.startswith("def _handle_weather"):
                in_duplicate_loop = False
                # Before adding _handle_weather, let's output our extracted handlers and keywords
                out_lines.append("\n\n")
                out_lines.append('''.
# ==================== EXTRACTED HANDLERS & KEYWORDS ====================

def _handle_send_message(text: str) -> Optional[str]:
    """Handle send message commands with confirmation flow."""
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
            return None
        
    except Exception as e:
        print(f"[Messaging Handler] Error: {e}")
    return None

'''.replace('.', ''))
                
                out_lines.extend(extracted_handlers)
                out_lines.append("\n")
                out_lines.extend(extracted_keywords)
                out_lines.append("\n\n")
                
                out_lines.append(line)
            i += 1
            continue
            
        # Also need to replace SYSTEM_PROMPT in _build_messages and _build_system_boot_messages
        if "SYSTEM_PROMPT" in line and ("_build_messages" in line or "append" in line or "sys_text = SYSTEM_PROMPT" in line):
            line = line.replace("SYSTEM_PROMPT", "get_dynamic_system_prompt()")
            
        out_lines.append(line)
        i += 1

    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(out_lines)

fix_zara_core('c:/Users/Maikano/Documents/Friday/zara_core.py')
print("Done")
