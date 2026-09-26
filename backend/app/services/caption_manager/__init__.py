"""
Deep Level Caption Management Architecture
==========================================

This module provides a comprehensive caption management system with:

1. CaptionManager - Main orchestrator for caption pipeline
2. CaptionTimingEngine - Precise word-level timing synchronization
3. CaptionRenderer - ASS/SRT subtitle file generation
4. CaptionSyncService - Audio-text alignment using Whisper
5. CaptionValidator - Quality checks and validation
6. CaptionCache - Caching for processed captions

Architecture Flow:
    Audio + Text → SyncService → TimingEngine → Validator → Renderer → Output
    
Components:
    - CaptionManager: Orchestrates the entire pipeline
    - CaptionTimingEngine: Handles timing calculations and adjustments
    - CaptionRenderer: Generates ASS/SRT subtitle files
    - CaptionSyncService: Uses Whisper for accurate word timestamps
    - CaptionValidator: Validates caption quality and timing
    - CaptionCache: Caches processed captions for performance
"""

from .manager import CaptionManager
from .timing_engine import CaptionTimingEngine
from .renderer import CaptionRenderer
from .sync_service import CaptionSyncService
from .validator import CaptionValidator
from .cache import CaptionCache
from .models import (
    CaptionCue,
    CaptionWord,
    CaptionSegment,
    CaptionTiming,
    CaptionConfig,
    CaptionFormat,
    CaptionStyle,
    SyncResult,
    SyncMethod,
)

__all__ = [
    "CaptionManager",
    "CaptionTimingEngine",
    "CaptionRenderer",
    "CaptionSyncService",
    "CaptionValidator",
    "CaptionCache",
    "CaptionCue",
    "CaptionWord",
    "CaptionSegment",
    "CaptionTiming",
    "CaptionConfig",
    "CaptionFormat",
    "CaptionStyle",
    "SyncResult",
    "SyncMethod",
]
