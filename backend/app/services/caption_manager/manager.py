"""
Caption Manager
===============

Main orchestrator for the caption management pipeline.

This manager coordinates:
1. Audio-text synchronization (Whisper/Estimate)
2. Timing calculations and adjustments
3. Caption generation and grouping
4. Quality validation
5. Subtitle file rendering
6. Caching for performance
"""

import logging
from typing import List, Optional, Tuple
from .models import (
    CaptionWord,
    CaptionCue,
    CaptionSegment,
    CaptionConfig,
    CaptionFormat,
    CaptionStyle,
    SyncResult,
    SyncMethod,
    ValidationResult,
)
from .sync_service import CaptionSyncService
from .timing_engine import CaptionTimingEngine
from .renderer import CaptionRenderer
from .validator import CaptionValidator
from .cache import CaptionCache

log = logging.getLogger(__name__)


class CaptionManager:
    """
    Main orchestrator for caption management.
    
    Provides a high-level API for generating captions from
    audio and text, with full pipeline control.
    """
    
    def __init__(self, config: Optional[CaptionConfig] = None):
        self.config = config or CaptionConfig()
        
        # Initialize components
        self.sync_service = CaptionSyncService()
        self.timing_engine = CaptionTimingEngine(self.config.timing)
        self.renderer = CaptionRenderer(self.config)
        self.validator = CaptionValidator(self.config)
        self.cache = CaptionCache()
    
    def generate_captions(
        self,
        audio_path: str,
        text: str,
        duration_ms: float,
        speed: float = 1.0,
        emotion: Optional[str] = None,
        sync_method: SyncMethod = SyncMethod.WHISPER,
        validate: bool = True,
    ) -> Tuple[List[CaptionCue], ValidationResult]:
        """
        Generate captions from audio and text.
        
        This is the main entry point for caption generation.
        
        Args:
            audio_path: Path to audio file
            text: Original text
            duration_ms: Audio duration in milliseconds
            speed: Speech speed multiplier
            emotion: Detected emotion for timing adjustments
            sync_method: Method for audio-text synchronization
            validate: Whether to validate the result
            
        Returns:
            Tuple of (cues, validation_result)
        """
        log.info(f"Generating captions for {audio_path}")
        
        # Check cache first
        cached_cues = self.cache.get(audio_path, text)
        if cached_cues:
            log.info("Using cached captions")
            if validate:
                result = self.validator.validate(cached_cues)
                return cached_cues, result
            return cached_cues, ValidationResult(is_valid=True)
        
        # Step 1: Sync audio with text
        sync_result = self.sync_service.sync(
            audio_path,
            text,
            duration_ms,
            sync_method,
        )
        log.info(
            f"Sync complete: {sync_result.word_count} words, "
            f"confidence={sync_result.avg_confidence:.2f}"
        )
        
        # Step 2: Process words into caption cues
        cues = self.timing_engine.process_words(
            sync_result.words,
            speed,
            emotion,
        )
        log.info(f"Generated {len(cues)} caption cues")
        
        # Step 3: Validate if requested
        validation_result = ValidationResult(is_valid=True)
        if validate:
            validation_result = self.validator.validate(cues)
            if not validation_result.is_valid:
                log.warning(
                    f"Caption validation failed: "
                    f"{len(validation_result.errors)} errors"
                )
        
        # Step 4: Cache the result
        self.cache.set(audio_path, text, cues)
        
        return cues, validation_result
    
    def render_captions(
        self,
        cues: List[CaptionCue],
        output_path: str,
        format: Optional[CaptionFormat] = None,
        video_width: int = 1080,
        video_height: int = 1920,
    ):
        """
        Render captions to a subtitle file.
        
        Args:
            cues: List of caption cues
            output_path: Output file path
            format: Output format (ASS, SRT, JSON)
            video_width: Video width for resolution
            video_height: Video height for resolution
        """
        self.renderer.render_to_file(
            cues,
            output_path,
            format,
            video_width,
            video_height,
        )
    
    def get_caption_text(
        self,
        cues: List[CaptionCue],
        format: Optional[CaptionFormat] = None,
        video_width: int = 1080,
        video_height: int = 1920,
    ) -> str:
        """
        Get caption text without writing to file.
        
        Args:
            cues: List of caption cues
            format: Output format
            video_width: Video width
            video_height: Video height
            
        Returns:
            Caption content as string
        """
        return self.renderer.render(
            cues,
            format,
            video_width,
            video_height,
        )
    
    def validate_captions(self, cues: List[CaptionCue]) -> ValidationResult:
        """
        Validate caption quality.
        
        Args:
            cues: List of caption cues
            
        Returns:
            Validation result
        """
        return self.validator.validate(cues)
    
    def get_cache_stats(self) -> dict:
        """Get cache statistics."""
        return self.cache.get_stats()
    
    def clear_cache(self):
        """Clear the caption cache."""
        self.cache.clear()


def create_caption_manager(
    preset: str = "storytelling",
    words_per_cue: int = 3,
    sync_method: str = "whisper",
) -> CaptionManager:
    """
    Factory function to create a CaptionManager with custom settings.
    
    Args:
        preset: Caption preset (storytelling, horror, romantic, etc.)
        words_per_cue: Maximum words per caption
        sync_method: Synchronization method (whisper, estimate, hybrid)
        
    Returns:
        Configured CaptionManager instance
    """
    from .models import CaptionTiming
    
    timing = CaptionTiming(
        words_per_cue=words_per_cue,
        lead_ms=0,
        tail_ms=50,
        min_gap_ms=50,
        silence_threshold_ms=250,
    )
    
    config = CaptionConfig(
        preset=preset,
        timing=timing,
        sync_method=SyncMethod(sync_method),
    )
    
    return CaptionManager(config)
