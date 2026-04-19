#!/usr/bin/env python3
"""Test Zara in text mode to isolate the brain from voice input."""

import sys
import friday_core

print("=" * 50)
print("🧠 Testing Zara Brain (Text Mode)")
print("=" * 50)
print("\nType your message and press Enter")
print("Type 'quit', 'exit', or 'bye' to stop\n")

while True:
    try:
        text = input("You: ").strip()

        if not text:
            continue

        if text.lower() in ("quit", "exit", "bye"):
            print("\nGoodbye!")
            sys.exit(0)

        print("\n[Zara] Thinking...")
        response = friday_core.generate_response(text)

        print(f"\nZara: {response}\n")

    except KeyboardInterrupt:
        print("\n\nGoodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] {e}\n")
