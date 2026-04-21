"""Zara - Output Router (Vilberta-inspired smart separation)

Routes LLM output to the appropriate channel:
- Conversation → Voice (spoken)
- Code/Data → Context Wing (visual)
- Commands → Action Executor (executed)
- Mixed content → Split intelligently
"""

from __future__ import annotations

import re
import time
from typing import List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class RoutedOutput:
    """Output split into appropriate channels."""
    spoken: str           # What Zara should say out loud
    visual: Optional[str]  # What goes to Context Wing
    action: Optional[str]  # JSON action payload if present
    raw_response: str     # Original unprocessed response


class OutputRouter:
    """Analyzes LLM response and routes to voice/visual/action channels."""

    # Patterns to detect content that shouldn't be spoken
    CODE_PATTERNS = [
        r'```[\s\S]*?```',           # Code blocks
        r'`[^`]+`',                   # Inline code
        r'def\s+\w+\s*\([^)]*\):',    # Function definitions
        r'class\s+\w+:',              # Class definitions
        r'import\s+[\w\.,\s]+',       # Import statements
    ]

    # Patterns that should be visual-only
    VISUAL_ONLY_PATTERNS = [
        r'^[#]{1,6}\s+.+$',           # Markdown headers
        r'^\s*[-*+]\s+.+$',           # Bullet lists
        r'^\s*\d+\.\s+.+$',           # Numbered lists
        r'^\s*[|].+[|]\s*$',          # Table rows
    ]

    # Greeting substitutions to make speech more natural
    GREETING_SUBSTITUTIONS = {
        r'hello[.!]?': "Hello!",
        r'hi there[.!]?': "Hi there!",
        r'greetings[.!]?': "Greetings!",
    }

    def __init__(self):
        self.compiled_code_patterns = [re.compile(p, re.IGNORECASE | re.MULTILINE)
                                       for p in self.CODE_PATTERNS]
        self.compiled_visual_patterns = [re.compile(p, re.IGNORECASE | re.MULTILINE)
                                         for p in self.VISUAL_ONLY_PATTERNS]

    def route(self, raw_response: str, action_payload: Optional[str] = None) -> RoutedOutput:
        """
        Analyze response and determine what goes where.

        Returns RoutedOutput with:
        - spoken: Clean text for TTS
        - visual: Content for Context Wing
        - action: Action to execute
        """
        spoken = raw_response
        visual = None

        # Extract and remove action block if present
        action = action_payload
        if not action:
            action_match = re.search(
                r'<EXECUTE>(.*?)</EXECUTE>', raw_response, re.DOTALL)
            if action_match:
                action = action_match.group(1).strip()
                spoken = re.sub(r'<EXECUTE>.*?</EXECUTE>',
                                '', spoken, flags=re.DOTALL)

        # Detect code blocks
        code_blocks = []
        for pattern in self.compiled_code_patterns:
            matches = pattern.findall(spoken)
            if matches:
                code_blocks.extend(matches)
                spoken = pattern.sub('[Code block — see Context Wing]', spoken)

        # Detect visual-only content
        visual_lines = []
        spoken_lines = []

        for line in spoken.split('\n'):
            is_visual = False
            for pattern in self.compiled_visual_patterns:
                if pattern.match(line.strip()):
                    visual_lines.append(line)
                    is_visual = True
                    break

            if not is_visual:
                spoken_lines.append(line)

        # Only route list content to visual if it contains 3+ items, to reduce clutter.
        final_visual_lines = []
        if len(visual_lines) < 3:
            for line in visual_lines:
                if re.match(r'^\s*[|].+[|]\s*$', line.strip()):
                    final_visual_lines.append(line)
                else:
                    spoken_lines.append(line)
        else:
            final_visual_lines = visual_lines

        spoken = '\n'.join(spoken_lines).strip()

        if final_visual_lines:
            visual = '\n'.join(final_visual_lines)
        elif code_blocks:
            visual = '\n\n'.join(code_blocks)

        # Clean up spoken text
        spoken = self._clean_for_speech(spoken)

        return RoutedOutput(
            spoken=spoken,
            visual=visual,
            action=action,
            raw_response=raw_response
        )

    def _clean_for_speech(self, text: str) -> str:
        """Make text more natural for TTS."""
        # Remove markdown formatting
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # Bold
        text = re.sub(r'\*([^*]+)\*', r'\1', text)       # Italic
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)  # Links
        text = re.sub(r'`([^`]+)`', r'\1', text)         # Inline code

        # Remove excessive newlines
        text = re.sub(r'\n{3,}', '\n\n', text)

        return text.strip()

    def should_speak_code(self, code_length: int) -> bool:
        """Determine if code should be spoken or just shown."""
        # Never speak code longer than 100 characters
        return code_length < 100

    def create_visual_card(self, visual_content: str, card_type: str = "TEXT") -> dict:
        """Create a Context Card payload for the UI."""
        return {
            "type": card_type,
            "content": visual_content,
            "timestamp": time.time()
        }


# Global singleton
_router: Optional[OutputRouter] = None


def get_router() -> OutputRouter:
    global _router
    if _router is None:
        _router = OutputRouter()
    return _router
