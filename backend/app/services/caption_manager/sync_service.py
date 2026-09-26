"""
Caption Sync Service
====================

Audio-text alignment service using Whisper for accurate word timestamps.

This service handles:
1. Whisper-based speech recognition with word timestamps
2. Fallback estimation when Whisper is unavailable
3. Confidence scoring for aligned words
4. Speaker diarization (optional)
"""

import os
import subprocess
import json
import re
import logging
from typing import List, Optional, Tuple
from .models import (
    CaptionWord,
    SyncResult,
    SyncMethod,
)

log = logging.getLogger(__name__)


class CaptionSyncService:
    """
    Service for synchronizing audio with text.
    
    Uses Whisper for accurate word-level timestamps when available,
    falls back to estimation algorithms otherwise.
    """
    
    # Whisper configuration
    WHISPER_MODEL = "base"
    WHISPER_LANGUAGE = "en"
    
    def __init__(self):
        self._whisper_available = None
    
    def sync(
        self,
        audio_path: str,
        text: str,
        duration_ms: float,
        method: SyncMethod = SyncMethod.WHISPER,
    ) -> SyncResult:
        """
        Synchronize audio with text to get word timestamps.
        
        Args:
            audio_path: Path to audio file
            text: Original text
            duration_ms: Audio duration in milliseconds
            method: Synchronization method to use
            
        Returns:
            SyncResult with word timestamps and metadata
        """
        if method == SyncMethod.WHISPER and self._check_whisper():
            return self._sync_with_whisper(audio_path, text, duration_ms)
        elif method == SyncMethod.HYBRID:
            return self._sync_hybrid(audio_path, text, duration_ms)
        else:
            return self._sync_estimate(text, duration_ms)
    
    def _check_whisper(self) -> bool:
        """Check if Whisper is available."""
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
    
    def _sync_with_whisper(
        self,
        audio_path: str,
        text: str,
        duration_ms: float,
    ) -> SyncResult:
        """
        Use Whisper for accurate word-level timestamps.
        
        This provides the most accurate alignment by actually
        processing the audio file with Whisper's speech recognition.
        """
        json_path = None
        try:
            # Run Whisper with word timestamps
            cmd = [
                "whisper",
                audio_path,
                "--model", self.WHISPER_MODEL,
                "--language", self.WHISPER_LANGUAGE,
                "--output_format", "json",
                "--word_timestamps", "True",
                "--output_dir", os.path.dirname(audio_path)
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode != 0:
                log.warning(f"Whisper failed: {result.stderr[:500]}")
                return self._sync_estimate(text, duration_ms)
            
            # Parse Whisper output
            json_path = os.path.splitext(audio_path)[0] + ".json"
            if not os.path.exists(json_path):
                log.warning("Whisper output file not found")
                return self._sync_estimate(text, duration_ms)
            
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Extract word timestamps
            words = []
            for segment in data.get("segments", []):
                for word_info in segment.get("words", []):
                    word_text = word_info["word"].strip()
                    if word_text:
                        words.append(CaptionWord(
                            text=word_text,
                            start_ms=word_info["start"] * 1000,
                            end_ms=word_info["end"] * 1000,
                            confidence=word_info.get("probability", 0.9),
                        ))
            
            if not words:
                log.warning("No words extracted from Whisper")
                return self._sync_estimate(text, duration_ms)
            
            # Calculate overall confidence
            avg_confidence = sum(w.confidence for w in words) / len(words)
            
            return SyncResult(
                words=words,
                method=SyncMethod.WHISPER,
                confidence=avg_confidence,
                duration_ms=duration_ms,
                word_count=len(words),
                metadata={"whisper_model": self.WHISPER_MODEL},
            )
            
        except (subprocess.TimeoutExpired, Exception) as e:
            log.warning(f"Whisper alignment failed: {e}")
            return self._sync_estimate(text, duration_ms)
        finally:
            # Clean up Whisper output file
            if json_path and os.path.exists(json_path):
                try:
                    os.remove(json_path)
                except OSError:
                    pass
    
    def _sync_hybrid(
        self,
        audio_path: str,
        text: str,
        duration_ms: float,
    ) -> SyncResult:
        """
        Hybrid sync: Try Whisper first, fall back to estimation.
        
        Uses Whisper when available for accuracy, but can also
        combine estimation for reliability.
        """
        if self._check_whisper():
            whisper_result = self._sync_with_whisper(audio_path, text, duration_ms)
            if whisper_result.method == SyncMethod.WHISPER:
                return whisper_result
        
        return self._sync_estimate(text, duration_ms)
    
    def _sync_estimate(
        self,
        text: str,
        duration_ms: float,
    ) -> SyncResult:
        """
        Estimate word timestamps based on text analysis.
        
        This is a fallback when Whisper is not available.
        Uses syllable counting and punctuation analysis.
        """
        # Clean text
        clean_text = text.replace('\\n', ' ').replace('\\b', ' ').replace('\\t', ' ')
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        
        # Extract words
        words = re.findall(r'\b\w+\b|[.!?;,:\-—]+', clean_text)
        if not words:
            return SyncResult(
                words=[],
                method=SyncMethod.ESTIMATE,
                confidence=0.0,
                duration_ms=duration_ms,
                word_count=0,
            )
        
        # Calculate word weights
        weights = []
        for word in words:
            syl_count = self._count_syllables(word)
            weight = max(syl_count, 1) * (1.0 + 0.1 * min(len(word), 5))
            weights.append(weight)
        
        total_weight = sum(weights)
        if total_weight == 0:
            total_weight = len(words)
        
        ms_per_unit = duration_ms / total_weight
        
        # Generate timestamps
        timestamps = []
        current_ms = 0.0
        
        for i, word in enumerate(words):
            # Skip standalone punctuation
            if re.match(r'^[.!?;,:\-—]+$', word):
                continue
            
            weight = weights[i]
            word_duration = weight * ms_per_unit
            word_duration = max(50, min(600, word_duration))
            
            end_ms = min(current_ms + word_duration, duration_ms)
            
            timestamps.append(CaptionWord(
                text=word,
                start_ms=current_ms,
                end_ms=end_ms,
                confidence=0.7,  # Lower confidence for estimated timing
            ))
            
            current_ms = end_ms
            
            # Add gap
            gap = ms_per_unit * 0.12
            
            # Add pause for punctuation
            punct_pauses = {
                '.': ms_per_unit * 2.0,
                '!': ms_per_unit * 2.2,
                '?': ms_per_unit * 2.0,
                ',': ms_per_unit * 0.7,
                ';': ms_per_unit * 0.8,
                ':': ms_per_unit * 0.5,
            }
            
            for punct, p_dur in punct_pauses.items():
                if word.endswith(punct):
                    gap += p_dur
                    break
            
            if i < len(words) - 1:
                current_ms += gap
        
        # Normalize timestamps to fit within duration
        if timestamps and timestamps[-1].end_ms > duration_ms * 0.98:
            scale = (duration_ms * 0.98) / timestamps[-1].end_ms
            for ts in timestamps:
                ts.start_ms *= scale
                ts.end_ms *= scale
        
        avg_confidence = sum(w.confidence for w in timestamps) / len(timestamps) if timestamps else 0
        
        return SyncResult(
            words=timestamps,
            method=SyncMethod.ESTIMATE,
            confidence=avg_confidence,
            duration_ms=duration_ms,
            word_count=len(timestamps),
        )
    
    def _count_syllables(self, word: str) -> int:
        """Estimate syllable count for a word."""
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
        
        return max(1, count)


def expand_sentence_captions_to_words(
    sentence_captions: list[dict],
    words_per_cue: int = 3,
) -> list:
    """
    Expand sentence-level captions to word-level CaptionCue objects.
    
    Takes the sentence-level captions from kokoro_service (which have accurate
    timing based on actual audio tensor lengths) and distributes words within
    each sentence proportionally.
    
    Args:
        sentence_captions: List of dicts with 'text', 'start_time_ms', 'duration_ms'
        words_per_cue: Max words per caption cue (default 3 for Shorts)
        
    Returns:
        List of CaptionCue objects with word-level timing
    """
    from .models import CaptionCue, CaptionWord
    
    cues = []
    cue_id = 0
    
    for sent_cap in sentence_captions:
        text = sent_cap.get('text', '').strip()
        start_ms = sent_cap.get('start_time_ms', 0)
        duration_ms = sent_cap.get('duration_ms', 0)
        
        if not text or duration_ms <= 0:
            continue
        
        # Split sentence into words
        words = text.split()
        if not words:
            continue
        
        # Calculate weight for each word (syllables + length)
        weights = []
        for word in words:
            syl_count = _count_syllables_simple(word)
            weight = max(syl_count, 1) * (1.0 + 0.08 * min(len(word), 6))
            weights.append(weight)
        
        total_weight = sum(weights)
        if total_weight == 0:
            total_weight = len(words)
        
        ms_per_unit = duration_ms / total_weight
        
        # Generate word-level timestamps within this sentence
        word_timestamps = []
        current_ms = start_ms
        
        for i, word in enumerate(words):
            weight = weights[i]
            word_duration = weight * ms_per_unit
            word_duration = max(40, min(600, word_duration))
            
            end_ms = min(current_ms + word_duration, start_ms + duration_ms)
            
            word_timestamps.append(CaptionWord(
                text=word,
                start_ms=current_ms,
                end_ms=end_ms,
                confidence=1.0,
            ))
            
            current_ms = end_ms
        
        # Group words into cues (words_per_cue words max)
        for i in range(0, len(word_timestamps), words_per_cue):
            chunk = word_timestamps[i:i + words_per_cue]
            if not chunk:
                continue
            
            # STRICT: max 3 words
            chunk = chunk[:3]
            
            cue_start = chunk[0].start_ms
            cue_end = chunk[-1].end_ms
            
            cues.append(CaptionCue(
                id=f"cue_{cue_id}",
                words=chunk,
                start_ms=cue_start,
                end_ms=cue_end,
            ))
            cue_id += 1
    
    # DEDUPLICATE: remove cues with same text within 50ms
    unique_cues = []
    for cue in cues:
        if not unique_cues:
            unique_cues.append(cue)
            continue
        prev = unique_cues[-1]
        curr_text = " ".join(w.text for w in cue.words)
        prev_text = " ".join(w.text for w in prev.words)
        time_diff = abs(cue.start_ms - prev.start_ms)
        if curr_text != prev_text or time_diff > 50:
            unique_cues.append(cue)
    
    # ENSURE NO OVERLAPS: add small gap between sequential cues
    for i in range(1, len(unique_cues)):
        prev = unique_cues[i - 1]
        curr = unique_cues[i]
        if curr.start_ms < prev.end_ms:
            curr.start_ms = prev.end_ms + 30  # 30ms gap
        if curr.end_ms <= curr.start_ms:
            curr.end_ms = curr.start_ms + 100
    
    return unique_cues


def _count_syllables_simple(word: str) -> int:
    """Fast syllable count estimate."""
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
    
    return max(1, count)
