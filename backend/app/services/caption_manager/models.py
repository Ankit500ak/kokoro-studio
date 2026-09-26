"""
Caption Management Data Models
==============================

Core data structures for the caption management system.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum


class CaptionFormat(Enum):
    """Supported caption output formats."""
    ASS = "ass"
    SRT = "srt"
    JSON = "json"


class SyncMethod(Enum):
    """Speech synchronization methods."""
    WHISPER = "whisper"
    ESTIMATE = "estimate"
    HYBRID = "hybrid"


class CaptionStyle(Enum):
    """Caption display styles."""
    WORD_BY_WORD = "word_by_word"
    PHRASE = "phrase"
    SENTENCE = "sentence"
    KARAOKE = "karaoke"


@dataclass
class CaptionWord:
    """Individual word with timing information."""
    text: str
    start_ms: float
    end_ms: float
    confidence: float = 1.0
    speaker: Optional[str] = None
    
    @property
    def duration_ms(self) -> float:
        return self.end_ms - self.start_ms
    
    @property
    def center_ms(self) -> float:
        return (self.start_ms + self.end_ms) / 2


@dataclass
class CaptionCue:
    """A group of words displayed together as a caption."""
    id: str
    words: List[CaptionWord]
    start_ms: float
    end_ms: float
    style: CaptionStyle = CaptionStyle.PHRASE
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def duration_ms(self) -> float:
        return self.end_ms - self.start_ms
    
    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)
    
    @property
    def word_count(self) -> int:
        return len(self.words)
    
    @property
    def confidence(self) -> float:
        if not self.words:
            return 0.0
        return sum(w.confidence for w in self.words) / len(self.words)


@dataclass
class CaptionSegment:
    """A segment of captions representing a phrase or sentence."""
    id: str
    cues: List[CaptionCue]
    start_ms: float
    end_ms: float
    text: str
    emotion: Optional[str] = None
    
    @property
    def duration_ms(self) -> float:
        return self.end_ms - self.start_ms
    
    @property
    def cue_count(self) -> int:
        return len(self.cues)


@dataclass
class CaptionTiming:
    """Timing configuration for caption generation."""
    lead_ms: float = 0.0
    tail_ms: float = 50.0
    min_gap_ms: float = 50.0
    max_gap_ms: float = 2000.0
    silence_threshold_ms: float = 250.0
    words_per_cue: int = 3
    speed_multiplier: float = 1.0


@dataclass
class CaptionConfig:
    """Configuration for caption generation."""
    format: CaptionFormat = CaptionFormat.ASS
    style: CaptionStyle = CaptionStyle.PHRASE
    sync_method: SyncMethod = SyncMethod.WHISPER
    timing: CaptionTiming = field(default_factory=CaptionTiming)
    preset: str = "storytelling"
    font_name: str = "Arial Black"
    font_size: int = 72
    primary_color: str = "&H00FFFFFF"
    outline_color: str = "&H00000000"
    outline_width: int = 6
    margin_v: int = 50


@dataclass
class SyncResult:
    """Result of speech synchronization."""
    words: List[CaptionWord]
    method: SyncMethod
    confidence: float
    duration_ms: float
    word_count: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def avg_confidence(self) -> float:
        if not self.words:
            return 0.0
        return sum(w.confidence for w in self.words) / len(self.words)


@dataclass
class ValidationResult:
    """Result of caption validation."""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)
    
    def add_error(self, error: str):
        self.errors.append(error)
        self.is_valid = False
    
    def add_warning(self, warning: str):
        self.warnings.append(warning)


@dataclass
class CaptionCacheEntry:
    """Cached caption data."""
    audio_hash: str
    text: str
    cues: List[CaptionCue]
    segments: List[CaptionSegment]
    created_at: float
    ttl_seconds: int = 3600
