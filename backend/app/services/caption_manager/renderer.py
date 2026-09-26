"""
Caption Renderer
================

Generates subtitle files (ASS/SRT) from caption cues.

This renderer handles:
1. ASS subtitle generation with styling
2. SRT subtitle generation
3. JSON export for custom rendering
4. Style customization per preset
"""

import logging
from typing import List, Optional
from .models import (
    CaptionCue,
    CaptionFormat,
    CaptionStyle,
    CaptionConfig,
)

log = logging.getLogger(__name__)


class CaptionRenderer:
    """
    Renderer for generating subtitle files.
    
    Supports ASS and SRT formats with customizable styling.
    """
    
    # Preset styles
    PRESET_STYLES = {
        "storytelling": {
            "font_size": 82,
            "primary_color": "&H00FFFFFF",   # White
            "secondary_color": "&H0000FFFF", # Yellow highlight
            "outline_color": "&H00000000",   # Black outline
            "outline_width": 6,
            "shadow": 3,
            "margin_v": 60,
        },
        "horror": {
            "font_size": 78,
            "primary_color": "&H00FFFFFF",
            "secondary_color": "&H000055FF", # Orange highlight
            "outline_color": "&H00000000",
            "outline_width": 6,
            "shadow": 3,
            "margin_v": 60,
        },
        "romantic": {
            "font_size": 80,
            "primary_color": "&H00FFFFFF",
            "secondary_color": "&H00FF99FF", # Pink highlight
            "outline_color": "&H00000000",
            "outline_width": 6,
            "shadow": 3,
            "margin_v": 60,
        },
        "documentary": {
            "font_size": 82,
            "primary_color": "&H00FFFFFF",
            "secondary_color": "&H0000FFFF", # Yellow highlight
            "outline_color": "&H00000000",
            "outline_width": 6,
            "shadow": 3,
            "margin_v": 60,
        },
        "news": {
            "font_size": 80,
            "primary_color": "&H00FFFFFF",
            "secondary_color": "&H0000FFFF",
            "outline_color": "&H00000000",
            "outline_width": 6,
            "shadow": 3,
            "margin_v": 60,
        },
        "shorts": {
            "font_size": 84,
            "primary_color": "&H00FFFFFF",
            "secondary_color": "&H0000FFFF", # Yellow highlight
            "outline_color": "&H00000000",
            "outline_width": 7,
            "shadow": 3,
            "margin_v": 70,
        },
    }
    
    def __init__(self, config: Optional[CaptionConfig] = None):
        self.config = config or CaptionConfig()
        self._apply_preset_style()
    
    def _apply_preset_style(self):
        """Apply style from preset configuration."""
        preset_style = self.PRESET_STYLES.get(self.config.preset, {})
        if preset_style:
            self.config.font_size = preset_style.get("font_size", self.config.font_size)
            self.config.primary_color = preset_style.get("primary_color", self.config.primary_color)
            self.config.secondary_color = preset_style.get("secondary_color", getattr(self.config, 'secondary_color', "&H0000FFFF"))
            self.config.outline_color = preset_style.get("outline_color", self.config.outline_color)
            self.config.outline_width = preset_style.get("outline_width", self.config.outline_width)
            self.config.shadow = preset_style.get("shadow", getattr(self.config, 'shadow', 3))
            self.config.margin_v = preset_style.get("margin_v", self.config.margin_v)
    
    def render(
        self,
        cues: List[CaptionCue],
        format: Optional[CaptionFormat] = None,
        video_width: int = 1080,
        video_height: int = 1920,
    ) -> str:
        """
        Render caption cues to subtitle file.
        
        Args:
            cues: List of caption cues
            format: Output format (ASS, SRT, JSON)
            video_width: Video width for resolution
            video_height: Video height for resolution
            
        Returns:
            Subtitle file content as string
        """
        fmt = format or self.config.format
        
        if fmt == CaptionFormat.ASS:
            return self._render_ass(cues, video_width, video_height)
        elif fmt == CaptionFormat.SRT:
            return self._render_srt(cues)
        elif fmt == CaptionFormat.JSON:
            return self._render_json(cues)
        else:
            raise ValueError(f"Unsupported format: {fmt}")
    
    def _render_ass(
        self,
        cues: List[CaptionCue],
        video_width: int,
        video_height: int,
    ) -> str:
        """Render captions in ASS format with karaoke highlighting."""
        play_res_x = video_width
        play_res_y = video_height
        
        # Get secondary color for karaoke highlight
        secondary_color = getattr(self.config, 'secondary_color', "&H0000FFFF")
        shadow = getattr(self.config, 'shadow', 3)
        
        header = f"""[Script Info]
Title: Kokoro Studio Captions
ScriptType: v4.00+
PlayResX: {play_res_x}
PlayResY: {play_res_y}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Black,{self.config.font_size},{self.config.primary_color},{secondary_color},{self.config.outline_color},&H80000000,1,0,0,0,100,100,3,0,1,{self.config.outline_width},{shadow},5,0,0,{self.config.margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        events = []
        seen = set()
        prev_end_ms = 0
        for cue in cues:
            display_words = cue.words[:3]
            if not display_words:
                continue
            
            # DEDUP: skip if same text within 100ms
            text = " ".join(w.text for w in display_words)
            start_ms = cue.start_ms
            end_ms = cue.end_ms
            
            # NO OVERLAP: push start after previous cue ends
            if start_ms < prev_end_ms:
                start_ms = prev_end_ms + 30
            if end_ms <= start_ms:
                end_ms = start_ms + 100
            
            start = self._format_time(start_ms)
            dedup_key = f"{text}_{start}"
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            
            end = self._format_time(end_ms)
            
            # Build word-by-word text with karaoke timing
            word_parts = []
            for word in display_words:
                word_start_ms = word.start_ms - cue.start_ms
                word_end_ms = word.end_ms - cue.start_ms
                word_duration_cs = max(1, int((word_end_ms - word_start_ms) / 10))
                
                # \kf = fill from left to right (karaoke highlight)
                word_parts.append(f"{{\\kf{word_duration_cs}}}{word.text}")
            
            text = " ".join(word_parts)
            events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")
            prev_end_ms = end_ms
        
        return header + "\n".join(events) + "\n"
    
    def _render_srt(self, cues: List[CaptionCue]) -> str:
        """Render captions in SRT format."""
        srt_content = []
        
        for i, cue in enumerate(cues, 1):
            # Only show max 3 words per caption
            display_words = cue.words[:3]
            if not display_words:
                continue
            
            start = self._format_srt_time(cue.start_ms)
            end = self._format_srt_time(cue.end_ms)
            text = " ".join(w.text for w in display_words)
            
            srt_content.append(f"{i}")
            srt_content.append(f"{start} --> {end}")
            srt_content.append(text)
            srt_content.append("")
        
        return "\n".join(srt_content)
    
    def _render_json(self, cues: List[CaptionCue]) -> str:
        """Render captions in JSON format."""
        import json
        
        captions = []
        for cue in cues:
            display_words = cue.words[:3]
            if not display_words:
                continue
            
            captions.append({
                "start_ms": cue.start_ms,
                "end_ms": cue.end_ms,
                "duration_ms": cue.duration_ms,
                "text": " ".join(w.text for w in display_words),
                "words": [
                    {
                        "text": w.text,
                        "start_ms": w.start_ms,
                        "end_ms": w.end_ms,
                        "confidence": w.confidence,
                    }
                    for w in display_words
                ],
            })
        
        return json.dumps(captions, indent=2)
    
    def _format_time(self, ms: float) -> str:
        """Format time for ASS format (H:MM:SS.CC)."""
        total_seconds = ms / 1000
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)
        centiseconds = int((ms % 1000) / 10)
        return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"
    
    def _format_srt_time(self, ms: float) -> str:
        """Format time for SRT format (HH:MM:SS,mmm)."""
        total_seconds = ms / 1000
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)
        milliseconds = int(ms % 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
    
    def render_to_file(
        self,
        cues: List[CaptionCue],
        output_path: str,
        format: Optional[CaptionFormat] = None,
        video_width: int = 1080,
        video_height: int = 1920,
    ):
        """Render captions to a file."""
        content = self.render(cues, format, video_width, video_height)
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        log.info(f"Rendered captions to {output_path}")
