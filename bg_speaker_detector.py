"""Zara - Background Speaker Detection.

Distinguishes between:
1. Direct address to Zara (high confidence, near mic, wake-word prefixed)
2. Background conversation (other people talking, TV/radio noise, ambient speech)
3. Silence / non-speech

Uses multiple signal characteristics:
- Energy level (direct speech is louder)
- Wake word presence
- Spectral characteristics (voice direction / distance proxy)
- Temporal patterns (overlapping voices)
"""

from __future__ import annotations

import time
import threading
import re
from collections import deque
from typing import Optional
import numpy as np


class SpeakerContext:
    """Classification result for a speech segment."""
    DIRECT = "direct"           # User is talking to Zara
    BACKGROUND = "background"   # Someone else talking in background
    AMBIENT = "ambient"         # TV, radio, music
    UNKNOWN = "unknown"


class BackgroundSpeakerDetector:
    """
    Detects whether detected speech is directed at Zara or background.
    
    Strategy:
    - Wake word present → DIRECT (high confidence)
    - Energy much higher than calibrated baseline → more likely DIRECT
    - Broadband/flat spectrum during playback → AMBIENT (music/TV)
    - Multiple overlapping voice signatures → BACKGROUND
    - Lacks sentence structure or question form without name → ambiguous
    - Short utterances without wake word during media playback → BACKGROUND
    """

    def __init__(self):
        # Energy baseline from calibration
        self.baseline_energy = 500.0
        self.direct_energy_multiplier = 1.8  # Direct speech is ~1.8x louder

        # Spectral centroid baseline (voice distance proxy)
        self.baseline_spectral_centroid = 1800.0

        # Recent classification history
        self._history: deque = deque(maxlen=20)

        # Confidence threshold to act on speech
        self.confidence_threshold = 0.6

        # Wake words that guarantee DIRECT classification
        self.wake_words = [
            "zara", "hey zara", "okay zara", "ok zara", "hi zara"
        ]

        # Background speech indicators
        self.background_indicators = [
            "yeah", "you know", "like", "um", "uh", "actually",
            "basically", "literally", "honestly", "totally",
        ]

        # Direct address patterns (questions/commands to Zara)
        self.direct_patterns = [
            r"(?:can you|could you|would you|please|zara)\b",
            r"(?:what|how|why|when|where|who)\s+(?:is|are|was|were|do|does|did|can|should|will)\b",
            r"(?:tell me|show me|find|search|play|open|close|set|turn)\b",
            r"(?:volume|weather|time|date|news|music|timer|alarm)\b",
        ]

        self._lock = threading.Lock()

    def calibrate(self, background_energy: float, background_centroid: float = None):
        """Update baselines from ambient noise calibration."""
        self.baseline_energy = max(100.0, background_energy)
        if background_centroid:
            self.baseline_spectral_centroid = background_centroid
        print(f"[BG Detector] Calibrated: energy={self.baseline_energy:.0f}")

    def classify_audio(
        self,
        audio_frames: list,
        sample_rate: int = 16000,
        transcription: Optional[str] = None,
        media_playing: bool = False,
    ) -> tuple[str, float]:
        """
        Classify speech as DIRECT, BACKGROUND, or AMBIENT.
        
        Returns (classification, confidence)
        """
        # Build feature vector
        features = self._extract_features(audio_frames, sample_rate)

        # Rule 1: Wake word → definitely DIRECT
        if transcription:
            text_lower = transcription.lower().strip()
            for wake in self.wake_words:
                if text_lower.startswith(wake) or f" {wake}" in text_lower:
                    return SpeakerContext.DIRECT, 0.99

        # Rule 2: Ambient media signature (music/TV) detection.
        # High spectral flatness and weak voice-band dominance generally indicate non-speech.
        spectral_flatness = features.get("spectral_flatness", 0.0)
        voice_ratio = features.get("voice_band_ratio", 1.0)
        centroid = features.get("spectral_centroid", self.baseline_spectral_centroid)
        if (spectral_flatness > 0.30 and voice_ratio < 0.45) or (media_playing and spectral_flatness > 0.26 and centroid > 2600):
            return SpeakerContext.AMBIENT, 0.88

        # Rule 2: Media playing + no wake word → likely BACKGROUND
        if media_playing and transcription:
            text_lower = transcription.lower()
            if not any(kw in text_lower for kw in ["zara", "volume", "pause", "stop", "skip"]):
                return SpeakerContext.BACKGROUND, 0.80

        # Rule 3: Energy analysis
        energy_ratio = features["energy"] / max(self.baseline_energy, 1.0)

        if energy_ratio < 0.8:
            # Very quiet → background or far away
            return SpeakerContext.BACKGROUND, 0.75

        if energy_ratio > self.direct_energy_multiplier:
            # Loud and clear → likely direct
            direct_score = 0.70
        elif energy_ratio > 1.2:
            direct_score = 0.55
        else:
            direct_score = 0.40

        # Rule 4: Text analysis
        if transcription:
            text_lower = transcription.lower()

            # Check for direct address patterns
            for pattern in self.direct_patterns:
                if re.search(pattern, text_lower):
                    direct_score += 0.20
                    break

            # Check for background speech indicators
            bg_count = sum(1 for ind in self.background_indicators if f" {ind} " in f" {text_lower} ")
            if bg_count >= 2:
                direct_score -= 0.25

            # Very short utterances without structure are likely background fragments
            word_count = len(text_lower.split())
            if word_count <= 2 and "zara" not in text_lower:
                direct_score -= 0.20

        # Rule 5: Spectral characteristics
        if features.get("spectral_centroid"):
            sc_ratio = features["spectral_centroid"] / self.baseline_spectral_centroid
            if sc_ratio > 1.3:
                # Higher frequency content = closer/clearer speech
                direct_score += 0.10

        # Clamp and classify
        direct_score = max(0.0, min(1.0, direct_score))

        if direct_score >= self.confidence_threshold:
            classification = SpeakerContext.DIRECT
        else:
            classification = SpeakerContext.BACKGROUND

        confidence = direct_score if classification == SpeakerContext.DIRECT else (1.0 - direct_score)

        # Log to history
        with self._lock:
            self._history.append({
                "time": time.time(),
                "classification": classification,
                "confidence": confidence,
                "energy_ratio": energy_ratio,
            })

        return classification, confidence

    def _extract_features(self, frames: list, sample_rate: int) -> dict:
        """Extract audio features for classification."""
        features = {}

        try:
            # Combine frames
            all_samples = np.frombuffer(b"".join(frames), dtype=np.int16).astype(np.float32)

            if len(all_samples) == 0:
                return {"energy": 0.0}

            # RMS energy
            features["energy"] = float(np.sqrt(np.mean(all_samples ** 2)))

            # Spectral centroid (rough)
            if len(all_samples) > 512:
                fft_mag = np.abs(np.fft.rfft(all_samples[:4096]))
                freqs = np.fft.rfftfreq(min(len(all_samples), 4096), 1.0 / sample_rate)
                if fft_mag.sum() > 0:
                    features["spectral_centroid"] = float(
                        np.sum(freqs * fft_mag) / np.sum(fft_mag)
                    )
                    # Spectral flatness: higher for noise/music beds, lower for voiced speech.
                    fft_safe = fft_mag + 1e-10
                    features["spectral_flatness"] = float(
                        np.exp(np.mean(np.log(fft_safe))) / np.mean(fft_safe)
                    )
                    voice_band = (freqs >= 85) & (freqs <= 3400)
                    features["voice_band_ratio"] = float(
                        np.sum(fft_mag[voice_band]) / np.sum(fft_mag)
                    )

            # Zero crossing rate (roughness proxy)
            signs = np.sign(all_samples)
            features["zcr"] = float(np.sum(np.abs(np.diff(signs))) / (2.0 * len(all_samples)))

        except Exception as e:
            print(f"[BG Detector] Feature extraction error: {e}")
            features["energy"] = 500.0  # neutral fallback

        return features

    def is_background_only(self) -> bool:
        """Check if recent history is all background (not worth processing)."""
        with self._lock:
            if len(self._history) < 3:
                return False
            recent = list(self._history)[-5:]
            bg_count = sum(1 for r in recent if r["classification"] == SpeakerContext.BACKGROUND)
            return bg_count >= 4

    def get_recent_stats(self) -> dict:
        with self._lock:
            if not self._history:
                return {}
            recent = list(self._history)
            direct = [r for r in recent if r["classification"] == SpeakerContext.DIRECT]
            return {
                "total": len(recent),
                "direct": len(direct),
                "background": len(recent) - len(direct),
                "direct_pct": len(direct) / len(recent) * 100,
            }


# Global singleton
_detector: Optional[BackgroundSpeakerDetector] = None


def get_bg_detector() -> BackgroundSpeakerDetector:
    global _detector
    if _detector is None:
        _detector = BackgroundSpeakerDetector()
    return _detector
