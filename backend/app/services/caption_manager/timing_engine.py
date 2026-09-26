"""
Caption Timing Engine
=====================

Precise word-level timing synchronization for captions.

This engine handles:
1. Word-level timing calculations
2. Silence detection and pause handling
3. Speed-based timing adjustments
4. Emotion-based timing variations
5. Caption grouping and splitting
"""

import re
import logging
from typing import List, Optional, Tuple
from .models import (
    CaptionWord,
    CaptionCue,
    CaptionTiming,
    CaptionStyle,
)

log = logging.getLogger(__name__)


class CaptionTimingEngine:
    """
    Engine for precise caption timing calculations.
    
    Responsibilities:
    - Calculate precise word timings from audio alignment
    - Detect silence gaps and split captions accordingly
    - Group words into optimal caption cues
    - Apply speed and emotion-based timing adjustments
    - Ensure smooth transitions between captions
    """
    
    # Timing constants
    MIN_WORD_DURATION_MS = 50
    MAX_WORD_DURATION_MS = 800
    DEFAULT_SPEED = 1.0
    
    # Emotion speed multipliers
    EMOTION_SPEED = {
        'fear': 0.75,
        'sadness': 0.78,
        'romance': 0.80,
        'tension': 0.72,
        'wisdom': 0.85,
        'neutral': 1.0,
        'suspense': 0.82,
        'anger': 1.18,
        'joy': 1.15,
        'excitement': 1.22,
        'humor': 1.12,
        'surprise': 1.10,
    }
    
    def __init__(self, timing: Optional[CaptionTiming] = None):
        self.timing = timing or CaptionTiming()
    
    def process_words(
        self,
        words: List[CaptionWord],
        speed: float = 1.0,
        emotion: Optional[str] = None,
    ) -> List[CaptionCue]:
        """
        Process word timestamps into caption cues.
        
        Args:
            words: List of words with timestamps
            speed: Speech speed multiplier
            emotion: Detected emotion for timing adjustments
            
        Returns:
            List of caption cues with precise timing
        """
        if not words:
            return []
        
        # Step 1: Apply speed adjustments to words
        adjusted_words = self._apply_speed_adjustments(words, speed, emotion)
        
        # Step 2: Detect silence gaps and split into phrases
        phrases = self._detect_silence_gaps(adjusted_words)
        
        # Step 3: Group words within phrases into caption cues
        cues = []
        for phrase in phrases:
            phrase_cues = self._group_phrase_to_cues(phrase)
            cues.extend(phrase_cues)
        
        # Step 4: Apply timing adjustments
        cues = self._apply_timing_adjustments(cues)
        
        # Step 5: Ensure smooth transitions
        cues = self._ensure_smooth_transitions(cues)
        
        return cues
    
    def _apply_speed_adjustments(
        self,
        words: List[CaptionWord],
        speed: float,
        emotion: Optional[str],
    ) -> List[CaptionWord]:
        """Speed adjustments are not needed here — Whisper timestamps already
        come from the actual audio which was generated at the requested speed."""
        return words
    
    def _detect_silence_gaps(
        self,
        words: List[CaptionWord],
    ) -> List[List[CaptionWord]]:
        """
        Detect silence gaps and split words into phrases.
        
        A silence gap is defined as a gap between words that exceeds
        the silence threshold. This is used to split captions at
        natural pause points.
        """
        if not words:
            return []
        
        phrases = []
        current_phrase = [words[0]]
        
        for i in range(1, len(words)):
            gap = words[i].start_ms - words[i-1].end_ms
            
            if gap >= self.timing.silence_threshold_ms:
                # Large gap detected - start new phrase
                if current_phrase:
                    phrases.append(current_phrase)
                current_phrase = [words[i]]
            else:
                current_phrase.append(words[i])
        
        if current_phrase:
            phrases.append(current_phrase)
        
        return phrases
    
    def _group_phrase_to_cues(
        self,
        phrase: List[CaptionWord],
    ) -> List[CaptionCue]:
        """
        Group words within a phrase into caption cues.
        
        Groups words based on:
        - Maximum words per cue
        - Natural sentence boundaries (punctuation)
        - Clause boundaries
        """
        if not phrase:
            return []
        
        cues = []
        current_group = []
        
        for word in phrase:
            current_group.append(word)
            
            # Check if we should start a new cue
            should_split = (
                len(current_group) >= self.timing.words_per_cue or
                self._ends_sentence(word.text) or
                self._ends_clause(word.text)
            )
            
            if should_split and current_group:
                cue = self._create_cue(current_group)
                cues.append(cue)
                current_group = []
        
        # Don't forget remaining words
        if current_group:
            cue = self._create_cue(current_group)
            cues.append(cue)
        
        return cues
    
    def _ends_sentence(self, text: str) -> bool:
        """Check if text ends with sentence-ending punctuation."""
        return bool(re.search(r'[.!?…]$', text.strip()))
    
    def _ends_clause(self, text: str) -> bool:
        """Check if text ends with clause-ending punctuation."""
        return bool(re.search(r'[,;:]$', text.strip()))
    
    def _create_cue(self, words: List[CaptionWord]) -> CaptionCue:
        """Create a caption cue from a group of words."""
        if not words:
            raise ValueError("Cannot create cue from empty words")
        
        # Generate unique ID
        cue_id = f"cue_{words[0].start_ms}_{words[-1].end_ms}"
        
        # Calculate timing
        start_ms = words[0].start_ms
        end_ms = words[-1].end_ms
        
        # Apply lead and tail
        start_ms = max(0, start_ms - self.timing.lead_ms)
        end_ms = end_ms + self.timing.tail_ms
        
        return CaptionCue(
            id=cue_id,
            words=words,
            start_ms=start_ms,
            end_ms=end_ms,
        )
    
    def _apply_timing_adjustments(self, cues: List[CaptionCue]) -> List[CaptionCue]:
        """Apply final timing adjustments to cues."""
        adjusted_cues = []
        
        for cue in cues:
            # Ensure minimum duration
            if cue.duration_ms < self.timing.min_gap_ms:
                cue.end_ms = cue.start_ms + self.timing.min_gap_ms
            
            # Ensure maximum duration
            if cue.duration_ms > self.timing.max_gap_ms:
                # Split long cues
                split_cues = self._split_long_cue(cue)
                adjusted_cues.extend(split_cues)
            else:
                adjusted_cues.append(cue)
        
        return adjusted_cues
    
    def _split_long_cue(self, cue: CaptionCue) -> List[CaptionCue]:
        """Split a cue that exceeds maximum duration."""
        if cue.word_count <= 1:
            return [cue]
        
        mid = cue.word_count // 2
        words1 = cue.words[:mid]
        words2 = cue.words[mid:]
        
        cue1 = self._create_cue(words1)
        cue2 = self._create_cue(words2)
        
        return [cue1, cue2]
    
    def _ensure_smooth_transitions(self, cues: List[CaptionCue]) -> List[CaptionCue]:
        """Ensure smooth transitions between captions."""
        if len(cues) <= 1:
            return cues
        
        smoothed = [cues[0]]
        
        for i in range(1, len(cues)):
            prev = smoothed[-1]
            curr = cues[i]
            
            # Ensure no overlap
            if curr.start_ms < prev.end_ms:
                curr.start_ms = prev.end_ms
            
            # Ensure minimum gap
            if curr.start_ms < prev.end_ms + self.timing.min_gap_ms:
                curr.start_ms = prev.end_ms + self.timing.min_gap_ms
            
            smoothed.append(curr)
        
        return smoothed
    
    def calculate_word_timing(
        self,
        text: str,
        duration_ms: float,
        start_ms: float = 0.0,
    ) -> List[CaptionWord]:
        """
        Calculate word timing for text without audio alignment.
        
        This is used as a fallback when Whisper is not available.
        """
        words = re.findall(r'\b\w+\b|[.!?;,:\-—]+', text)
        if not words:
            return []
        
        # Calculate word weights based on syllables and length
        weights = []
        for word in words:
            syl_count = self._count_syllables(word)
            weight = max(syl_count, 1) * (1.0 + 0.1 * min(len(word), 5))
            weights.append(weight)
        
        total_weight = sum(weights)
        if total_weight == 0:
            total_weight = len(words)
        
        ms_per_unit = duration_ms / total_weight
        
        timestamps = []
        current_ms = start_ms
        
        for i, word in enumerate(words):
            # Skip standalone punctuation
            if re.match(r'^[.!?;,:\-—]+$', word):
                continue
            
            weight = weights[i]
            word_duration = weight * ms_per_unit
            word_duration = max(self.MIN_WORD_DURATION_MS, min(self.MAX_WORD_DURATION_MS, word_duration))
            
            end_ms = current_ms + word_duration
            
            timestamps.append(CaptionWord(
                text=word,
                start_ms=current_ms,
                end_ms=end_ms,
                confidence=0.8,  # Lower confidence for estimated timing
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
        
        return timestamps
    
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
