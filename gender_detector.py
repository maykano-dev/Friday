"""Zara - Gender Detection System.

Detects user gender from:
1. Voice pitch analysis (formant detection via librosa)
2. Explicit mentions in conversation ("I'm a man/woman/guy/girl")
3. Names mentioned
4. Pronouns used

Stores result in prefs and state so Zara uses correct honorific.
"""

from __future__ import annotations

import re
import os
import json
from typing import Optional
from enum import Enum


class Gender(Enum):
    MALE = "male"
    FEMALE = "female"
    UNKNOWN = "unknown"


PREF_FILE = os.path.join(os.path.dirname(__file__), "zara_prefs.json")

# Explicit gender cues in text
MALE_PATTERNS = [
    r"\bi(?:'m| am) a (?:man|guy|male|boy|dude|bloke)\b",
    r"\bcall me (?:sir|mr\.?|mister)\b",
    r"\bhe/him\b",
    r"\bmy (?:husband|boyfriend|son|father|dad|brother)\b",  # context clues
    r"\bi(?:'m| am) male\b",
]

FEMALE_PATTERNS = [
    r"\bi(?:'m| am) a (?:woman|girl|female|lady|gal)\b",
    r"\bcall me (?:ma'?am|mrs\.?|ms\.?|miss|madam)\b",
    r"\bshe/her\b",
    r"\bmy (?:wife|girlfriend|daughter|mother|mom|sister)\b",
    r"\bi(?:'m| am) female\b",
]

# Common name databases (subset for fast matching)
MALE_NAMES = {
    "james", "john", "robert", "michael", "william", "david", "richard",
    "joseph", "thomas", "charles", "christopher", "daniel", "matthew",
    "anthony", "mark", "donald", "steven", "paul", "andrew", "joshua",
    "kevin", "brian", "george", "edward", "ronald", "timothy", "jason",
    "jeffrey", "ryan", "jacob", "gary", "nicholas", "eric", "jonathan",
    "stephen", "larry", "justin", "scott", "brandon", "benjamin", "samuel",
    "raymond", "gregory", "frank", "alexander", "patrick", "jack", "dennis",
    "jerry", "tyler", "aaron", "jose", "adam", "henry", "nathan", "douglas",
    "zachary", "peter", "kyle", "noah", "ethan", "jeremy", "walter", "christian",
    "kwame", "kofi", "ama", "kweku", "yaw", "kojo", "abena", "akosua",
    "mensah", "asante", "osei", "boateng", "asamoah", "owusu",
}

FEMALE_NAMES = {
    "mary", "patricia", "jennifer", "linda", "barbara", "elizabeth",
    "susan", "jessica", "sarah", "karen", "lisa", "nancy", "betty",
    "margaret", "sandra", "ashley", "dorothy", "kimberly", "emily",
    "donna", "michelle", "carol", "amanda", "melissa", "deborah",
    "stephanie", "rebecca", "sharon", "laura", "cynthia", "kathleen",
    "amy", "angela", "shirley", "anna", "brenda", "pamela", "emma",
    "nicole", "helen", "samantha", "katherine", "christine", "debra",
    "rachel", "carolyn", "janet", "catherine", "maria", "heather",
    "diane", "julie", "joyce", "victoria", "kelly", "christina",
    "joan", "evelyn", "lauren", "judith", "olivia", "alice", "julia",
    "abena", "akosua", "afia", "ama", "adwoa", "adjoa", "afua",
    "akua", "yaa", "efua", "araba", "maame", "abiba",
}


class GenderDetector:
    """Detects and remembers user gender for appropriate honorifics."""

    def __init__(self):
        self._gender = Gender.UNKNOWN
        self._confidence = 0.0
        self._load_from_prefs()

    def _load_from_prefs(self):
        """Load saved gender from prefs file."""
        try:
            if os.path.exists(PREF_FILE):
                with open(PREF_FILE, "r") as f:
                    data = json.load(f)
                saved = data.get("user_gender", "unknown")
                self._gender = Gender(saved)
        except Exception:
            pass

    def _save_to_prefs(self):
        """Persist detected gender."""
        try:
            data = {}
            if os.path.exists(PREF_FILE):
                with open(PREF_FILE, "r") as f:
                    data = json.load(f)
            data["user_gender"] = self._gender.value
            with open(PREF_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def detect_from_text(self, text: str) -> Gender:
        """Analyze text for gender cues."""
        text_lower = text.lower()

        # Check explicit patterns
        for pattern in MALE_PATTERNS:
            if re.search(pattern, text_lower):
                self._set_gender(Gender.MALE, 0.95)
                return self._gender

        for pattern in FEMALE_PATTERNS:
            if re.search(pattern, text_lower):
                self._set_gender(Gender.FEMALE, 0.95)
                return self._gender

        # Check for name introduction
        name_match = re.search(
            r"(?:my name is|i(?:'m| am)|call me|they call me)\s+([a-z]+)", text_lower
        )
        if name_match:
            name = name_match.group(1).strip()
            if name in MALE_NAMES:
                self._set_gender(Gender.MALE, 0.75)
            elif name in FEMALE_NAMES:
                self._set_gender(Gender.FEMALE, 0.75)

        return self._gender

    def detect_from_voice_pitch(self, audio_samples, sample_rate: int = 16000) -> Gender:
        """
        Detect gender from voice pitch using fundamental frequency analysis.
        Male voices: typically 85-180 Hz
        Female voices: typically 165-265 Hz
        """
        try:
            import numpy as np

            # Simple zero-crossing rate as proxy for pitch
            samples = np.array(audio_samples, dtype=np.float32)

            # Normalize
            if samples.max() > 0:
                samples = samples / samples.max()

            # Count zero crossings
            zero_crossings = np.sum(np.abs(np.diff(np.signbit(samples))))
            zcr = zero_crossings / (2.0 * len(samples) / sample_rate)

            # Map ZCR to approximate fundamental frequency
            # This is a rough estimate — use librosa for precision
            estimated_f0 = zcr * 0.8  # rough approximation

            if 80 < estimated_f0 < 165:
                self._set_gender(Gender.MALE, 0.65)
            elif 155 < estimated_f0 < 280:
                self._set_gender(Gender.FEMALE, 0.65)

        except Exception as e:
            print(f"[Gender Detector] Voice analysis failed: {e}")

        return self._gender

    def _set_gender(self, gender: Gender, confidence: float):
        """Update gender if confidence is higher than current."""
        if confidence > self._confidence:
            self._gender = gender
            self._confidence = confidence
            self._save_to_prefs()
            print(f"[Gender Detector] Detected: {gender.value} (confidence: {confidence:.0%})")

    def get_honorific(self) -> str:
        """Return Sir, Ma'am, or empty string based on detected gender."""
        if self._gender == Gender.MALE:
            return "Sir"
        elif self._gender == Gender.FEMALE:
            return "Ma'am"
        return "Sir"  # Default fallback

    def get_gender(self) -> Gender:
        return self._gender

    def reset(self):
        self._gender = Gender.UNKNOWN
        self._confidence = 0.0
        self._save_to_prefs()


# Global singleton
_detector: Optional[GenderDetector] = None


def get_gender_detector() -> GenderDetector:
    global _detector
    if _detector is None:
        _detector = GenderDetector()
    return _detector


def get_honorific() -> str:
    return get_gender_detector().get_honorific()
