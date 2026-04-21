"""Zara - Universal Messaging Agent.

Can send messages through any messaging app installed on the PC:
- WhatsApp (Desktop)
- Telegram (Desktop)
- Signal (Desktop)
- Discord
- Slack
- Microsoft Teams
- Messenger (Facebook)
- Instagram DMs
- SMS via Phone Link (Windows)
- Gmail / Outlook (web or desktop)

Flow:
1. Parse recipient and message from user command
2. Find the app and open it
3. Navigate to contact using vision + OCR
4. Type the message
5. READ THE MESSAGE BACK TO USER for confirmation
6. Wait for "send it" / "yes" / "cancel" / "no" 
7. Send or cancel based on response
"""

from __future__ import annotations

import re
import time
import threading
import subprocess
from typing import Optional, Callable
from dataclasses import dataclass
from enum import Enum


class MessagingApp(Enum):
    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"
    SIGNAL = "signal"
    DISCORD = "discord"
    SLACK = "slack"
    TEAMS = "teams"
    MESSENGER = "messenger"
    INSTAGRAM = "instagram"
    SMS = "sms"
    GMAIL = "gmail"
    OUTLOOK = "outlook"
    UNKNOWN = "unknown"


@dataclass
class MessageRequest:
    """A pending message awaiting confirmation."""
    app: MessagingApp
    recipient: str
    message: str
    confirmed: bool = False
    cancelled: bool = False


class MessagingAgent:
    """
    Sends messages through any app with user confirmation before sending.
    """

    # App detection keywords
    APP_KEYWORDS = {
        MessagingApp.WHATSAPP: ["whatsapp", "whats app"],
        MessagingApp.TELEGRAM: ["telegram"],
        MessagingApp.SIGNAL: ["signal"],
        MessagingApp.DISCORD: ["discord"],
        MessagingApp.SLACK: ["slack"],
        MessagingApp.TEAMS: ["teams", "microsoft teams"],
        MessagingApp.MESSENGER: ["messenger", "facebook", "fb"],
        MessagingApp.INSTAGRAM: ["instagram", "insta", "ig", "dm"],
        MessagingApp.SMS: ["sms", "text", "message", "phone", "phone link"],
        MessagingApp.GMAIL: ["gmail", "email", "mail"],
        MessagingApp.OUTLOOK: ["outlook"],
    }

    def __init__(self, speak_callback: Callable[[str], None], listen_callback: Callable[[], str]):
        self.speak = speak_callback
        self.listen = listen_callback
        self._pending_message: Optional[MessageRequest] = None
        self._confirmation_event = threading.Event()
        self._confirmation_result: Optional[bool] = None

    def parse_message_command(self, text: str) -> Optional[MessageRequest]:
        """
        Parse natural language message command.
        
        Examples:
        - "Send a message to John on WhatsApp saying hello"
        - "Text Sarah that I'll be late"
        - "Message David on Discord: are you free tonight?"
        - "Send an email to boss@company.com saying I'm sick"
        """
        text_lower = text.lower()

        # Detect app
        app = MessagingApp.UNKNOWN
        for msg_app, keywords in self.APP_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                app = msg_app
                break

        # Default to WhatsApp if no app specified but "message/text" used
        if app == MessagingApp.UNKNOWN:
            if any(w in text_lower for w in ["send", "message", "text", "tell"]):
                app = MessagingApp.WHATSAPP

        # Extract recipient
        recipient = self._extract_recipient(text)
        if not recipient:
            return None

        # Extract message content
        message = self._extract_message(text)
        if not message:
            return None

        return MessageRequest(app=app, recipient=recipient, message=message)

    def _extract_recipient(self, text: str) -> Optional[str]:
        """Extract recipient name from command."""
        patterns = [
            r"(?:send|message|text|tell|email|dm)\s+(?:a\s+)?(?:message\s+)?(?:to\s+)?([A-Za-z][A-Za-z\s]+?)(?:\s+(?:on|via|using|through|saying|that|:))",
            r"(?:to|@)\s+([A-Za-z][A-Za-z\s]+?)(?:\s+(?:on|via|saying|that|:|\,))",
            r"send\s+([A-Za-z][A-Za-z\s]+?)\s+a\s+message",
            r"message\s+([A-Za-z][A-Za-z\s]+?)\s+(?:saying|that|:)",
            r"tell\s+([A-Za-z][A-Za-z\s]+?)\s+(?:that|to|:)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                # Filter out common words that aren't names
                if name.lower() not in ["me", "them", "him", "her", "us", "you", "someone"]:
                    return name

        # Email address
        email_match = re.search(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b", text)
        if email_match:
            return email_match.group(0)

        return None

    def _extract_message(self, text: str) -> Optional[str]:
        """Extract the message content from command."""
        patterns = [
            r"(?:saying|say|that|message:|:)\s+['\"]?(.+)['\"]?$",
            r"(?:saying|say|that)\s+(.+)$",
            r":\s*(.+)$",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                msg = match.group(1).strip().strip('"\'')
                if len(msg) > 1:
                    return msg

        # Try: everything after "to [name] on [app]"
        multi_match = re.search(
            r"(?:on|via|using|through)\s+\w+\s+(?:saying|say|that|:)?\s*(.+)$",
            text, re.IGNORECASE
        )
        if multi_match:
            msg = multi_match.group(1).strip().strip('"\'')
            if len(msg) > 1:
                return msg

        return None

    def initiate_send(self, request: MessageRequest) -> None:
        """
        Start the send flow: compose, confirm, then send.
        This is the main entry point - handles the whole conversation flow.
        """
        self._pending_message = request
        honorific = "Sir"
        try:
            from gender_detector import get_honorific
            honorific = get_honorific()
        except Exception:
            pass

        app_name = request.app.value.title()

        # Read back the message for confirmation
        confirmation_text = (
            f"I'm about to send this {app_name} message to {request.recipient}. "
            f"The message reads: {request.message}. "
            f"Shall I send it, {honorific}?"
        )
        self.speak(confirmation_text)

        # Wait for confirmation (handled externally by zara_core)
        # The pending request is stored and checked in handle_confirmation()

    def handle_confirmation(self, user_response: str) -> Optional[str]:
        """
        Process user's yes/no response to message confirmation.
        Returns result message to speak, or None if not a confirmation.
        """
        if not self._pending_message:
            return None

        response_lower = user_response.lower().strip()
        honorific = "Sir"
        try:
            from gender_detector import get_honorific
            honorific = get_honorific()
        except Exception:
            pass

        # Positive responses
        yes_words = [
            "yes", "yeah", "yep", "yup", "send it", "go ahead", "confirm",
            "do it", "send", "ok", "okay", "sure", "absolutely", "correct",
            "that's right", "affirmative", "proceed",
        ]

        # Negative responses
        no_words = [
            "no", "nope", "cancel", "don't", "stop", "abort", "nevermind",
            "never mind", "wait", "hold on", "actually", "wrong",
        ]

        is_yes = any(w in response_lower for w in yes_words)
        is_no = any(w in response_lower for w in no_words)

        if not is_yes and not is_no:
            return None  # Not a confirmation response

        if is_no:
            request = self._pending_message
            self._pending_message = None
            return f"Message to {request.recipient} cancelled, {honorific}."

        if is_yes:
            request = self._pending_message
            self._pending_message = None

            # Execute the send in background
            threading.Thread(
                target=self._execute_send,
                args=(request, honorific),
                daemon=True
            ).start()

            return f"Sending message to {request.recipient} now, {honorific}."

        return None

    def has_pending_confirmation(self) -> bool:
        return self._pending_message is not None

    def _execute_send(self, request: MessageRequest, honorific: str) -> None:
        """Actually send the message through the app."""
        try:
            success = False

            if request.app == MessagingApp.WHATSAPP:
                success = self._send_whatsapp(request.recipient, request.message)
            elif request.app == MessagingApp.TELEGRAM:
                success = self._send_telegram(request.recipient, request.message)
            elif request.app == MessagingApp.DISCORD:
                success = self._send_discord(request.recipient, request.message)
            elif request.app == MessagingApp.SLACK:
                success = self._send_slack(request.recipient, request.message)
            elif request.app == MessagingApp.TEAMS:
                success = self._send_teams(request.recipient, request.message)
            elif request.app in (MessagingApp.GMAIL, MessagingApp.OUTLOOK):
                success = self._send_email(request.recipient, request.message, request.app)
            elif request.app == MessagingApp.SMS:
                success = self._send_sms(request.recipient, request.message)
            else:
                # Generic: try to open the app and find the contact
                success = self._send_generic(request.app.value, request.recipient, request.message)

            if success:
                self.speak(f"Message sent to {request.recipient}, {honorific}.")
            else:
                self.speak(f"I had trouble sending the message, {honorific}. You may need to send it manually.")

        except Exception as e:
            print(f"[Messaging] Send error: {e}")
            self.speak(f"Something went wrong sending the message, {honorific}.")

    def _send_whatsapp(self, recipient: str, message: str) -> bool:
        """Send WhatsApp message via desktop app."""
        try:
            import subprocess, os, time
            import pyautogui
            import pyperclip

            # Try WhatsApp URL scheme first (opens or activates WhatsApp)
            encoded_msg = message.replace(" ", "%20")

            # Check if WhatsApp is installed as UWP or desktop
            wa_path = os.path.expanduser("~\\AppData\\Local\\WhatsApp\\WhatsApp.exe")

            if os.path.exists(wa_path):
                subprocess.Popen([wa_path])
            else:
                os.startfile("whatsapp://")

            time.sleep(3)

            # Focus WhatsApp
            from action_engine import focus_app
            focus_app("WhatsApp")
            time.sleep(1)

            # Use Ctrl+F to search for contact
            pyautogui.hotkey("ctrl", "f")
            time.sleep(0.5)
            pyperclip.copy(recipient)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(1.5)

            # Press Enter to open first result
            pyautogui.press("enter")
            time.sleep(0.8)

            # Type message in chat input
            pyautogui.hotkey("ctrl", "a")
            pyperclip.copy(message)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.3)

            # Send
            pyautogui.press("enter")
            time.sleep(0.5)

            return True

        except Exception as e:
            print(f"[Messaging] WhatsApp error: {e}")
            return False

    def _send_telegram(self, recipient: str, message: str) -> bool:
        """Send Telegram message."""
        try:
            import os, time
            import pyautogui
            import pyperclip

            os.startfile("tg://")
            time.sleep(2)

            from action_engine import focus_app
            focus_app("Telegram")
            time.sleep(1)

            # Ctrl+K opens search in Telegram
            pyautogui.hotkey("ctrl", "k")
            time.sleep(0.5)
            pyperclip.copy(recipient)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(1.5)
            pyautogui.press("enter")
            time.sleep(0.5)

            pyperclip.copy(message)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.3)
            pyautogui.press("enter")

            return True

        except Exception as e:
            print(f"[Messaging] Telegram error: {e}")
            return False

    def _send_discord(self, recipient: str, message: str) -> bool:
        """Send Discord DM."""
        try:
            import os, time
            import pyautogui
            import pyperclip

            os.startfile("discord://")
            time.sleep(3)

            from action_engine import focus_app
            focus_app("Discord")
            time.sleep(1)

            # Ctrl+K opens quick switcher in Discord
            pyautogui.hotkey("ctrl", "k")
            time.sleep(0.5)
            pyperclip.copy(recipient)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(1.5)
            pyautogui.press("enter")
            time.sleep(0.8)

            pyperclip.copy(message)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.3)
            pyautogui.press("enter")

            return True

        except Exception as e:
            print(f"[Messaging] Discord error: {e}")
            return False

    def _send_slack(self, recipient: str, message: str) -> bool:
        """Send Slack DM."""
        try:
            import os, time
            import pyautogui
            import pyperclip

            os.startfile("slack://")
            time.sleep(3)

            from action_engine import focus_app
            focus_app("Slack")
            time.sleep(1)

            # Ctrl+K opens DM search in Slack
            pyautogui.hotkey("ctrl", "k")
            time.sleep(0.5)
            pyperclip.copy(recipient)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(1.5)
            pyautogui.press("enter")
            time.sleep(0.8)

            pyperclip.copy(message)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.3)
            pyautogui.press("enter")

            return True

        except Exception as e:
            print(f"[Messaging] Slack error: {e}")
            return False

    def _send_teams(self, recipient: str, message: str) -> bool:
        """Send Microsoft Teams message."""
        try:
            import os, time
            import pyautogui
            import pyperclip

            subprocess.Popen(["ms-teams:"])
            time.sleep(3)

            from action_engine import focus_app
            focus_app("Teams")
            time.sleep(1)

            # Ctrl+F1 opens new chat in Teams
            pyautogui.hotkey("ctrl", "F1")
            time.sleep(0.5)
            pyperclip.copy(recipient)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(1.5)
            pyautogui.press("enter")
            time.sleep(0.8)

            pyperclip.copy(message)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.3)
            pyautogui.press("enter")

            return True

        except Exception as e:
            print(f"[Messaging] Teams error: {e}")
            return False

    def _send_email(self, recipient: str, message: str, app: MessagingApp) -> bool:
        """Send email via Gmail or Outlook."""
        try:
            import webbrowser
            import urllib.parse

            # Extract subject from message (first sentence or 50 chars)
            subject = message[:50].split(".")[0] if "." in message[:50] else message[:50]

            if app == MessagingApp.GMAIL:
                url = f"https://mail.google.com/mail/?view=cm&to={urllib.parse.quote(recipient)}&su={urllib.parse.quote(subject)}&body={urllib.parse.quote(message)}"
                webbrowser.open(url)
            else:  # Outlook
                url = f"mailto:{recipient}?subject={urllib.parse.quote(subject)}&body={urllib.parse.quote(message)}"
                webbrowser.open(url)

            time.sleep(3)
            # Press Send (Ctrl+Enter in most email clients)
            import pyautogui
            pyautogui.hotkey("ctrl", "enter")

            return True

        except Exception as e:
            print(f"[Messaging] Email error: {e}")
            return False

    def _send_sms(self, recipient: str, message: str) -> bool:
        """Send SMS via Windows Phone Link."""
        try:
            import subprocess, time
            import pyautogui
            import pyperclip

            # Open Phone Link
            subprocess.Popen(["ms-phonelink://"])
            time.sleep(3)

            from action_engine import focus_app
            focus_app("Phone Link")
            time.sleep(1)

            # Navigate to Messages tab
            pyautogui.hotkey("ctrl", "2")  # Messages tab shortcut
            time.sleep(0.5)

            # New message button - try clicking it
            # Fallback to Ctrl+N
            pyautogui.hotkey("ctrl", "n")
            time.sleep(0.5)

            pyperclip.copy(recipient)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(1.5)
            pyautogui.press("enter")
            time.sleep(0.5)

            pyperclip.copy(message)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.3)
            pyautogui.press("enter")

            return True

        except Exception as e:
            print(f"[Messaging] SMS error: {e}")
            return False

    def _send_generic(self, app_name: str, recipient: str, message: str) -> bool:
        """Generic send using vision + OCR to navigate the app."""
        try:
            import os, time
            import pyautogui
            import pyperclip

            # Try to launch the app
            os.startfile(app_name)
            time.sleep(3)

            from action_engine import focus_app
            focus_app(app_name)
            time.sleep(1)

            # Try common search shortcuts
            for shortcut in [("ctrl", "k"), ("ctrl", "f"), ("ctrl", "n")]:
                pyautogui.hotkey(*shortcut)
                time.sleep(0.3)

                # Check if a search box appeared via OCR
                try:
                    from zara_vision import get_vision
                    vision = get_vision()
                    coords = vision.find_element("search contact input box")
                    if coords:
                        pyautogui.click(*coords)
                        time.sleep(0.2)
                        pyperclip.copy(recipient)
                        pyautogui.hotkey("ctrl", "v")
                        time.sleep(1.0)
                        pyautogui.press("enter")
                        time.sleep(0.5)
                        pyperclip.copy(message)
                        pyautogui.hotkey("ctrl", "v")
                        time.sleep(0.3)
                        pyautogui.press("enter")
                        return True
                except Exception:
                    pass

                # Escape failed shortcut
                pyautogui.press("escape")

            return False

        except Exception as e:
            print(f"[Messaging] Generic send error: {e}")
            return False


# Global singleton
_agent: Optional[MessagingAgent] = None


def get_messaging_agent(
    speak_callback: Callable = None,
    listen_callback: Callable = None
) -> MessagingAgent:
    global _agent
    if _agent is None:
        if speak_callback is None:
            from local_voice import speak
            speak_callback = speak
        if listen_callback is None:
            listen_callback = lambda: ""
        _agent = MessagingAgent(speak_callback, listen_callback)
    return _agent
