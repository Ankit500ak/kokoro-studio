import json
import logging
from typing import List, Optional
from sqlalchemy.orm import Session
from ..core.models import GeneratedAudio, VideoAsset, RenderJob
from .types import (
    WordTimestamp, CaptionCue, SelectedClip,
    AudioLayer, VideoSegment, TitleLayer, RenderTimeline
)
from .speech_alignment import SpeechAlignmentService
from .clip_selector import ClipSelector

log = logging.getLogger(__name__)


class TimelineBuilder:
    """Build a complete render timeline from audio, captions, and clips."""

    def __init__(self):
        self.alignment_service = SpeechAlignmentService()
        self.clip_selector = ClipSelector()

    def build_timeline(
        self,
        job: RenderJob,
        audio: GeneratedAudio,
        db: Session,
        title: Optional[str] = None,
        template: Optional[dict] = None,
    ) -> RenderTimeline:
        """Build complete render timeline."""
        duration_ms = (audio.duration or 10) * 1000

        # Get preset and speed from audio record
        preset = getattr(audio, 'preset', 'storytelling') or 'storytelling'
        speed = getattr(audio, 'speed', 1.0) or 1.0

        # Get video folder filter from job (stored as comma-separated string)
        video_folder_raw = getattr(job, 'video_folder', None)
        video_folders = [f.strip() for f in video_folder_raw.split(",") if f.strip()] if video_folder_raw else None

        # 1. Use real captions from DB if available, otherwise fall back to estimation
        captions = []
        if audio.captions_json:
            try:
                sentence_captions = json.loads(audio.captions_json)
                from .caption_manager.sync_service import expand_sentence_captions_to_words
                captions = expand_sentence_captions_to_words(sentence_captions, words_per_cue=3)
                log.info(f"Using {len(captions)} caption cues from real audio timing")
            except (json.JSONDecodeError, Exception) as e:
                log.warning(f"Failed to parse stored captions: {e}, falling back to estimation")
        
        if not captions:
            # Fallback: estimate captions (only if no real captions available)
            audio_path = str(self._get_audio_path(audio.filename))
            from .caption_manager import CaptionManager, CaptionConfig, SyncMethod
            from .caption_manager.models import CaptionTiming
            
            timing = CaptionTiming(
                words_per_cue=3,
                lead_ms=0,
                tail_ms=50,
                min_gap_ms=50,
                silence_threshold_ms=250,
            )
            
            caption_config = CaptionConfig(
                preset=preset,
                timing=timing,
                sync_method=SyncMethod.ESTIMATE,
            )
            
            caption_manager = CaptionManager(caption_config)
            captions, _ = caption_manager.generate_captions(
                audio_path,
                audio.text,
                duration_ms,
                speed=speed,
                emotion=None,
                sync_method=SyncMethod.ESTIMATE,
                validate=False,
            )

        # 2. Select B-roll clips
        clips = self.clip_selector.select_clips(
            db,
            duration_ms,
            seed=job.render_seed or 42,
            folder_filter=video_folders,
        )

        # 4. Build audio layer
        audio_layer = AudioLayer(
            asset_id=audio.id,
            filename=audio.filename,
            duration_ms=duration_ms,
        )

        # 5. Build video segments
        video_segments = [
            VideoSegment(
                asset_id=clip.asset_id,
                filename=clip.filename,
                source_start_ms=clip.source_start_ms,
                source_end_ms=clip.source_end_ms,
                timeline_start_ms=clip.timeline_start_ms,
                timeline_end_ms=clip.timeline_end_ms,
            )
            for clip in clips
        ]

        # 6. Build title layer
        title_layer = None
        if title:
            title_layer = TitleLayer(
                text=title,
                color=template.get("title", {}).get("color", "#FFD400") if template else "#FFD400",
                position=template.get("title", {}).get("position", "top") if template else "top",
            )

        # 7. Use default template if not provided
        if template is None:
            template = {
                "canvas": {"width": 1080, "height": 1920, "fps": 30},
                "title": {"color": "#FFD400", "position": "top", "maxLines": 3, "fontWeight": 800},
                "captions": {"color": "#FFFFFF", "position": "center", "maxWords": 3, "maxLines": 1, "outline": "#000000", "outlineWidth": 6, "font": "Arial Black", "shadow": 2},
                "audio": {"sourceVideoAudio": False},
                "preset": preset,
                "speed": speed,
            }

        return RenderTimeline(
            duration_ms=duration_ms,
            audio=audio_layer,
            video=video_segments,
            title=title_layer,
            captions=captions,
            template=template,
            render_seed=job.render_seed or 42,
        )

    def _get_audio_path(self, filename: str):
        from ..core.config import settings
        return settings.AUDIO_DIR / filename
