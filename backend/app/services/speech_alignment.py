import os
import subprocess
import json
import re
import logging
from typing import List
from .types import WordTimestamp

log = logging.getLogger(__name__)


class SpeechAlignmentService:
    """Provides word-level timestamps from audio files."""

    def __init__(self):
        self._whisper_available = None

    def _check_whisper(self) -> bool:
        if self._whisper_available is None:
            try:
                result = subprocess.run(
                    ["whisper", "--help"],
                    capture_output=True,
                    timeout=5
                )
                self._whisper_available = result.returncode == 0
            except (FileNotFoundError, subprocess.TimeoutExpired):
                self._whisper_available = False
        return self._whisper_available

    def align(self, audio_path: str, text: str, duration_ms: float) -> List[WordTimestamp]:
        if self._check_whisper():
            return self._align_with_whisper(audio_path)
        return self._align_estimate(text, duration_ms)

    def _align_with_whisper(self, audio_path: str) -> List[WordTimestamp]:
        json_path = None
        try:
            cmd = [
                "whisper",
                audio_path,
                "--model", "base",
                "--output_format", "json",
                "--word_timestamps", "True",
                "--output_dir", os.path.dirname(audio_path)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

            if result.returncode == 0:
                json_path = os.path.splitext(audio_path)[0] + ".json"
                if os.path.exists(json_path):
                    with open(json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    words = []
                    for segment in data.get("segments", []):
                        for word_info in segment.get("words", []):
                            words.append(WordTimestamp(
                                text=word_info["word"].strip(),
                                start_ms=word_info["start"] * 1000,
                                end_ms=word_info["end"] * 1000,
                                confidence=1.0
                            ))
                    return words
        except (subprocess.TimeoutExpired, Exception) as e:
            log.warning(f"Whisper alignment failed: {e}")
        finally:
            if json_path and os.path.exists(json_path):
                try:
                    os.remove(json_path)
                except OSError:
                    pass
        return []

    def _align_estimate(self, text: str, duration_ms: float) -> List[WordTimestamp]:
        text = text.replace('\\n', ' ').replace('\\b', ' ').replace('\\t', ' ')
        text = re.sub(r'\s+', ' ', text).strip()
        
        words = re.findall(r'\b\w+\b|[.!?;,:\-—]+', text)
        if not words:
            return []

        # Calculate character and syllable weights
        char_weights = []
        syl_weights = []
        for w in words:
            syl = self._count_syllables(w)
            char_weight = len(w)
            # Short words spoken faster, long words slower
            weight = max(syl, 1) * (1.0 + 0.1 * min(len(w), 5))
            syl_weights.append(max(syl, 1))
            char_weights.append(weight)

        total_weight = sum(char_weights)
        if total_weight == 0:
            total_weight = len(words)

        # Base time per unit weight
        base_ms_per_unit = duration_ms / total_weight

        # Punctuation pauses (in ms)
        punct_pauses = {
            '.': base_ms_per_unit * 2.0,
            '!': base_ms_per_unit * 2.2,
            '?': base_ms_per_unit * 2.0,
            ',': base_ms_per_unit * 0.7,
            ';': base_ms_per_unit * 0.8,
            ':': base_ms_per_unit * 0.5,
            '—': base_ms_per_unit * 1.0,
            '-': base_ms_per_unit * 0.4,
        }

        timestamps = []
        current_ms = 0.0

        for i, word in enumerate(words):
            # Skip standalone punctuation tokens
            if re.match(r'^[.!?;,:\-—]+$', word):
                continue

            weight = char_weights[i] if i < len(char_weights) else 1.0
            word_duration = weight * base_ms_per_unit

            # Clamp word duration
            word_duration = max(word_duration, 60)
            word_duration = min(word_duration, 600)

            end_ms = min(current_ms + word_duration, duration_ms)

            timestamps.append(WordTimestamp(
                text=word,
                start_ms=current_ms,
                end_ms=end_ms,
            ))

            current_ms = end_ms

            # Add gap after word
            gap = base_ms_per_unit * 0.12

            # Add pause for punctuation
            for punct, p_dur in punct_pauses.items():
                if word.endswith(punct):
                    gap += p_dur
                    break

            if i < len(words) - 1:
                current_ms += gap

            if current_ms >= duration_ms:
                break

        # Normalize timestamps to fit within duration
        if timestamps and timestamps[-1].end_ms > duration_ms * 0.98:
            scale = (duration_ms * 0.98) / timestamps[-1].end_ms
            for ts in timestamps:
                ts.start_ms *= scale
                ts.end_ms *= scale

        return timestamps

    def _count_syllables(self, word: str) -> int:
        word = word.lower().strip()
        if len(word) <= 2:
            return 1

        vowels = "aeiouy"
        count = 0
        prev_vowel = False

        for char in word:
            is_vowel = char in vowels
            if is_vowel and not prev_vowel:
                count += 1
            prev_vowel = is_vowel

        if word.endswith('e') and count > 1:
            count -= 1

        return max(count, 1)
