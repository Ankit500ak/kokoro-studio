from dataclasses import dataclass
from typing import List, Optional


@dataclass
class WordTimestamp:
    text: str
    start_ms: float
    end_ms: float
    confidence: float = 1.0


@dataclass
class CaptionWord:
    text: str
    start_ms: float
    end_ms: float
    is_highlighted: bool = False


@dataclass
class CaptionCue:
    start_ms: float
    end_ms: float
    words: List[CaptionWord]


@dataclass
class SelectedClip:
    asset_id: str
    filename: str
    source_start_ms: float
    source_end_ms: float
    timeline_start_ms: float
    timeline_end_ms: float


@dataclass
class AudioLayer:
    asset_id: str
    filename: str
    duration_ms: float


@dataclass
class VideoSegment:
    asset_id: str
    filename: str
    source_start_ms: float
    source_end_ms: float
    timeline_start_ms: float
    timeline_end_ms: float


@dataclass
class TitleLayer:
    text: str
    color: str = "#FFD400"
    position: str = "top"
    max_lines: int = 3
    font_weight: int = 800


@dataclass
class RenderTimeline:
    duration_ms: float
    audio: AudioLayer
    video: List[VideoSegment]
    title: Optional[TitleLayer]
    captions: List[CaptionCue]
    template: dict
    render_seed: int
