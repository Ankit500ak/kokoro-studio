"""
Caption Validator
=================

Quality checks and validation for captions.

This validator checks:
1. Timing accuracy and consistency
2. Caption length and readability
3. Overlap detection
4. Gap consistency
5. Confidence thresholds
"""

import logging
from typing import List
from .models import (
    CaptionCue,
    CaptionConfig,
    ValidationResult,
)

log = logging.getLogger(__name__)


class CaptionValidator:
    """
    Validator for caption quality assurance.
    
    Performs comprehensive checks on caption timing,
    content, and overall quality.
    """
    
    # Validation thresholds
    MIN_CUE_DURATION_MS = 100
    MAX_CUE_DURATION_MS = 5000
    MIN_GAP_MS = 30
    MAX_GAP_MS = 3000
    MIN_CONFIDENCE = 0.5
    MAX_WORDS_PER_CUE = 5
    MIN_WORDS_PER_CUE = 1
    
    def __init__(self, config: CaptionConfig = None):
        self.config = config or CaptionConfig()
    
    def validate(self, cues: List[CaptionCue]) -> ValidationResult:
        """
        Validate caption cues for quality issues.
        
        Args:
            cues: List of caption cues to validate
            
        Returns:
            ValidationResult with errors and warnings
        """
        result = ValidationResult(is_valid=True)
        
        if not cues:
            result.add_warning("No captions to validate")
            return result
        
        # Run all validation checks
        self._check_timing_accuracy(cues, result)
        self._check_overlaps(cues, result)
        self._check_gaps(cues, result)
        self._check_caption_length(cues, result)
        self._check_confidence(cues, result)
        self._check_word_count(cues, result)
        self._check_readability(cues, result)
        
        # Calculate statistics
        result.stats = self._calculate_stats(cues)
        
        return result
    
    def _check_timing_accuracy(self, cues: List[CaptionCue], result: ValidationResult):
        """Check for timing accuracy issues."""
        for i, cue in enumerate(cues):
            # Check for negative duration
            if cue.duration_ms < 0:
                result.add_error(f"Cue {i}: Negative duration ({cue.duration_ms}ms)")
            
            # Check for too short duration
            if cue.duration_ms < self.MIN_CUE_DURATION_MS:
                result.add_warning(
                    f"Cue {i}: Very short duration ({cue.duration_ms}ms)"
                )
            
            # Check for too long duration
            if cue.duration_ms > self.MAX_CUE_DURATION_MS:
                result.add_warning(
                    f"Cue {i}: Very long duration ({cue.duration_ms}ms)"
                )
            
            # Check for invalid timing
            if cue.start_ms < 0:
                result.add_error(f"Cue {i}: Negative start time ({cue.start_ms}ms)")
            
            if cue.end_ms < cue.start_ms:
                result.add_error(
                    f"Cue {i}: End time ({cue.end_ms}ms) before start time ({cue.start_ms}ms)"
                )
    
    def _check_overlaps(self, cues: List[CaptionCue], result: ValidationResult):
        """Check for overlapping captions."""
        for i in range(1, len(cues)):
            prev = cues[i - 1]
            curr = cues[i]
            
            if curr.start_ms < prev.end_ms:
                overlap = prev.end_ms - curr.start_ms
                result.add_error(
                    f"Cues {i-1} and {i} overlap by {overlap}ms"
                )
    
    def _check_gaps(self, cues: List[CaptionCue], result: ValidationResult):
        """Check for gap consistency."""
        for i in range(1, len(cues)):
            prev = cues[i - 1]
            curr = cues[i]
            
            gap = curr.start_ms - prev.end_ms
            
            # Check for negative gap (overlap)
            if gap < 0:
                continue  # Already caught in overlap check
            
            # Check for very small gap
            if gap < self.MIN_GAP_MS and gap > 0:
                result.add_warning(
                    f"Cues {i-1} and {i}: Very small gap ({gap}ms)"
                )
            
            # Check for very large gap
            if gap > self.MAX_GAP_MS:
                result.add_warning(
                    f"Cues {i-1} and {i}: Very large gap ({gap}ms)"
                )
    
    def _check_caption_length(self, cues: List[CaptionCue], result: ValidationResult):
        """Check caption text length."""
        for i, cue in enumerate(cues):
            text = cue.text
            
            # Check for empty caption
            if not text.strip():
                result.add_error(f"Cue {i}: Empty caption text")
            
            # Check for very long text
            if len(text) > 100:
                result.add_warning(
                    f"Cue {i}: Very long text ({len(text)} chars)"
                )
    
    def _check_confidence(self, cues: List[CaptionCue], result: ValidationResult):
        """Check confidence scores."""
        for i, cue in enumerate(cues):
            if cue.confidence < self.MIN_CONFIDENCE:
                result.add_warning(
                    f"Cue {i}: Low confidence ({cue.confidence:.2f})"
                )
    
    def _check_word_count(self, cues: List[CaptionCue], result: ValidationResult):
        """Check word count per caption."""
        for i, cue in enumerate(cues):
            word_count = cue.word_count
            
            if word_count < self.MIN_WORDS_PER_CUE:
                result.add_warning(
                    f"Cue {i}: Too few words ({word_count})"
                )
            
            if word_count > self.MAX_WORDS_PER_CUE:
                result.add_warning(
                    f"Cue {i}: Too many words ({word_count})"
                )
    
    def _check_readability(self, cues: List[CaptionCue], result: ValidationResult):
        """Check caption readability."""
        for i, cue in enumerate(cues):
            # Check for ALL CAPS (can be hard to read)
            text = cue.text
            if text.isupper() and len(text) > 10:
                result.add_warning(
                    f"Cue {i}: Text is ALL CAPS"
                )
            
            # Check for special characters
            special_chars = set(text) - set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,!?;:\'"-')
            if special_chars:
                result.add_warning(
                    f"Cue {i}: Contains special characters: {''.join(special_chars)}"
                )
    
    def _calculate_stats(self, cues: List[CaptionCue]) -> dict:
        """Calculate statistics for the captions."""
        if not cues:
            return {}
        
        durations = [cue.duration_ms for cue in cues]
        word_counts = [cue.word_count for cue in cues]
        confidences = [cue.confidence for cue in cues]
        
        # Calculate gaps
        gaps = []
        for i in range(1, len(cues)):
            gap = cues[i].start_ms - cues[i-1].end_ms
            gaps.append(max(0, gap))
        
        return {
            "total_cues": len(cues),
            "total_words": sum(word_counts),
            "avg_duration_ms": sum(durations) / len(durations),
            "min_duration_ms": min(durations),
            "max_duration_ms": max(durations),
            "avg_words_per_cue": sum(word_counts) / len(word_counts),
            "avg_confidence": sum(confidences) / len(confidences),
            "avg_gap_ms": sum(gaps) / len(gaps) if gaps else 0,
            "total_duration_ms": cues[-1].end_ms - cues[0].start_ms if cues else 0,
        }
